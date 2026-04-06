from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from src.db.base import Base
from src.db.models import ExtractedFact, ExtractionEvidence, FilingDocument, ReviewTask
from src.pipeline.services import EvidenceInput, FactInput, PersistenceService
from src.pipeline.types import FilingRecord


@pytest.fixture
def db_session() -> Session:
    import src.db.models  # noqa: F401

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with session_factory() as session:
        yield session


def _filing(accession_no: str, form_type: str = "8-K") -> FilingRecord:
    return FilingRecord(
        accession_no=accession_no,
        cik="0000000001",
        ticker="ACME",
        form_type=form_type,
        filed_at=datetime(2025, 1, 2, 0, 0, tzinfo=timezone.utc),
        accepted_at=datetime(2025, 1, 2, 12, 0, tzinfo=timezone.utc),
        period_end=None,
        is_amendment=form_type.endswith("/A"),
        amendment_no=1 if form_type.endswith("/A") else None,
    )


def test_persist_filing_bundle_rejects_facts_without_evidence(db_session: Session):
    service = PersistenceService(db_session)

    with pytest.raises(ValueError, match="at least one evidence"):
        service.persist_filing_bundle(
            filing=_filing("0000000001-25-000001"),
            route="issuer",
            facts=[
                FactInput(
                    field_name="shares_outstanding",
                    value_numeric=100.0,
                    value_text=None,
                    value_json=None,
                    value_unit="shares",
                    confidence=0.95,
                    extracted_at=datetime(2025, 1, 2, 12, 1, tzinfo=timezone.utc),
                )
            ],
            evidences=[],
        )


def test_persist_filing_bundle_treats_amendment_as_new_document(db_session: Session):
    service = PersistenceService(db_session)

    service.persist_filing_bundle(
        filing=_filing("0000000001-25-000001", "8-K"),
        route="issuer",
        facts=[],
        evidences=[],
    )
    service.persist_filing_bundle(
        filing=_filing("0000000001-25-000001/A", "8-K/A"),
        route="issuer",
        facts=[],
        evidences=[],
    )

    rows = db_session.scalars(
        select(FilingDocument).where(FilingDocument.cik == "0000000001")
    ).all()

    assert len(rows) == 2
    assert {row.accession_no for row in rows} == {
        "0000000001-25-000001",
        "0000000001-25-000001/A",
    }


def test_persist_filing_bundle_low_confidence_fact_opens_review_task(db_session: Session):
    service = PersistenceService(db_session)

    service.persist_filing_bundle(
        filing=_filing("0000000001-25-000002"),
        route="owner",
        facts=[
            FactInput(
                field_name="ownership_pct",
                value_numeric=2.5,
                value_text=None,
                value_json=None,
                value_unit="percent",
                confidence=0.49,
                extracted_at=datetime(2025, 1, 3, 12, 1, tzinfo=timezone.utc),
            )
        ],
        evidences=[
            EvidenceInput(
                field_name="ownership_pct",
                locator_kind="html_span",
                source_section="Ownership",
                source_item_no=None,
                source_xpath="/html/body/div[1]/p[4]",
                xbrl_concept=None,
                source_span="Beneficial ownership is 2.5%.",
                raw_value="2.5%",
                normalized_value="2.5",
                created_at=datetime(2025, 1, 3, 12, 1, tzinfo=timezone.utc),
            )
        ],
    )

    fact_count = db_session.scalar(select(func.count()).select_from(ExtractedFact))
    evidence_count = db_session.scalar(select(func.count()).select_from(ExtractionEvidence))
    review_tasks = db_session.scalars(select(ReviewTask)).all()

    assert fact_count == 1
    assert evidence_count == 1
    assert len(review_tasks) == 1
    assert review_tasks[0].accession_no == "0000000001-25-000002"
    assert review_tasks[0].route == "owner"
    assert review_tasks[0].field_name == "ownership_pct"
