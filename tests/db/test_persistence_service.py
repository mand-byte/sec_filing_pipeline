from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.db.base import Base
from src.db.models import ExtractedFact, ExtractionEvidence, FilingDocument, ReviewTask
from src.pipeline.services import EvidenceInput, FactInput, PersistenceService
from src.pipeline.types import FilingRecord


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False)()


def _filing() -> FilingRecord:
    return FilingRecord(
        accession_no="0000000000-24-000010",
        cik="0000789019",
        ticker="MSFT",
        form_type="4",
        filed_at=None,
        accepted_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
        period_end=None,
        is_amendment=False,
        amendment_no=None,
    )


def _normalize_to_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def test_persist_filing_bundle_supports_multiple_subject_keys() -> None:
    session = _session()
    service = PersistenceService(session)

    service.persist_filing_bundle(
        filing=_filing(),
        route="owner",
        facts=[
            FactInput(field_name="shares_acquired_or_disposed", subject_key="txn:1", value_numeric=100.0),
            FactInput(field_name="shares_acquired_or_disposed", subject_key="txn:2", value_numeric=200.0),
        ],
        evidences=[
            EvidenceInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                locator_kind="obj",
                source_span="transactions[0].shares",
                raw_value="100",
                normalized_value="100.0",
            ),
            EvidenceInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:2",
                locator_kind="obj",
                source_span="transactions[1].shares",
                raw_value="200",
                normalized_value="200.0",
            ),
        ],
    )

    facts = session.query(ExtractedFact).order_by(ExtractedFact.subject_key).all()
    assert len(facts) == 2
    assert [fact.subject_key for fact in facts] == ["txn:1", "txn:2"]

    evidences = session.query(ExtractionEvidence).order_by(ExtractionEvidence.subject_key).all()
    assert len(evidences) == 2
    assert [evidence.subject_key for evidence in evidences] == ["txn:1", "txn:2"]


def test_persist_filing_bundle_updates_existing_subject_key_row() -> None:
    session = _session()
    service = PersistenceService(session)
    filing = _filing()

    service.persist_filing_bundle(
        filing=filing,
        route="owner",
        facts=[FactInput(field_name="transaction_price_per_share", subject_key="txn:1", value_numeric=10.0)],
        evidences=[
            EvidenceInput(
                field_name="transaction_price_per_share",
                subject_key="txn:1",
                locator_kind="obj",
                source_span="transactions[0].price",
                raw_value="10",
                normalized_value="10.0",
            )
        ],
    )
    service.persist_filing_bundle(
        filing=filing,
        route="owner",
        facts=[FactInput(field_name="transaction_price_per_share", subject_key="txn:1", value_numeric=11.0)],
        evidences=[
            EvidenceInput(
                field_name="transaction_price_per_share",
                subject_key="txn:1",
                locator_kind="obj",
                source_span="transactions[0].price",
                raw_value="11",
                normalized_value="11.0",
            )
        ],
    )

    facts = session.query(ExtractedFact).all()
    assert len(facts) == 1
    assert facts[0].subject_key == "txn:1"
    assert facts[0].value_numeric == 11.0


def test_persist_filing_bundle_supports_holding_position_rows() -> None:
    session = _session()
    service = PersistenceService(session)

    service.persist_filing_bundle(
        filing=_filing(),
        route="holding",
        facts=[
            FactInput(field_name="position_value_usd", subject_key="position:1", value_numeric=1250000.0),
            FactInput(field_name="position_value_usd", subject_key="position:2", value_numeric=750000.0),
            FactInput(field_name="info_table_entry_total", subject_key="document", value_numeric=2.0),
        ],
        evidences=[
            EvidenceInput(
                field_name="position_value_usd",
                subject_key="position:1",
                locator_kind="obj",
                source_span="infotable[0].Value",
                raw_value="1250",
                normalized_value="1250000.0",
            ),
            EvidenceInput(
                field_name="position_value_usd",
                subject_key="position:2",
                locator_kind="obj",
                source_span="infotable[1].Value",
                raw_value="750",
                normalized_value="750000.0",
            ),
            EvidenceInput(
                field_name="info_table_entry_total",
                subject_key="document",
                locator_kind="obj",
                source_span="summary_page.tableEntryTotal",
                raw_value="2",
                normalized_value="2.0",
            ),
        ],
    )

    facts = session.query(ExtractedFact).order_by(ExtractedFact.subject_key, ExtractedFact.field_name).all()
    assert len(facts) == 3
    assert [fact.subject_key for fact in facts] == ["document", "position:1", "position:2"]

    evidences = session.query(ExtractionEvidence).order_by(ExtractionEvidence.subject_key, ExtractionEvidence.field_name).all()
    assert len(evidences) == 3
    assert [evidence.subject_key for evidence in evidences] == ["document", "position:1", "position:2"]


