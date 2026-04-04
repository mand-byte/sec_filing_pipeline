from datetime import datetime, timezone
from pathlib import Path

from src.domain.enums import DecisionState, ParserMethod, ReviewReason
from src.models.filing import FilingDocument, FilingIndex
from src.models.state import IngestionState
from src.parsers.ownership_xml import ParsedOwnershipFact, ParsedOwnershipSubmission
from src.storage.filing_repo import FilingRepository
from src.storage.owner_discovery import DiscoveredFiling
from src.storage.parse_route_log_repo import ParseRouteLogRepository
from src.storage.raw_store import RawStore
from src.storage.sec_download_adapter import (
    DownloadedAttachment,
    DownloadedFilingBundle,
)
from src.worker.owner_persistence import (
    build_fact_row,
    build_filing_document_row,
    build_filing_index_row,
    build_review_item,
    persist_owner_bundle_artifacts,
)
from src.worker.owner_pipeline import (
    ingest_downloaded_owner_filing_bundle,
    persist_owner_submission,
    process_owner_document,
    replay_owner_accession,
    update_ingestion_state,
)


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.by_pk = {}
        self.filing_indexes: list[FilingIndex] = []
        self.filing_documents: list[FilingDocument] = []

    def add(self, obj) -> None:
        self.added.append(obj)

        if hasattr(obj, "fact_id"):
            self.by_pk[(obj.__class__, obj.fact_id)] = obj
        if hasattr(obj, "review_item_id"):
            self.by_pk[(obj.__class__, obj.review_item_id)] = obj
        if isinstance(obj, FilingIndex):
            self.filing_indexes.append(obj)
            self.by_pk[(obj.__class__, obj.filing_id)] = obj
        if isinstance(obj, FilingDocument):
            self.filing_documents.append(obj)
            self.by_pk[(obj.__class__, obj.document_id)] = obj

    def get(self, model, pk):
        return self.by_pk.get((model, pk))


def test_build_filing_index_row_from_discovered_filing() -> None:
    discovered = DiscoveredFiling(
        cik="0000320193",
        accession_no="0000320193-24-000012",
        form_type_raw="4/A",
        acceptance_datetime_utc=datetime(2024, 4, 3, 12, 30, tzinfo=timezone.utc),
        primary_document="ownership.xml",
    )

    row = build_filing_index_row(
        cik=discovered.cik,
        accession_no=discovered.accession_no,
        form_type_raw=discovered.form_type_raw,
        acceptance_datetime_utc=discovered.acceptance_datetime_utc,
        primary_document=discovered.primary_document,
    )

    assert row.filing_id == "owner:0000320193:0000320193-24-000012"
    assert row.form_type_raw == "4/A"
    assert row.form_type_base == "4"
    assert row.is_amendment is True
    assert row.route_type == "owner"


def test_build_filing_document_row_includes_snapshot_paths() -> None:
    row = build_filing_document_row(
        filing_id="owner:0000320193:0000320193-24-000012",
        accession_no="0000320193-24-000012",
        document_id="doc-1",
        filename="ownership.xml",
        content_type="text/xml",
        sha256_hex="a" * 64,
        byte_length=123,
        raw_path="/tmp/raw/doc.xml",
        decoded_text_path="/tmp/snapshots/doc.decoded.txt",
        parser_snapshot_path="/tmp/snapshots/doc.parser-input.txt",
    )

    assert row.document_id == "doc-1"
    assert row.decoded_text_path == "/tmp/snapshots/doc.decoded.txt"
    assert row.parser_snapshot_path == "/tmp/snapshots/doc.parser-input.txt"


def test_build_fact_row_marks_complete_xml_fact_as_accepted() -> None:
    parsed_fact = ParsedOwnershipFact(
        fact_name="transaction_shares",
        fact_value="1234",
        parser_method="structured_xml",
        snippet_text="1234",
        snippet_locator="/ownershipDocument/nonDerivativeTable/nonDerivativeTransaction/transactionAmounts/transactionShares/value",
        document_filename="primary_doc.xml",
        validation_results={"is_numeric": True},
    )

    fact_row = build_fact_row(
        filing_id="filing-1",
        accession_no="0000320193-24-000012",
        cik="0000320193",
        document_id="doc-1",
        run_id="run-1",
        fallback_reason=None,
        parsed_fact=parsed_fact,
    )

    assert fact_row.decision_state == "accepted"
    assert fact_row.confidence_bucket == "high"
    assert fact_row.cik == "0000320193"
    assert fact_row.document_id == "doc-1"
    assert fact_row.run_id == "run-1"


