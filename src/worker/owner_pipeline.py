from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from src.models.state import IngestionState
from src.parsers.ownership_deterministic import parse_ownership_deterministic
from src.parsers.ownership_xml import ParsedOwnershipSubmission
from src.parsers.ownership_xml import parse_ownership_xml
from src.storage.filing_repo import FilingRepository
from src.storage.owner_discovery import DiscoveredFiling
from src.storage.raw_store import RawStore
from src.storage.sec_download_adapter import DownloadedAttachment
from src.storage.sec_download_adapter import DownloadedFilingBundle
from src.worker.decision_service import DecisionResult, DecisionService
from src.worker.owner_persistence import (
    PersistedDocumentContext,
    build_fact_row,
    build_review_item,
    ordered_attempt_timestamps,
    persist_owner_bundle_artifacts,
    persist_owner_submission,
    persist_phase_a1_decision_review_artifacts,
)


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


def _ensure_utc_aware(dt: datetime | None) -> datetime | None:
    """Normalize datetime to UTC-aware for safe comparison.

    SQLite may reload datetimes as naive (no timezone), while callers pass
    UTC-aware datetimes. This function ensures both are comparable.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _is_candidate_owner_attachment(attachment: DownloadedAttachment) -> bool:
    filename = attachment.filename.lower()
    content_type = attachment.content_type.lower()
    return filename.endswith((".xml", ".txt")) or "xml" in content_type


def _decode_attachment_text(attachment: DownloadedAttachment) -> str:
    return attachment.content.decode("utf-8", errors="replace")


def _attempted_methods_from_decision_result(decision_result: DecisionResult) -> list[str]:
    attempted = [
        method
        for method in [
            "structured_xml",
            decision_result.selected_parser_method,
        ]
        if method is not None
    ]

    deduped: list[str] = []
    for method in attempted:
        if method not in deduped:
            deduped.append(method)
    return deduped


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

    attempt_timestamps = ordered_attempt_timestamps(attempted_at_utc, 4)
    attempt_index = 0

    def _next_attempted_at() -> datetime:
        nonlocal attempt_index
        timestamp = attempt_timestamps[min(attempt_index, len(attempt_timestamps) - 1)]
        attempt_index += 1
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

    persist_phase_a1_decision_review_artifacts(
        session=session,
        decision_result=decision_result,
        run_id=run_id,
        filing_id=document.filing_id,
        accession_no=document.accession_no,
        document_id=document.document_id,
        selected_attempted_at_utc=attempted_at_utc,
    )

    if decision_result.parsed_submission is None:
        return decision_result

    persist_owner_submission(
        session=session,
        filing_id=document.filing_id,
        accession_no=document.accession_no,
        cik=document.cik,
        document_id=document.document_id,
        run_id=run_id,
        fallback_reason=decision_result.failure_reason,
        attempted_methods=_attempted_methods_from_decision_result(decision_result),
        parsed_facts=decision_result.parsed_submission.facts,
    )
    return decision_result


def update_ingestion_state(
    state: IngestionState,
    accession_no: str,
    acceptance_datetime_utc: datetime,
) -> IngestionState:
    # Normalize persisted datetime to UTC-aware for comparison
    current_acceptance = _ensure_utc_aware(state.last_acceptance_datetime_utc)
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
    return IngestionState(cik=cik, route_type="owner")


def ingest_downloaded_owner_filing_bundle(
    session,
    parse_route_logger,
    raw_store: RawStore,
    bundle: DownloadedFilingBundle,
    run_id: str,
    attempted_at_utc: datetime,
    discovered_filing: DiscoveredFiling | None = None,
    structured_parser: Callable[[str], ParsedOwnershipSubmission] | None = None,
    deterministic_parser: Callable[[str], ParsedOwnershipSubmission] | None = None,
) -> int:
    filing_repo = FilingRepository(session)
    persisted_bundle = persist_owner_bundle_artifacts(
        session=session,
        filing_repo=filing_repo,
        raw_store=raw_store,
        bundle=bundle,
        attempted_at_utc=attempted_at_utc,
        discovered_filing=discovered_filing,
    )

    processed_documents = 0
    for attachment, persisted_doc in persisted_bundle.documents:
        if not _is_candidate_owner_attachment(attachment):
            continue

        _process_persisted_owner_document(
            session=session,
            parse_route_logger=parse_route_logger,
            run_id=run_id,
            attempted_at_utc=attempted_at_utc,
            filing_id=persisted_bundle.filing_id,
            accession_no=bundle.accession_no,
            cik=bundle.cik,
            attachment=attachment,
            persisted_doc=persisted_doc,
            structured_parser=structured_parser,
            deterministic_parser=deterministic_parser,
        )
        processed_documents += 1

    return processed_documents


def _process_persisted_owner_document(
    *,
    session,
    parse_route_logger,
    run_id: str,
    attempted_at_utc: datetime,
    filing_id: str,
    accession_no: str,
    cik: str,
    attachment: DownloadedAttachment,
    persisted_doc: PersistedDocumentContext,
    structured_parser: Callable[[str], ParsedOwnershipSubmission] | None,
    deterministic_parser: Callable[[str], ParsedOwnershipSubmission] | None,
) -> DecisionResult:
    return process_owner_document(
        session=session,
        parse_route_logger=parse_route_logger,
        run_id=run_id,
        attempted_at_utc=attempted_at_utc,
        filing_id=filing_id,
        accession_no=accession_no,
        cik=cik,
        document_id=persisted_doc.document_id,
        document_type=persisted_doc.document_type,
        document_filename=attachment.filename,
        document_path=persisted_doc.document_path,
        snapshot_path=persisted_doc.parser_snapshot_path,
        source_url=persisted_doc.source_url,
        sha256_hex=persisted_doc.sha256_hex,
        byte_length=persisted_doc.byte_length,
        xml_text=_decode_attachment_text(attachment),
        structured_parser=structured_parser,
        deterministic_parser=deterministic_parser,
    )


def replay_owner_accession(
    session,
    parse_route_logger,
    raw_store: RawStore,
    sec_download_adapter,
    cik: str,
    accession_no: str,
    run_id: str,
    attempted_at_utc: datetime,
    discovered_filing: DiscoveredFiling | None = None,
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
        discovered_filing=discovered_filing,
    )
