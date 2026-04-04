from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from hashlib import sha1
from pathlib import Path

from src.domain.enums import DecisionState, ParserMethod, ReviewReason, RouteType
from src.models.filing import ExtractedFact, FilingDocument, FilingIndex
from src.models.review import ReviewQueueItem
from src.parsers.ownership_xml import ParsedOwnershipFact, ParsedOwnershipSubmission
from src.storage.owner_discovery import DiscoveredFiling
from src.storage.raw_store import RawArtifact, RawStore
from src.storage.sec_download_adapter import DownloadedAttachment
from src.storage.sec_download_adapter import DownloadedFilingBundle
from src.worker.decision_service import DecisionResult


@dataclass(frozen=True, slots=True)
class PersistedDocumentContext:
    document_id: str
    document_type: str
    document_path: str
    source_url: str | None
    sha256_hex: str
    byte_length: int
    decoded_text_path: str | None
    parser_snapshot_path: str | None


@dataclass(frozen=True, slots=True)
class PersistedOwnerBundle:
    filing_id: str
    filing_row: FilingIndex | None
    documents: list[tuple[DownloadedAttachment, PersistedDocumentContext]]


def _fact_id(
    accession_no: str,
    document_id: str,
    fact_name: str,
    snippet_locator: str,
) -> str:
    return sha1(
        f"{accession_no}:{document_id}:{fact_name}:{snippet_locator}".encode("utf-8")
    ).hexdigest()


def _filing_form_parts(form_type_raw: str) -> tuple[str, str, bool]:
    form_raw = form_type_raw.strip().upper()
    is_amendment = form_raw.endswith("/A")
    form_base = form_raw[:-2] if is_amendment else form_raw
    return form_raw, form_base, is_amendment


def build_filing_index_row(
    *,
    cik: str,
    accession_no: str,
    form_type_raw: str,
    acceptance_datetime_utc: datetime,
    primary_document: str,
) -> FilingIndex:
    filing_id = f"owner:{cik}:{accession_no}"
    form_raw, form_base, is_amendment = _filing_form_parts(form_type_raw)

    return FilingIndex(
        filing_id=filing_id,
        cik=cik,
        accession_no=accession_no,
        form_type_raw=form_raw,
        form_type_base=form_base,
        is_amendment=is_amendment,
        route_type=RouteType.OWNER.value,
        acceptance_datetime_utc=acceptance_datetime_utc,
        filing_date=acceptance_datetime_utc.date(),
        primary_document=primary_document,
        amendment_group_key=f"owner:{cik}:{accession_no}",
        amendment_sequence=0,
    )


def build_filing_index_row_from_discovered(discovered: DiscoveredFiling) -> FilingIndex:
    return build_filing_index_row(
        cik=discovered.cik,
        accession_no=discovered.accession_no,
        form_type_raw=discovered.form_type_raw,
        acceptance_datetime_utc=discovered.acceptance_datetime_utc,
        primary_document=discovered.primary_document,
    )


def build_filing_index_row_from_bundle(bundle: DownloadedFilingBundle) -> FilingIndex:
    return build_filing_index_row(
        cik=bundle.cik,
        accession_no=bundle.accession_no,
        form_type_raw=bundle.form_type_raw,
        acceptance_datetime_utc=bundle.acceptance_datetime_utc,
        primary_document=bundle.primary_document,
    )


def build_filing_document_row(
    *,
    filing_id: str,
    accession_no: str,
    document_id: str,
    filename: str,
    content_type: str,
    sha256_hex: str,
    byte_length: int,
    raw_path: str,
    decoded_text_path: str | None,
    parser_snapshot_path: str | None,
) -> FilingDocument:
    return FilingDocument(
        document_id=document_id,
        filing_id=filing_id,
        accession_no=accession_no,
        filename=filename,
        content_type=content_type,
        sha256_hex=sha256_hex,
        byte_length=byte_length,
        raw_path=raw_path,
        decoded_text_path=decoded_text_path,
        parser_snapshot_path=parser_snapshot_path,
    )