def test_build_review_item_for_missing_mandatory_value() -> None:
    parsed_fact = ParsedOwnershipFact(
        fact_name="reporting_owner_cik",
        fact_value="",
        parser_method="structured_xml",
        snippet_text="",
        snippet_locator="/ownershipDocument/reportingOwner/reportingOwnerId/rptOwnerCik",
        document_filename="primary_doc.xml",
        validation_results={"mandatory_present": False},
    )

    fact_row = build_fact_row(
        filing_id="filing-1",
        accession_no="0000320193-24-000012",
        cik="0000320193",
        document_id="doc-1",
        run_id="run-1",
        fallback_reason=None,
        parsed_fact=parsed_fact,
    )

    review_item = build_review_item(
        filing_id="filing-1",
        accession_no="0000320193-24-000012",
        document_id="doc-1",
        run_id="run-1",
        fact_row=fact_row,
        parsed_fact=parsed_fact,
    )

    assert review_item.review_reason == "mandatory_field_missing"
    assert review_item.status == "open"
    assert review_item.filing_id == "filing-1"
    assert review_item.document_id == "doc-1"
    assert review_item.run_id == "run-1"


def test_build_review_item_for_non_mandatory_validation_failure() -> None:
    parsed_fact = ParsedOwnershipFact(
        fact_name="transaction_shares",
        fact_value="12x",
        parser_method="structured_xml",
        snippet_text="12x",
        snippet_locator="/ownershipDocument/nonDerivativeTable/nonDerivativeTransaction/transactionAmounts/transactionShares/value",
        document_filename="primary_doc.xml",
        validation_results={"mandatory_present": True, "is_numeric": False},
    )

    fact_row = build_fact_row(
        filing_id="filing-1",
        accession_no="0000320193-24-000012",
        cik="0000320193",
        document_id="doc-1",
        run_id="run-1",
        fallback_reason=None,
        parsed_fact=parsed_fact,
    )

    review_item = build_review_item(
        filing_id="filing-1",
        accession_no="0000320193-24-000012",
        document_id="doc-1",
        run_id="run-1",
        fact_row=fact_row,
        parsed_fact=parsed_fact,
    )

    assert review_item.review_reason == "source_conflict"


def test_persist_owner_submission_adds_facts_and_review_items() -> None:
    parsed_submission = ParsedOwnershipSubmission(
        accession_no="0000320193-24-000012",
        document_filename="primary_doc.xml",
        facts=[
            ParsedOwnershipFact(
                fact_name="issuer_cik",
                fact_value="0000320193",
                parser_method="structured_xml",
                snippet_text="0000320193",
                snippet_locator="/ownershipDocument/issuer/issuerCik",
                document_filename="primary_doc.xml",
                validation_results={"mandatory_present": True},
            ),
            ParsedOwnershipFact(
                fact_name="reporting_owner_cik",
                fact_value="",
                parser_method="structured_xml",
                snippet_text="",
                snippet_locator="/ownershipDocument/reportingOwner/reportingOwnerId/rptOwnerCik",
                document_filename="primary_doc.xml",
                validation_results={"mandatory_present": False},
            ),
        ],
    )

    session = FakeSession()
    persist_owner_submission(
        session=session,
        filing_id="filing-1",
        cik="0000320193",
        document_id="doc-1",
        run_id="run-1",
        fallback_reason=None,
        attempted_methods=["structured_xml"],
        parsed_submission=parsed_submission,
    )

    assert len(session.added) == 3
    assert [obj.__tablename__ for obj in session.added] == [
        "extracted_fact",
        "extracted_fact",
        "review_queue",
    ]


def test_update_ingestion_state_handles_naive_datetime_from_db_roundtrip() -> None:
    # Simulate a naive datetime that would be loaded from SQLite after DB round-trip
    # SQLite may reload stored UTC datetime as naive (no timezone info)
    naive_datetime = datetime(2024, 4, 3, 12, 30)  # naive, no tzinfo

    state = IngestionState(
        cik="0000320193",
        route_type="owner",
        last_acceptance_datetime_utc=naive_datetime,
        last_accession_no="0000320193-24-000012",
    )

    # Call with an aware UTC datetime (as callers would do)
    aware_datetime = datetime(2024, 4, 4, 9, 0, tzinfo=timezone.utc)

    # This should NOT raise TypeError: can't compare offset-naive and offset-aware datetimes
    updated = update_ingestion_state(
        state=state,
        accession_no="0000320193-24-000050",
        acceptance_datetime_utc=aware_datetime,
    )

    assert updated.last_acceptance_datetime_utc == aware_datetime
    assert updated.last_accession_no == "0000320193-24-000050"


def test_update_ingestion_state_advances_cursor_values() -> None:
    state = IngestionState(cik="0000320193", route_type="owner")
    acceptance = datetime(2024, 4, 3, 12, 30, tzinfo=timezone.utc)

    updated = update_ingestion_state(
        state=state,
        accession_no="0000320193-24-000012",
        acceptance_datetime_utc=acceptance,
    )

    assert updated.last_acceptance_datetime_utc == acceptance
    assert updated.last_accession_no == "0000320193-24-000012"