def test_persist_filing_bundle_creates_row_level_review_tasks_with_primary_evidence_link() -> None:
    session = _session()
    service = PersistenceService(session)

    service.persist_filing_bundle(
        filing=_filing(),
        route="owner",
        facts=[
            FactInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                value_numeric=100.0,
                confidence=0.49,
                review_reason="first_seen_template",
            ),
            FactInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:2",
                value_numeric=200.0,
                confidence=0.49,
                review_reason="first_seen_template",
            ),
        ],
        evidences=[
            EvidenceInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                locator_kind="obj",
                source_span="transactions[0].shares",
                raw_value="100",
                normalized_value="100.0",
            ),
            EvidenceInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:2",
                locator_kind="obj",
                source_span="transactions[1].shares",
                raw_value="200",
                normalized_value="200.0",
            ),
        ],
    )

    review_tasks = session.query(ReviewTask).order_by(ReviewTask.subject_key).all()
    assert len(review_tasks) == 2
    assert [task.subject_key for task in review_tasks] == ["txn:1", "txn:2"]
    assert all(task.primary_evidence_id is not None for task in review_tasks)

    evidences = session.query(ExtractionEvidence).order_by(ExtractionEvidence.subject_key).all()
    evidence_ids_by_subject = {evidence.subject_key: evidence.id for evidence in evidences}
    assert review_tasks[0].primary_evidence_id == evidence_ids_by_subject["txn:1"]
    assert review_tasks[1].primary_evidence_id == evidence_ids_by_subject["txn:2"]


def test_persist_filing_bundle_deduplicates_open_review_tasks_by_subject_key() -> None:
    session = _session()
    service = PersistenceService(session)
    filing = _filing()

    for numeric_value in (100.0, 101.0):
        service.persist_filing_bundle(
            filing=filing,
            route="owner",
            facts=[
                FactInput(
                    field_name="shares_acquired_or_disposed",
                    subject_key="txn:1",
                    value_numeric=numeric_value,
                    confidence=0.49,
                    review_reason="first_seen_template",
                )
            ],
            evidences=[
                EvidenceInput(
                    field_name="shares_acquired_or_disposed",
                    subject_key="txn:1",
                    locator_kind="obj",
                    source_span="transactions[0].shares",
                    raw_value=str(int(numeric_value)),
                    normalized_value=str(numeric_value),
                )
            ],
        )

    review_tasks = session.query(ReviewTask).all()
    assert len(review_tasks) == 1
    assert review_tasks[0].subject_key == "txn:1"


def test_persist_filing_bundle_persists_filing_metadata_fields() -> None:
    session = _session()
    service = PersistenceService(session)
    filing = FilingRecord(
        accession_no="0000000000-24-000011",
        cik="0000789019",
        ticker="MSFT",
        form_type="10-Q/A",
        filed_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
        accepted_at=datetime(2024, 5, 2, tzinfo=timezone.utc),
        period_end=datetime(2024, 3, 31, tzinfo=timezone.utc),
        is_amendment=True,
        amendment_no=2,
    )

    service.persist_filing_bundle(
        filing=filing,
        route="issuer",
        facts=[FactInput(field_name="total_revenue", subject_key="document", value_numeric=123.0)],
        evidences=[
            EvidenceInput(
                field_name="total_revenue",
                subject_key="document",
                locator_kind="xbrl_xml",
                source_span="xbrl-fact",
                raw_value="123",
                normalized_value="123.0",
            )
        ],
    )

    document = session.query(FilingDocument).one()
    assert _normalize_to_utc(document.filed_at) == filing.filed_at
    assert _normalize_to_utc(document.accepted_at) == filing.accepted_at
    assert _normalize_to_utc(document.period_end) == filing.period_end
    assert document.is_amendment is True
    assert document.amendment_no == 2