def build_fact_row(
    *,
    filing_id: str,
    accession_no: str,
    cik: str,
    document_id: str,
    run_id: str,
    fallback_reason: str | None,
    attempted_methods: list[str] | None = None,
    parsed_fact: ParsedOwnershipFact,
) -> ExtractedFact:
    is_complete = bool(parsed_fact.validation_results.get("mandatory_present", True))
    is_numeric_ok = parsed_fact.validation_results.get("is_numeric", True)
    accepted = is_complete and is_numeric_ok and fallback_reason is None

    return ExtractedFact(
        fact_id=_fact_id(
            accession_no,
            document_id,
            parsed_fact.fact_name,
            parsed_fact.snippet_locator,
        ),
        filing_id=filing_id,
        accession_no=accession_no,
        cik=cik,
        document_id=document_id,
        run_id=run_id,
        fact_name=parsed_fact.fact_name,
        fact_value=parsed_fact.fact_value,
        parser_method=parsed_fact.parser_method,
        fallback_reason=fallback_reason,
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
        attempted_methods=attempted_methods or [parsed_fact.parser_method],
    )


def build_review_item(
    *,
    filing_id: str,
    accession_no: str,
    document_id: str,
    run_id: str,
    fact_row: ExtractedFact,
    parsed_fact: ParsedOwnershipFact,
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
        review_item_id=fact_row.fact_id,
        filing_id=filing_id,
        accession_no=accession_no,
        document_id=document_id,
        fact_id=fact_row.fact_id,
        run_id=run_id,
        parser_method=fact_row.parser_method,
        decision_state=fact_row.decision_state,
        review_reason=review_reason,
        payload={
            "fact_name": parsed_fact.fact_name,
            "snippet_locator": parsed_fact.snippet_locator,
            "validation_results": parsed_fact.validation_results,
        },
        status="open",
        note=None,
    )


def build_bundle_level_review_item(
    *,
    filing_id: str,
    accession_no: str,
    document_id: str,
    run_id: str,
    review_reason: str,
    decision_result: DecisionResult,
) -> ReviewQueueItem:
    review_material = (
        f"{accession_no}:{document_id}:{review_reason}:"
        f"{decision_result.selected_parser_method}:{decision_result.failure_reason}"
    )
    review_item_id = sha1(review_material.encode("utf-8")).hexdigest()

    return ReviewQueueItem(
        review_item_id=review_item_id,
        filing_id=filing_id,
        accession_no=accession_no,
        document_id=document_id,
        fact_id=None,
        run_id=run_id,
        parser_method=decision_result.selected_parser_method,
        decision_state=decision_result.final_decision_state,
        review_reason=review_reason,
        payload={
            "failure_reason": decision_result.failure_reason,
            "selected_parser_method": decision_result.selected_parser_method,
            "route_type": decision_result.route_type,
        },
        status="open",
        note=None,
    )


def persist_owner_bundle_artifacts(
    *,
    session,
    filing_repo,
    raw_store: RawStore,
    bundle: DownloadedFilingBundle,
    attempted_at_utc: datetime,
    discovered_filing: DiscoveredFiling | None = None,
) -> PersistedOwnerBundle:
    filing_id = f"owner:{bundle.cik}:{bundle.accession_no}"
    filing_row = (
        build_filing_index_row_from_discovered(discovered_filing)
        if discovered_filing is not None
        else build_filing_index_row_from_bundle(bundle)
    )
    filing_repo.add_filing_index_if_missing(filing_row)

    persisted_documents: list[tuple[DownloadedAttachment, PersistedDocumentContext]] = []

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

        document_id = sha1(
            f"{bundle.accession_no}:{attachment.filename}:{stored.sha256_hex}".encode(
                "utf-8"
            )
        ).hexdigest()
        snapshot_filename = (
            f"{Path(attachment.filename).stem}.{document_id}{Path(attachment.filename).suffix}"
        )

        decoded_text = attachment.content.decode("utf-8", errors="replace")
        decoded_text_path = str(
            raw_store.persist_text_snapshot(
                cik=bundle.cik,
                accession_no=bundle.accession_no,
                filename=snapshot_filename,
                suffix=".decoded.txt",
                content=decoded_text,
            )
        )
        parser_snapshot_path = str(
            raw_store.persist_text_snapshot(
                cik=bundle.cik,
                accession_no=bundle.accession_no,
                filename=snapshot_filename,
                suffix=".parser-input.txt",
                content=decoded_text,
            )
        )

        filing_repo.add_document_if_missing(
            build_filing_document_row(
                filing_id=filing_id,
                accession_no=bundle.accession_no,
                document_id=document_id,
                filename=attachment.filename,
                content_type=attachment.content_type,
                sha256_hex=stored.sha256_hex,
                byte_length=stored.byte_length,
                raw_path=str(stored.path),
                decoded_text_path=decoded_text_path,
                parser_snapshot_path=parser_snapshot_path,
            )
        )

        persisted_documents.append(
            (
                attachment,
                PersistedDocumentContext(
                    document_id=document_id,
                    document_type=(filing_row.form_type_base if filing_row is not None else "4"),
                    document_path=str(stored.path),
                    source_url=None,
                    sha256_hex=stored.sha256_hex,
                    byte_length=stored.byte_length,
                    decoded_text_path=decoded_text_path,
                    parser_snapshot_path=parser_snapshot_path,
                ),
            )
        )

    return PersistedOwnerBundle(
        filing_id=filing_id,
        filing_row=filing_row,
        documents=persisted_documents,
    )