def test_update_ingestion_state_keeps_newer_existing_cursor() -> None:
    newer_acceptance = datetime(2024, 4, 4, 9, 0, tzinfo=timezone.utc)
    state = IngestionState(
        cik="0000320193",
        route_type="owner",
        last_acceptance_datetime_utc=newer_acceptance,
        last_accession_no="0000320193-24-000050",
    )

    older_acceptance = datetime(2024, 4, 3, 12, 30, tzinfo=timezone.utc)
    updated = update_ingestion_state(
        state=state,
        accession_no="0000320193-24-000012",
        acceptance_datetime_utc=older_acceptance,
    )

    assert updated.last_acceptance_datetime_utc == newer_acceptance
    assert updated.last_accession_no == "0000320193-24-000050"


def test_persist_owner_submission_is_idempotent_in_same_session() -> None:
    parsed_submission = ParsedOwnershipSubmission(
        accession_no="0000320193-24-000012",
        document_filename="primary_doc.xml",
        facts=[
            ParsedOwnershipFact(
                fact_name="issuer_cik",
                fact_value="0000320193",
                parser_method="structured_xml",
                snippet_text="0000320193",
                snippet_locator="/ownershipDocument/issuer/issuerCik",
                document_filename="primary_doc.xml",
                validation_results={"mandatory_present": True},
            ),
            ParsedOwnershipFact(
                fact_name="reporting_owner_cik",
                fact_value="",
                parser_method="structured_xml",
                snippet_text="",
                snippet_locator="/ownershipDocument/reportingOwner/reportingOwnerId/rptOwnerCik",
                document_filename="primary_doc.xml",
                validation_results={"mandatory_present": False},
            ),
        ],
    )

    session = FakeSession()
    persist_owner_submission(
        session,
        filing_id="filing-1",
        cik="0000320193",
        document_id="doc-1",
        run_id="run-1",
        fallback_reason=None,
        attempted_methods=["structured_xml"],
        parsed_submission=parsed_submission,
    )
    first_count = len(session.added)

    persist_owner_submission(
        session,
        filing_id="filing-1",
        cik="0000320193",
        document_id="doc-1",
        run_id="run-2",
        fallback_reason=None,
        attempted_methods=["structured_xml"],
        parsed_submission=parsed_submission,
    )

    assert first_count == 3
    assert len(session.added) == 3


def test_ingest_downloaded_owner_bundle_persists_distinct_facts_per_document(
    tmp_path,
) -> None:
    bundle = DownloadedFilingBundle(
        cik="0000320193",
        accession_no="0000320193-24-000012",
        form_type_raw="4/A",
        acceptance_datetime_utc=datetime(2024, 4, 1, 9, 15, tzinfo=timezone.utc),
        primary_document="ownership-1.xml",
        attachments=[
            DownloadedAttachment(
                filename="ownership-1.xml",
                content_type="text/xml",
                content=(
                    "<ownershipDocument><issuer><issuerCik>0000320193</issuerCik></issuer>"
                    "</ownershipDocument>"
                ).encode("utf-8"),
            ),
            DownloadedAttachment(
                filename="ownership-2.xml",
                content_type="text/xml",
                content=(
                    "<ownershipDocument><issuer><issuerCik>0000320193</issuerCik></issuer>"
                    "</ownershipDocument>"
                ).encode("utf-8"),
            ),
        ],
    )

    def structured_stub(_: str) -> ParsedOwnershipSubmission:
        return ParsedOwnershipSubmission(
            accession_no="0000320193-24-000012",
            document_filename="ownership.xml",
            facts=[
                ParsedOwnershipFact(
                    fact_name="issuer_cik",
                    fact_value="0000320193",
                    parser_method=ParserMethod.STRUCTURED_XML.value,
                    snippet_text="0000320193",
                    snippet_locator="/ownershipDocument/issuer/issuerCik",
                    document_filename="ownership.xml",
                    validation_results={"mandatory_present": True},
                )
            ],
        )

    session = FakeSession()
    repo = ParseRouteLogRepository(session)
    raw_store = RawStore(tmp_path)

    processed = ingest_downloaded_owner_filing_bundle(
        session=session,
        parse_route_logger=repo,
        raw_store=raw_store,
        bundle=bundle,
        run_id="run-1",
        attempted_at_utc=datetime(2024, 4, 3, 12, 30, tzinfo=timezone.utc),
        structured_parser=structured_stub,
    )

    fact_rows = [
        row for row in session.added if getattr(row, "__tablename__", "") == "extracted_fact"
    ]

    assert processed == 2
    assert len(fact_rows) == 2
    assert len({row.document_id for row in fact_rows}) == 2
    assert len({row.fact_id for row in fact_rows}) == 2


