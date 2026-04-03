from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from hashlib import sha1
from typing import Callable

from src.domain.enums import DecisionState, ReviewReason, RouteType
from src.models.filing import ExtractedFact
from src.models.review import ReviewQueueItem
from src.models.state import IngestionState
from src.parsers.ownership_deterministic import parse_ownership_deterministic
from src.parsers.ownership_xml import ParsedOwnershipFact, ParsedOwnershipSubmission
from src.parsers.ownership_xml import parse_ownership_xml
from src.storage.raw_store import RawArtifact, RawStore
from src.storage.sec_download_adapter import (
    DownloadedAttachment,
    DownloadedFilingBundle,
)
from src.worker.decision_service import DecisionResult, DecisionService


@dataclass(frozen=True, slots=True)
class ParseDocument:
    filing_id: str
    accession_no: str
    cik: str
    document_id: str
    document_type: str
    document_filename: str
    document_path: str
    snapshot_path: str | None
    source_url: str | None
    sha256_hex: str
    byte_length: int
    xml_text: str


@dataclass(frozen=True, slots=True)
class _DecisionContextDocument:
    run_id: str
    filing_id: str
    accession_no: str
    cik: str
    document_id: str
    document_type: str
    document_filename: str
    document_path: str
    snapshot_path: str | None
    source_url: str | None
    sha256_hex: str
    byte_length: int


def process_owner_document(
    session,
    parse_route_logger,
    run_id: str,
    attempted_at_utc: datetime,
    filing_id: str,
    accession_no: str,
    cik: str,
    document_id: str,
    document_type: str,
    document_filename: str,
    document_path: str,
    snapshot_path: str | None,
    source_url: str | None,
    sha256_hex: str,
    byte_length: int,
    xml_text: str,
    structured_parser: Callable[[str], ParsedOwnershipSubmission] | None = None,
    deterministic_parser: Callable[[str], ParsedOwnershipSubmission] | None = None,
) -> DecisionResult:
    document = ParseDocument(
        filing_id=filing_id,
        accession_no=accession_no,
        cik=cik,
        document_id=document_id,
        document_type=document_type,
        document_filename=document_filename,
        document_path=document_path,
        snapshot_path=snapshot_path,
        source_url=source_url,
        sha256_hex=sha256_hex,
        byte_length=byte_length,
        xml_text=xml_text,
    )

    effective_structured_parser = structured_parser or (
        lambda text: parse_ownership_xml(
            accession_no=document.accession_no,
            document_filename=document.document_filename,
            xml_text=text,
        )
    )
    effective_deterministic_parser = deterministic_parser or (
        lambda text: parse_ownership_deterministic(
            accession_no=document.accession_no,
            document_filename=document.document_filename,
            source_text=text,
        )
    )

    attempt_sequence = 0

    def _next_attempted_at() -> datetime:
        nonlocal attempt_sequence
        timestamp = attempted_at_utc + timedelta(microseconds=attempt_sequence)
        attempt_sequence += 1
        return timestamp

    decision_service = DecisionService(
        structured_parser=effective_structured_parser,
        deterministic_parser=effective_deterministic_parser,
        attempt_log_repo=parse_route_logger,
        now_fn=_next_attempted_at,
    )

    decision_result = decision_service.parse_document(
        document=_DecisionContextDocument(
            run_id=run_id,
            filing_id=document.filing_id,
            accession_no=document.accession_no,
            cik=document.cik,
            document_id=document.document_id,
            document_type=document.document_type,
            document_filename=document.document_filename,
            document_path=document.document_path,
            snapshot_path=document.snapshot_path,
            source_url=document.source_url,
            sha256_hex=document.sha256_hex,
            byte_length=document.byte_length,
        ),
        document_text=document.xml_text,
    )

    if decision_result.parsed_submission is None:
        return decision_result

    persist_owner_submission(
        session=session,
        filing_id=document.filing_id,
        parsed_submission=decision_result.parsed_submission,
    )
    return decision_result


def _fact_id(accession_no: str, fact_name: str, snippet_locator: str) -> str:
    return sha1(
        f"{accession_no}:{fact_name}:{snippet_locator}".encode("utf-8")
    ).hexdigest()


def build_fact_row(
    filing_id: str,
    accession_no: str,
    parsed_fact: ParsedOwnershipFact,
) -> ExtractedFact:
    is_complete = bool(parsed_fact.validation_results.get("mandatory_present", True))
    is_numeric_ok = parsed_fact.validation_results.get("is_numeric", True)
    accepted = is_complete and is_numeric_ok

    return ExtractedFact(
        fact_id=_fact_id(
            accession_no, parsed_fact.fact_name, parsed_fact.snippet_locator
        ),
        filing_id=filing_id,
        accession_no=accession_no,
        fact_name=parsed_fact.fact_name,
        fact_value=parsed_fact.fact_value,
        parser_method=parsed_fact.parser_method,
        confidence_score=0.99 if accepted else 0.30,
        confidence_bucket="high" if accepted else "low",
        decision_state=(
            DecisionState.ACCEPTED.value
            if accepted
            else DecisionState.NEEDS_REVIEW.value
        ),
        snippet_text=parsed_fact.snippet_text,
        snippet_locator=parsed_fact.snippet_locator,
        document_filename=parsed_fact.document_filename,
        validation_results=parsed_fact.validation_results,
        attempted_methods=[parsed_fact.parser_method],
    )