def persist_owner_submission(
    session,
    *,
    filing_id: str,
    cik: str,
    document_id: str,
    run_id: str,
    fallback_reason: str | None,
    attempted_methods: list[str],
    accession_no: str | None = None,
    parsed_submission: ParsedOwnershipSubmission | None = None,
    parsed_facts: list[ParsedOwnershipFact] | None = None,
) -> None:
    effective_parsed_facts = parsed_facts
    effective_accession_no = accession_no
    if parsed_submission is not None:
        effective_parsed_facts = parsed_submission.facts
        effective_accession_no = parsed_submission.accession_no

    if effective_parsed_facts is None or effective_accession_no is None:
        raise ValueError("persist_owner_submission requires parsed facts and accession")

    persisted_ids = getattr(session, "_owner_persisted_ids", None)
    if persisted_ids is None:
        persisted_ids = set()
        setattr(session, "_owner_persisted_ids", persisted_ids)

    session_get = getattr(session, "get", None)

    for parsed_fact in effective_parsed_facts:
        fact_row = build_fact_row(
            filing_id=filing_id,
            accession_no=effective_accession_no,
            cik=cik,
            document_id=document_id,
            run_id=run_id,
            fallback_reason=fallback_reason,
            attempted_methods=attempted_methods,
            parsed_fact=parsed_fact,
        )

        fact_key = ("fact", fact_row.fact_id)
        if fact_key in persisted_ids:
            continue
        if callable(session_get) and session_get(ExtractedFact, fact_row.fact_id) is not None:
            persisted_ids.add(fact_key)
            continue

        session.add(fact_row)
        persisted_ids.add(fact_key)

        if fact_row.decision_state == DecisionState.NEEDS_REVIEW.value:
            review_item = build_review_item(
                filing_id=filing_id,
                accession_no=effective_accession_no,
                document_id=document_id,
                run_id=run_id,
                fact_row=fact_row,
                parsed_fact=parsed_fact,
            )
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


def persist_phase_a1_decision_review_artifacts(
    *,
    session,
    decision_result: DecisionResult,
    run_id: str,
    filing_id: str,
    accession_no: str,
    document_id: str,
    selected_attempted_at_utc: datetime,
) -> None:
    if decision_result.parsed_submission is None:
        review_item = build_bundle_level_review_item(
            filing_id=filing_id,
            accession_no=accession_no,
            document_id=document_id,
            run_id=run_id,
            review_reason=ReviewReason.UNSUPPORTED_LAYOUT.value,
            decision_result=decision_result,
        )
        _add_review_if_missing(session, review_item)
        return

    if decision_result.selected_parser_method != ParserMethod.DETERMINISTIC_RULE.value:
        return

    review_item = build_bundle_level_review_item(
        filing_id=filing_id,
        accession_no=accession_no,
        document_id=document_id,
        run_id=run_id,
        review_reason=ReviewReason.PARSER_DISAGREEMENT.value,
        decision_result=decision_result,
    )
    _add_review_if_missing(session, review_item)


def _add_review_if_missing(session, review_item: ReviewQueueItem) -> None:
    session_get = getattr(session, "get", None)
    if (
        callable(session_get)
        and session_get(ReviewQueueItem, review_item.review_item_id) is not None
    ):
        return

    persisted_ids = getattr(session, "_owner_persisted_ids", None)
    if persisted_ids is None:
        persisted_ids = set()
        setattr(session, "_owner_persisted_ids", persisted_ids)

    review_key = ("review", review_item.review_item_id)
    if review_key in persisted_ids:
        return

    session.add(review_item)
    persisted_ids.add(review_key)


def ordered_attempt_timestamps(
    attempted_at_utc: datetime,
    count: int,
) -> list[datetime]:
    return [attempted_at_utc + timedelta(microseconds=i) for i in range(count)]