def test_persist_owner_submission_skips_db_existing_rows() -> None:
    parsed_submission = ParsedOwnershipSubmission(
        accession_no="0000320193-24-000012",
        document_filename="primary_doc.xml",
        facts=[
            ParsedOwnershipFact(
                fact_name="reporting_owner_cik",
                fact_value="",
                parser_method="structured_xml",
                snippet_text="",
                snippet_locator="/ownershipDocument/reportingOwner/reportingOwnerId/rptOwnerCik",
                document_filename="primary_doc.xml",
                validation_results={"mandatory_present": False},
            )
        ],
    )

    existing_fact = build_fact_row(
        filing_id="filing-1",
        accession_no=parsed_submission.accession_no,
        cik="0000320193",
        document_id="doc-1",
        run_id="run-1",
        fallback_reason=None,
        parsed_fact=parsed_submission.facts[0],
    )
    existing_review = build_review_item(
        filing_id="filing-1",
        accession_no=parsed_submission.accession_no,
        document_id="doc-1",
        run_id="run-1",
        fact_row=existing_fact,
        parsed_fact=parsed_submission.facts[0],
    )

    session = FakeSession()
    session.by_pk[(existing_fact.__class__, existing_fact.fact_id)] = existing_fact
    session.by_pk[(existing_review.__class__, existing_review.review_item_id)] = (
        existing_review
    )

    persist_owner_submission(
        session,
        filing_id="filing-1",
        cik="0000320193",
        document_id="doc-1",
        run_id="run-2",
        fallback_reason=None,
        attempted_methods=["structured_xml"],
        parsed_submission=parsed_submission,
    )

    assert session.added == []


def test_replay_creates_new_parse_route_log_rows_with_new_run_id() -> None:
    xml_text = """
    <ownershipDocument>
      <issuer><issuerCik>0000320193</issuerCik></issuer>
      <reportingOwner>
        <reportingOwnerId><rptOwnerCik>0001214156</rptOwnerCik></reportingOwnerId>
      </reportingOwner>
      <nonDerivativeTable>
        <nonDerivativeTransaction>
          <transactionAmounts><transactionShares><value>1200</value></transactionShares></transactionAmounts>
        </nonDerivativeTransaction>
      </nonDerivativeTable>
    </ownershipDocument>
    """.strip()

    session = FakeSession()
    parse_route_logger = ParseRouteLogRepository(session)
    attempted_at = datetime(2024, 4, 3, 12, 30, tzinfo=timezone.utc)

    process_owner_document(
        session=session,
        parse_route_logger=parse_route_logger,
        run_id="run-1",
        attempted_at_utc=attempted_at,
        filing_id="filing-1",
        accession_no="0000320193-24-000012",
        cik="0000320193",
        document_id="doc-1",
        document_type="4",
        document_filename="primary_doc.xml",
        document_path="raw/0000320193/0000320193-24-000012/doc-1.xml",
        snapshot_path=None,
        source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019324000012/xslF345X05/doc.xml",
        sha256_hex="a" * 64,
        byte_length=len(xml_text.encode("utf-8")),
        xml_text=xml_text,
    )

    keys_after_first_run = set(session.by_pk)

    process_owner_document(
        session=session,
        parse_route_logger=parse_route_logger,
        run_id="run-2",
        attempted_at_utc=attempted_at,
        filing_id="filing-1",
        accession_no="0000320193-24-000012",
        cik="0000320193",
        document_id="doc-1",
        document_type="4",
        document_filename="primary_doc.xml",
        document_path="raw/0000320193/0000320193-24-000012/doc-1.xml",
        snapshot_path=None,
        source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019324000012/xslF345X05/doc.xml",
        sha256_hex="a" * 64,
        byte_length=len(xml_text.encode("utf-8")),
        xml_text=xml_text,
    )

    assert len(session.rows) == 2
    assert {row.run_id for row in session.rows} == {"run-1", "run-2"}
    assert set(session.by_pk) == keys_after_first_run


def test_process_owner_document_fallback_logs_ordered_attempt_timeline() -> None:
    xml_text = "ownership text"
    session = FakeSession()
    parse_route_logger = ParseRouteLogRepository(session)
    attempted_at = datetime(2024, 4, 3, 13, 0, tzinfo=timezone.utc)

    def structured_stub(_: str) -> ParsedOwnershipSubmission:
        return ParsedOwnershipSubmission(
            accession_no="0000320193-24-000012",
            document_filename="primary_doc.xml",
            facts=[
                ParsedOwnershipFact(
                    fact_name="issuer_cik",
                    fact_value="",
                    parser_method=ParserMethod.STRUCTURED_XML.value,
                    snippet_text="",
                    snippet_locator="/ownershipDocument/issuer/issuerCik",
                    document_filename="primary_doc.xml",
                    validation_results={"mandatory_present": False},
                )
            ],
        )

    def deterministic_stub(_: str) -> ParsedOwnershipSubmission:
        return ParsedOwnershipSubmission(
            accession_no="0000320193-24-000012",
            document_filename="primary_doc.txt",
            facts=[
                ParsedOwnershipFact(
                    fact_name="issuer_cik",
                    fact_value="0000320193",
                    parser_method=ParserMethod.DETERMINISTIC_RULE.value,
                    snippet_text="Issuer CIK: 0000320193",
                    snippet_locator="line:1",
                    document_filename="primary_doc.txt",
                    validation_results={"mandatory_present": True},
                )
            ],
        )

    process_owner_document(
        session=session,
        parse_route_logger=parse_route_logger,
        run_id="run-1",
        attempted_at_utc=attempted_at,
        filing_id="filing-1",
        accession_no="0000320193-24-000012",
        cik="0000320193",
        document_id="doc-1",
        document_type="4",
        document_filename="primary_doc.xml",
        document_path="raw/0000320193/0000320193-24-000012/doc-1.xml",
        snapshot_path=None,
        source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019324000012/xslF345X05/doc.xml",
        sha256_hex="a" * 64,
        byte_length=len(xml_text.encode("utf-8")),
        xml_text=xml_text,
        structured_parser=structured_stub,
        deterministic_parser=deterministic_stub,
    )

    review_reasons = [
        row.review_reason
        for row in session.added
        if getattr(row, "__tablename__", "") == "review_queue"
    ]
    fact_rows = [
        row for row in session.added if getattr(row, "__tablename__", "") == "extracted_fact"
    ]

    assert [row.parser_method for row in session.rows] == [
        ParserMethod.STRUCTURED_XML.value,
        ParserMethod.DETERMINISTIC_RULE.value,
    ]
    assert session.rows[0].attempted_at_utc == attempted_at
    assert session.rows[1].attempted_at_utc > session.rows[0].attempted_at_utc
    assert session.rows[0].fallback_reason is not None
    assert ReviewReason.PARSER_DISAGREEMENT.value in review_reasons
    assert len(fact_rows) == 1
    assert fact_rows[0].fallback_reason is not None
    assert fact_rows[0].attempted_methods == [
        ParserMethod.STRUCTURED_XML.value,
        ParserMethod.DETERMINISTIC_RULE.value,
    ]


