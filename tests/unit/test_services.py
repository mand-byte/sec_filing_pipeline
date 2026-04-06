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
                    value_unit="shares",
                    confidence=0.95,
                )
            ],
            evidences=[],
        )


def test_persist_filing_bundle_uses_internal_timestamps_and_commits_once(db_session: Session):
    service = PersistenceService(db_session)

    commit_calls = 0
    original_commit = db_session.commit

    def counted_commit():
        nonlocal commit_calls
        commit_calls += 1
        original_commit()

    db_session.commit = counted_commit  # type: ignore[method-assign]

    before = datetime.now(timezone.utc)
    service.persist_filing_bundle(
        filing=_filing("0000000001-25-000002"),
        route="owner",
        facts=[
            FactInput(
                field_name="ownership_pct",
                value_numeric=2.5,
                value_unit="percent",
                confidence=0.49,
            )
        ],
        evidences=[
            EvidenceInput(
                field_name="ownership_pct",
                locator_kind="html_span",
                source_span="Beneficial ownership is 2.5%.",
                source_section="Ownership",
                source_xpath="/html/body/div[1]/p[4]",
                raw_value="2.5%",
                normalized_value="2.5",
            )
        ],
    )
    after = datetime.now(timezone.utc)

    filing_doc = db_session.scalar(
        select(FilingDocument).where(FilingDocument.accession_no == "0000000001-25-000002")
    )
    fact = db_session.scalar(
        select(ExtractedFact).where(ExtractedFact.accession_no == "0000000001-25-000002")
    )
    evidence = db_session.scalar(
        select(ExtractionEvidence).where(ExtractionEvidence.accession_no == "0000000001-25-000002")
    )
    review_tasks = db_session.scalars(select(ReviewTask)).all()

    assert filing_doc is not None
    assert fact is not None
    assert evidence is not None

    before_naive = before.replace(tzinfo=None)
    after_naive = after.replace(tzinfo=None)

    assert before_naive <= filing_doc.created_at <= after_naive
    assert before_naive <= fact.extracted_at <= after_naive
    assert before_naive <= evidence.created_at <= after_naive
    assert len(review_tasks) == 1
    assert review_tasks[0].priority == "high"
    assert commit_calls == 1


def test_persist_filing_bundle_fact_persistence_is_idempotent(db_session: Session):
    service = PersistenceService(db_session)

    service.persist_filing_bundle(
        filing=_filing("0000000001-25-000003"),
        route="issuer",
        facts=[
            FactInput(
                field_name="shares_outstanding",
                value_numeric=100.0,
                value_unit="shares",
                confidence=0.9,
            )
        ],
        evidences=[
            EvidenceInput(
                field_name="shares_outstanding",
                locator_kind="html_span",
                source_span="100 shares",
            )
        ],
    )

    service.persist_filing_bundle(
        filing=_filing("0000000001-25-000003"),
        route="issuer",
        facts=[
            FactInput(
                field_name="shares_outstanding",
                value_numeric=125.0,
                value_unit="shares",
                confidence=0.95,
            )
        ],
        evidences=[
            EvidenceInput(
                field_name="shares_outstanding",
                locator_kind="html_span",
                source_span="125 shares",
            )
        ],
    )

    facts = db_session.scalars(
        select(ExtractedFact).where(ExtractedFact.accession_no == "0000000001-25-000003")
    ).all()
    filings = db_session.scalars(
        select(FilingDocument).where(FilingDocument.accession_no == "0000000001-25-000003")
    ).all()

    assert len(facts) == 1
    assert facts[0].value_numeric == 125.0
    assert len(filings) == 1


def test_persist_filing_bundle_keeps_route_string_compatible(db_session: Session):
    service = PersistenceService(db_session)

    service.persist_filing_bundle(
        filing=_filing("0000000001-25-000004"),
        route="issuer",
        facts=[],
        evidences=[
            EvidenceInput(
                field_name="dummy",
                locator_kind="html_span",
                source_span="dummy",
            )
        ],
    )

    evidence = db_session.scalar(
        select(ExtractionEvidence).where(ExtractionEvidence.accession_no == "0000000001-25-000004")
    )
    assert evidence is not None
    assert evidence.route == "issuer"


def test_persist_filing_bundle_persists_evidence_rows(db_session: Session):
    service = PersistenceService(db_session)

    service.persist_filing_bundle(
        filing=_filing("0000000001-25-000005"),
        route="owner",
        facts=[],
        evidences=[
            EvidenceInput(
                field_name="ownership_pct",
                locator_kind="xbrl",
                source_span="2.5",
                xbrl_concept="dei:EntityCommonStockSharesOutstanding",
                normalized_value="2.5",
            ),
            EvidenceInput(
                field_name="ownership_pct",
                locator_kind="html_span",
                source_span="Beneficial ownership is 2.5%.",
                source_section="Ownership",
                raw_value="2.5%",
                normalized_value="2.5",
            ),
        ],
    )

    evidence_count = db_session.scalar(select(func.count()).select_from(ExtractionEvidence))
    assert evidence_count == 2


def test_persist_filing_bundle_does_not_duplicate_open_review_tasks(db_session: Session):
    service = PersistenceService(db_session)
    filing = _filing("0000000001-25-000006")

    service.persist_filing_bundle(
        filing=filing,
        route="owner",
        facts=[
            FactInput(
                field_name="ownership_pct",
                value_numeric=2.5,
                value_unit="percent",
                confidence=0.49,
            )
        ],
        evidences=[
            EvidenceInput(
                field_name="ownership_pct",
                locator_kind="html_span",
                source_span="Beneficial ownership is 2.5%.",
            )
        ],
    )

    service.persist_filing_bundle(
        filing=filing,
        route="owner",
        facts=[
            FactInput(
                field_name="ownership_pct",
                value_numeric=2.6,
                value_unit="percent",
                confidence=0.45,
            )
        ],
        evidences=[
            EvidenceInput(
                field_name="ownership_pct",
                locator_kind="html_span",
                source_span="Beneficial ownership is 2.6%.",
            )
        ],
    )

    review_tasks = db_session.scalars(
        select(ReviewTask).where(
            ReviewTask.accession_no == "0000000001-25-000006",
            ReviewTask.route == "owner",
            ReviewTask.field_name == "ownership_pct",
            ReviewTask.status == "open",
        )
    ).all()

    assert len(review_tasks) == 1
