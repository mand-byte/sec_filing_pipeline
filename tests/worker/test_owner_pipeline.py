from datetime import datetime, timezone

from src.models.state import IngestionState
from src.parsers.ownership_xml import ParsedOwnershipFact, ParsedOwnershipSubmission
from src.worker.owner_pipeline import (
    build_fact_row,
    build_review_item,
    persist_owner_submission,
    update_ingestion_state,
)


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.by_pk = {}

    def add(self, obj) -> None:
        self.added.append(obj)
        if hasattr(obj, "fact_id"):
            self.by_pk[(obj.__class__, obj.fact_id)] = obj
        if hasattr(obj, "review_item_id"):
            self.by_pk[(obj.__class__, obj.review_item_id)] = obj

    def get(self, model, pk):
        return self.by_pk.get((model, pk))


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
        parsed_fact=parsed_fact,
    )

    assert fact_row.decision_state == "accepted"
    assert fact_row.confidence_bucket == "high"


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

    review_item = build_review_item(
        accession_no="0000320193-24-000012",
        parsed_fact=parsed_fact,
    )

    assert review_item.review_reason == "mandatory_field_missing"
    assert review_item.status == "open"


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

    review_item = build_review_item(
        accession_no="0000320193-24-000012",
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
        parsed_submission=parsed_submission,
    )

    assert len(session.added) == 3
    assert [obj.__tablename__ for obj in session.added] == [
        "extracted_fact",
        "extracted_fact",
        "review_queue",
    ]


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
    persist_owner_submission(session, "filing-1", parsed_submission)
    first_count = len(session.added)

    persist_owner_submission(session, "filing-1", parsed_submission)

    assert first_count == 3
    assert len(session.added) == 3


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
        parsed_fact=parsed_submission.facts[0],
    )
    existing_review = build_review_item(
        accession_no=parsed_submission.accession_no,
        parsed_fact=parsed_submission.facts[0],
    )

    session = FakeSession()
    session.by_pk[(existing_fact.__class__, existing_fact.fact_id)] = existing_fact
    session.by_pk[(existing_review.__class__, existing_review.review_item_id)] = (
        existing_review
    )

    persist_owner_submission(session, "filing-1", parsed_submission)

    assert session.added == []