def test_process_owner_document_deterministic_fallback_success_persists_needs_review_fact() -> (
    None
):
    xml_text = "ownership text"
    session = FakeSession()
    parse_route_logger = ParseRouteLogRepository(session)
    attempted_at = datetime(2024, 4, 3, 13, 10, tzinfo=timezone.utc)

    def structured_stub(_: str) -> ParsedOwnershipSubmission:
        return ParsedOwnershipSubmission(
            accession_no="0000320193-24-000012",
            document_filename="primary_doc.xml",
            facts=[
                ParsedOwnershipFact(
                    fact_name="issuer_cik",
                    fact_value="",
                    parser_method=ParserMethod.STRUCTURED_XML.value,
                    snippet_text="",
                    snippet_locator="/ownershipDocument/issuer/issuerCik",
                    document_filename="primary_doc.xml",
                    validation_results={"mandatory_present": False},
                )
            ],
        )

    def deterministic_stub(_: str) -> ParsedOwnershipSubmission:
        return ParsedOwnershipSubmission(
            accession_no="0000320193-24-000012",
            document_filename="primary_doc.txt",
            facts=[
                ParsedOwnershipFact(
                    fact_name="issuer_cik",
                    fact_value="0000320193",
                    parser_method=ParserMethod.DETERMINISTIC_RULE.value,
                    snippet_text="Issuer CIK: 0000320193",
                    snippet_locator="line:1",
                    document_filename="primary_doc.txt",
                    validation_results={"mandatory_present": True, "is_numeric": True},
                )
            ],
        )

    result = process_owner_document(
        session=session,
        parse_route_logger=parse_route_logger,
        run_id="run-1",
        attempted_at_utc=attempted_at,
        filing_id="filing-1",
        accession_no="0000320193-24-000012",
        cik="0000320193",
        document_id="doc-1",
        document_type="4",
        document_filename="primary_doc.xml",
        document_path="raw/0000320193/0000320193-24-000012/doc-1.xml",
        snapshot_path=None,
        source_url=None,
        sha256_hex="a" * 64,
        byte_length=len(xml_text.encode("utf-8")),
        xml_text=xml_text,
        structured_parser=structured_stub,
        deterministic_parser=deterministic_stub,
    )

    fact_rows = [
        row for row in session.added if getattr(row, "__tablename__", "") == "extracted_fact"
    ]
    disagreement_reviews = [
        row
        for row in session.added
        if getattr(row, "__tablename__", "") == "review_queue"
        and row.review_reason == ReviewReason.PARSER_DISAGREEMENT.value
    ]

    assert result.final_decision_state == DecisionState.NEEDS_REVIEW.value
    assert len(fact_rows) == 1
    assert fact_rows[0].decision_state == DecisionState.NEEDS_REVIEW.value
    assert fact_rows[0].confidence_bucket != "high"
    assert len(disagreement_reviews) == 1


