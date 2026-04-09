from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.db.base import Base
from src.db.models import ExtractedFact, ExtractionEvidence
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