def build_review_item(
    accession_no: str, parsed_fact: ParsedOwnershipFact
) -> ReviewQueueItem:
    mandatory_present = bool(
        parsed_fact.validation_results.get("mandatory_present", True)
    )
    review_reason = (
        ReviewReason.MANDATORY_FIELD_MISSING.value
        if not mandatory_present
        else ReviewReason.SOURCE_CONFLICT.value
    )

    return ReviewQueueItem(
        review_item_id=_fact_id(
            accession_no, parsed_fact.fact_name, parsed_fact.snippet_locator
        ),
        accession_no=accession_no,
        fact_id=None,
        review_reason=review_reason,
        payload={
            "fact_name": parsed_fact.fact_name,
            "snippet_locator": parsed_fact.snippet_locator,
            "validation_results": parsed_fact.validation_results,
        },
        status="open",
        note=None,
    )


def persist_owner_submission(
    session,
    filing_id: str,
    parsed_submission: ParsedOwnershipSubmission,
) -> None:
    persisted_ids = getattr(session, "_owner_persisted_ids", None)
    if persisted_ids is None:
        persisted_ids = set()
        setattr(session, "_owner_persisted_ids", persisted_ids)

    for parsed_fact in parsed_submission.facts:
        fact_row = build_fact_row(
            filing_id=filing_id,
            accession_no=parsed_submission.accession_no,
            parsed_fact=parsed_fact,
        )
        session_get = getattr(session, "get", None)

        fact_key = ("fact", fact_row.fact_id)
        if fact_key in persisted_ids:
            continue
        if (
            callable(session_get)
            and session_get(ExtractedFact, fact_row.fact_id) is not None
        ):
            persisted_ids.add(fact_key)
            continue

        session.add(fact_row)
        persisted_ids.add(fact_key)

        if fact_row.decision_state == DecisionState.NEEDS_REVIEW.value:
            review_item = build_review_item(parsed_submission.accession_no, parsed_fact)
            review_key = ("review", review_item.review_item_id)
            if review_key in persisted_ids:
                continue
            if (
                callable(session_get)
                and session_get(ReviewQueueItem, review_item.review_item_id) is not None
            ):
                persisted_ids.add(review_key)
                continue
            session.add(review_item)
            persisted_ids.add(review_key)


def update_ingestion_state(
    state: IngestionState,
    accession_no: str,
    acceptance_datetime_utc: datetime,
) -> IngestionState:
    current_acceptance = state.last_acceptance_datetime_utc
    current_accession = state.last_accession_no or ""

    should_advance = current_acceptance is None
    if current_acceptance is not None:
        if acceptance_datetime_utc > current_acceptance:
            should_advance = True
        elif (
            acceptance_datetime_utc == current_acceptance
            and accession_no > current_accession
        ):
            should_advance = True

    if should_advance:
        state.last_accession_no = accession_no
        state.last_acceptance_datetime_utc = acceptance_datetime_utc

    return state


def default_ingestion_state(cik: str) -> IngestionState:
    return IngestionState(cik=cik, route_type=RouteType.OWNER.value)


def _is_candidate_owner_attachment(attachment: DownloadedAttachment) -> bool:
    filename = attachment.filename.lower()
    content_type = attachment.content_type.lower()
    return filename.endswith((".xml", ".txt")) or "xml" in content_type


def _decode_attachment_text(attachment: DownloadedAttachment) -> str:
    return attachment.content.decode("utf-8", errors="replace")


def ingest_downloaded_owner_filing_bundle(
    session,
    parse_route_logger,
    raw_store: RawStore,
    bundle: DownloadedFilingBundle,
    run_id: str,
    attempted_at_utc: datetime,
    structured_parser: Callable[[str], ParsedOwnershipSubmission] | None = None,
    deterministic_parser: Callable[[str], ParsedOwnershipSubmission] | None = None,
) -> int:
    processed_documents = 0
    for attachment in bundle.attachments:
        stored = raw_store.persist_document(
            RawArtifact(
                cik=bundle.cik,
                accession_no=bundle.accession_no,
                filename=attachment.filename,
                content_type=attachment.content_type,
                content=attachment.content,
            )
        )

        if not _is_candidate_owner_attachment(attachment):
            continue

        document_id = sha1(
            f"{bundle.accession_no}:{attachment.filename}:{stored.sha256_hex}".encode(
                "utf-8"
            )
        ).hexdigest()
        process_owner_document(
            session=session,
            parse_route_logger=parse_route_logger,
            run_id=run_id,
            attempted_at_utc=attempted_at_utc,
            filing_id=f"owner:{bundle.cik}:{bundle.accession_no}",
            accession_no=bundle.accession_no,
            cik=bundle.cik,
            document_id=document_id,
            document_type="4",
            document_filename=attachment.filename,
            document_path=str(stored.path),
            snapshot_path=None,
            source_url=None,
            sha256_hex=stored.sha256_hex,
            byte_length=stored.byte_length,
            xml_text=_decode_attachment_text(attachment),
            structured_parser=structured_parser,
            deterministic_parser=deterministic_parser,
        )
        processed_documents += 1

    return processed_documents


def replay_owner_accession(
    session,
    parse_route_logger,
    raw_store: RawStore,
    sec_download_adapter,
    cik: str,
    accession_no: str,
    run_id: str,
    attempted_at_utc: datetime,
) -> int:
    bundle = sec_download_adapter.download_owner_filing_bundle(
        cik=cik,
        accession_no=accession_no,
    )
    return ingest_downloaded_owner_filing_bundle(
        session=session,
        parse_route_logger=parse_route_logger,
        raw_store=raw_store,
        bundle=bundle,
        run_id=run_id,
        attempted_at_utc=attempted_at_utc,
    )