def test_process_owner_document_emits_unsupported_layout_review_when_all_methods_fail() -> (
    None
):
    xml_text = "ownership text"
    session = FakeSession()
    parse_route_logger = ParseRouteLogRepository(session)
    attempted_at = datetime(2024, 4, 3, 13, 5, tzinfo=timezone.utc)

    def structured_stub(_: str) -> ParsedOwnershipSubmission:
        raise ValueError("invalid xml")

    def deterministic_stub(_: str) -> ParsedOwnershipSubmission:
        raise ValueError("deterministic parser not applicable")

    result = process_owner_document(
        session=session,
        parse_route_logger=parse_route_logger,
        run_id="run-1",
        attempted_at_utc=attempted_at,
        filing_id="filing-1",
        accession_no="0000320193-24-000012",
        cik="0000320193",
        document_id="doc-1",
        document_type="4",
        document_filename="primary_doc.xml",
        document_path="raw/0000320193/0000320193-24-000012/doc-1.xml",
        snapshot_path="/tmp/snapshot.txt",
        source_url=None,
        sha256_hex="a" * 64,
        byte_length=len(xml_text.encode("utf-8")),
        xml_text=xml_text,
        structured_parser=structured_stub,
        deterministic_parser=deterministic_stub,
    )

    review_rows = [
        row
        for row in session.added
        if getattr(row, "__tablename__", "") == "review_queue"
    ]

    assert result.parsed_submission is None
    assert len(review_rows) == 1
    assert review_rows[0].review_reason == ReviewReason.UNSUPPORTED_LAYOUT.value


def test_process_owner_document_parser_disagreement_review_is_idempotent_across_replay() -> (
    None
):
    xml_text = "ownership text"
    session = FakeSession()
    parse_route_logger = ParseRouteLogRepository(session)
    attempted_at = datetime(2024, 4, 3, 13, 0, tzinfo=timezone.utc)

    def structured_stub(_: str) -> ParsedOwnershipSubmission:
        return ParsedOwnershipSubmission(
            accession_no="0000320193-24-000012",
            document_filename="primary_doc.xml",
            facts=[
                ParsedOwnershipFact(
                    fact_name="issuer_cik",
                    fact_value="",
                    parser_method=ParserMethod.STRUCTURED_XML.value,
                    snippet_text="",
                    snippet_locator="/ownershipDocument/issuer/issuerCik",
                    document_filename="primary_doc.xml",
                    validation_results={"mandatory_present": False},
                )
            ],
        )

    def deterministic_stub(_: str) -> ParsedOwnershipSubmission:
        return ParsedOwnershipSubmission(
            accession_no="0000320193-24-000012",
            document_filename="primary_doc.txt",
            facts=[
                ParsedOwnershipFact(
                    fact_name="issuer_cik",
                    fact_value="0000320193",
                    parser_method=ParserMethod.DETERMINISTIC_RULE.value,
                    snippet_text="Issuer CIK: 0000320193",
                    snippet_locator="line:1",
                    document_filename="primary_doc.txt",
                    validation_results={"mandatory_present": True},
                )
            ],
        )

    process_owner_document(
        session=session,
        parse_route_logger=parse_route_logger,
        run_id="run-1",
        attempted_at_utc=attempted_at,
        filing_id="filing-1",
        accession_no="0000320193-24-000012",
        cik="0000320193",
        document_id="doc-1",
        document_type="4",
        document_filename="primary_doc.xml",
        document_path="raw/0000320193/0000320193-24-000012/doc-1.xml",
        snapshot_path=None,
        source_url=None,
        sha256_hex="a" * 64,
        byte_length=len(xml_text.encode("utf-8")),
        xml_text=xml_text,
        structured_parser=structured_stub,
        deterministic_parser=deterministic_stub,
    )
    process_owner_document(
        session=session,
        parse_route_logger=parse_route_logger,
        run_id="run-2",
        attempted_at_utc=attempted_at,
        filing_id="filing-1",
        accession_no="0000320193-24-000012",
        cik="0000320193",
        document_id="doc-1",
        document_type="4",
        document_filename="primary_doc.xml",
        document_path="raw/0000320193/0000320193-24-000012/doc-1.xml",
        snapshot_path=None,
        source_url=None,
        sha256_hex="a" * 64,
        byte_length=len(xml_text.encode("utf-8")),
        xml_text=xml_text,
        structured_parser=structured_stub,
        deterministic_parser=deterministic_stub,
    )

    disagreement_reviews = [
        row
        for row in session.added
        if getattr(row, "__tablename__", "") == "review_queue"
        and row.review_reason == ReviewReason.PARSER_DISAGREEMENT.value
    ]

    assert len(disagreement_reviews) == 1


def test_process_owner_document_unsupported_layout_review_is_idempotent_across_replay() -> (
    None
):
    xml_text = "ownership text"
    session = FakeSession()
    parse_route_logger = ParseRouteLogRepository(session)
    attempted_at = datetime(2024, 4, 3, 13, 5, tzinfo=timezone.utc)

    def structured_stub(_: str) -> ParsedOwnershipSubmission:
        raise ValueError("invalid xml")

    def deterministic_stub(_: str) -> ParsedOwnershipSubmission:
        raise ValueError("deterministic parser not applicable")

    process_owner_document(
        session=session,
        parse_route_logger=parse_route_logger,
        run_id="run-1",
        attempted_at_utc=attempted_at,
        filing_id="filing-1",
        accession_no="0000320193-24-000012",
        cik="0000320193",
        document_id="doc-1",
        document_type="4",
        document_filename="primary_doc.xml",
        document_path="raw/0000320193/0000320193-24-000012/doc-1.xml",
        snapshot_path="/tmp/snapshot.txt",
        source_url=None,
        sha256_hex="a" * 64,
        byte_length=len(xml_text.encode("utf-8")),
        xml_text=xml_text,
        structured_parser=structured_stub,
        deterministic_parser=deterministic_stub,
    )
    process_owner_document(
        session=session,
        parse_route_logger=parse_route_logger,
        run_id="run-2",
        attempted_at_utc=attempted_at,
        filing_id="filing-1",
        accession_no="0000320193-24-000012",
        cik="0000320193",
        document_id="doc-1",
        document_type="4",
        document_filename="primary_doc.xml",
        document_path="raw/0000320193/0000320193-24-000012/doc-1.xml",
        snapshot_path="/tmp/snapshot.txt",
        source_url=None,
        sha256_hex="a" * 64,
        byte_length=len(xml_text.encode("utf-8")),
        xml_text=xml_text,
        structured_parser=structured_stub,
        deterministic_parser=deterministic_stub,
    )

    unsupported_layout_reviews = [
        row
        for row in session.added
        if getattr(row, "__tablename__", "") == "review_queue"
        and row.review_reason == ReviewReason.UNSUPPORTED_LAYOUT.value
    ]

    assert len(unsupported_layout_reviews) == 1


def test_ingest_downloaded_owner_bundle_persists_documents_and_discovered_metadata(
    tmp_path,
) -> None:
    bundle = DownloadedFilingBundle(
        cik="0000320193",
        accession_no="0000320193-24-000012",
        form_type_raw="4/A",
        acceptance_datetime_utc=datetime(2024, 4, 1, 9, 15, tzinfo=timezone.utc),
        primary_document="ownership.xml",
        attachments=[
            DownloadedAttachment(
                filename="ownership.xml",
                content_type="text/xml",
                content=(
                    "<ownershipDocument><issuer><issuerCik>0000320193</issuerCik></issuer>"
                    "</ownershipDocument>"
                ).encode("utf-8"),
            ),
            DownloadedAttachment(
                filename="index.json",
                content_type="application/json",
                content=b"{}",
            ),
        ],
    )
    discovered = DiscoveredFiling(
        cik="0000320193",
        accession_no="0000320193-24-000012",
        form_type_raw="4/A",
        acceptance_datetime_utc=datetime(2024, 4, 1, 9, 15, tzinfo=timezone.utc),
        primary_document="ownership.xml",
    )

    session = FakeSession()
    repo = ParseRouteLogRepository(session)
    raw_store = RawStore(tmp_path)

    processed = ingest_downloaded_owner_filing_bundle(
        session=session,
        parse_route_logger=repo,
        raw_store=raw_store,
        bundle=bundle,
        run_id="run-1",
        attempted_at_utc=datetime(2024, 4, 3, 12, 30, tzinfo=timezone.utc),
        discovered_filing=discovered,
    )

    filing_index = session.filing_indexes[0]
    xml_document = next(
        row for row in session.filing_documents if row.filename == "ownership.xml"
    )

    assert processed == 1
    assert len(session.filing_indexes) == 1
    assert filing_index.form_type_raw == "4/A"
    assert filing_index.form_type_base == "4"
    assert filing_index.is_amendment is True
    assert filing_index.acceptance_datetime_utc == discovered.acceptance_datetime_utc
    assert filing_index.primary_document == discovered.primary_document
    assert len(session.filing_documents) == 2
    assert xml_document.decoded_text_path is not None
    assert xml_document.parser_snapshot_path is not None
    assert len(session.rows) >= 1
    assert list(tmp_path.rglob("*"))


def test_persist_owner_bundle_artifacts_uses_distinct_snapshot_paths_for_same_stem_attachments(
    tmp_path,
) -> None:
    bundle = DownloadedFilingBundle(
        cik="0000320193",
        accession_no="0000320193-24-000012",
        form_type_raw="4/A",
        acceptance_datetime_utc=datetime(2024, 4, 1, 9, 15, tzinfo=timezone.utc),
        primary_document="ownership.xml",
        attachments=[
            DownloadedAttachment(
                filename="ownership.xml",
                content_type="text/xml",
                content=b"<ownershipDocument>xml source</ownershipDocument>",
            ),
            DownloadedAttachment(
                filename="ownership.txt",
                content_type="text/plain",
                content=b"deterministic parser text source",
            ),
        ],
    )

    session = FakeSession()
    raw_store = RawStore(tmp_path)
    filing_repo = FilingRepository(session)

    persisted = persist_owner_bundle_artifacts(
        session=session,
        filing_repo=filing_repo,
        raw_store=raw_store,
        bundle=bundle,
        attempted_at_utc=datetime(2024, 4, 3, 12, 30, tzinfo=timezone.utc),
    )

    by_filename = {attachment.filename: context for attachment, context in persisted.documents}
    xml_context = by_filename["ownership.xml"]
    txt_context = by_filename["ownership.txt"]

    # Document type comes from filing form base, not attachment type (e.g. "4" from "4/A")
    assert xml_context.document_type == "4"
    assert txt_context.document_type == "4"

    assert xml_context.decoded_text_path is not None
    assert xml_context.parser_snapshot_path is not None
    assert txt_context.decoded_text_path is not None
    assert txt_context.parser_snapshot_path is not None

    assert xml_context.decoded_text_path != txt_context.decoded_text_path
    assert xml_context.parser_snapshot_path != txt_context.parser_snapshot_path

    xml_decoded = Path(xml_context.decoded_text_path).read_text(encoding="utf-8")
    txt_decoded = Path(txt_context.decoded_text_path).read_text(encoding="utf-8")
    xml_parser_input = Path(xml_context.parser_snapshot_path).read_text(encoding="utf-8")
    txt_parser_input = Path(txt_context.parser_snapshot_path).read_text(encoding="utf-8")

    assert xml_decoded == "<ownershipDocument>xml source</ownershipDocument>"
    assert txt_decoded == "deterministic parser text source"
    assert xml_parser_input == "<ownershipDocument>xml source</ownershipDocument>"
    assert txt_parser_input == "deterministic parser text source"


def test_replay_owner_accession_uses_download_adapter(tmp_path) -> None:
    class _Adapter:
        def download_owner_filing_bundle(
            self, cik: str, accession_no: str
        ) -> DownloadedFilingBundle:
            assert cik == "0000320193"
            assert accession_no == "0000320193-24-000012"
            return DownloadedFilingBundle(
                cik=cik,
                accession_no=accession_no,
                form_type_raw="4/A",
                acceptance_datetime_utc=datetime(
                    2024, 4, 2, 8, 0, tzinfo=timezone.utc
                ),
                primary_document="ownership.xml",
                attachments=[
                    DownloadedAttachment(
                        filename="ownership.xml",
                        content_type="text/xml",
                        content=(
                            "<ownershipDocument><issuer><issuerCik>0000320193</issuerCik></issuer>"
                            "</ownershipDocument>"
                        ).encode("utf-8"),
                    )
                ],
            )

    discovered = DiscoveredFiling(
        cik="0000320193",
        accession_no="0000320193-24-000012",
        form_type_raw="4/A",
        acceptance_datetime_utc=datetime(2024, 4, 2, 8, 0, tzinfo=timezone.utc),
        primary_document="ownership.xml",
    )

    session = FakeSession()
    repo = ParseRouteLogRepository(session)
    raw_store = RawStore(tmp_path)

    processed = replay_owner_accession(
        session=session,
        parse_route_logger=repo,
        raw_store=raw_store,
        sec_download_adapter=_Adapter(),
        cik="0000320193",
        accession_no="0000320193-24-000012",
        run_id="run-2",
        attempted_at_utc=datetime(2024, 4, 3, 12, 45, tzinfo=timezone.utc),
        discovered_filing=discovered,
    )

    filing_index = session.filing_indexes[0]

    assert processed == 1
    assert len(session.filing_indexes) == 1
    assert filing_index.form_type_raw == "4/A"
    assert filing_index.acceptance_datetime_utc == discovered.acceptance_datetime_utc
    assert filing_index.primary_document == "ownership.xml"
    assert len(session.filing_documents) == 1
    assert len(session.rows) >= 1


def test_ingest_downloaded_owner_bundle_without_discovered_persists_filing_index_from_bundle_metadata(
    tmp_path,
) -> None:
    bundle = DownloadedFilingBundle(
        cik="0000320193",
        accession_no="0000320193-24-000012",
        form_type_raw="4/A",
        acceptance_datetime_utc=datetime(2024, 4, 1, 9, 15, tzinfo=timezone.utc),
        primary_document="ownership.xml",
        attachments=[
            DownloadedAttachment(
                filename="ownership.xml",
                content_type="text/xml",
                content=(
                    "<ownershipDocument><issuer><issuerCik>0000320193</issuerCik></issuer>"
                    "</ownershipDocument>"
                ).encode("utf-8"),
            )
        ],
    )

    session = FakeSession()
    repo = ParseRouteLogRepository(session)
    raw_store = RawStore(tmp_path)

    processed = ingest_downloaded_owner_filing_bundle(
        session=session,
        parse_route_logger=repo,
        raw_store=raw_store,
        bundle=bundle,
        run_id="run-1",
        attempted_at_utc=datetime(2024, 4, 3, 12, 30, tzinfo=timezone.utc),
    )

    filing_index = session.filing_indexes[0]

    assert processed == 1
    assert len(session.filing_indexes) == 1
    assert filing_index.form_type_raw == "4/A"
    assert filing_index.form_type_base == "4"
    assert filing_index.is_amendment is True
    assert filing_index.acceptance_datetime_utc == bundle.acceptance_datetime_utc
    assert filing_index.primary_document == bundle.primary_document
    assert len(session.filing_documents) == 1
    assert len(session.rows) >= 1
