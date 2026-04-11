from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.db.base import Base
from src.db.models import FilingAttempt, PipelineLog
from src.db.repositories import PipelineRepository


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False)()


def test_write_log_persists_error_detail() -> None:
    session = _session()
    repo = PipelineRepository(session)

    repo.write_log(
        run_id="run-001",
        route="issuer",
        stage="extract",
        level="ERROR",
        message="router failed",
        cik="0000789019",
        accession_no="0000000000-24-000001",
        error_type="RuntimeError",
        error_detail="Traceback (most recent call last): ...",
    )

    row = session.query(PipelineLog).one()
    assert row.run_id == "run-001"
    assert row.error_type == "RuntimeError"
    assert row.error_detail == "Traceback (most recent call last): ..."


def test_upsert_filing_attempt_updates_existing_run_route_accession() -> None:
    session = _session()
    repo = PipelineRepository(session)

    repo.upsert_filing_attempt(
        run_id="run-001",
        route="issuer",
        accession_no="0000000000-24-000001",
        cik="0000789019",
        accepted_at=None,
        status="in_progress",
    )
    repo.upsert_filing_attempt(
        run_id="run-001",
        route="issuer",
        accession_no="0000000000-24-000001",
        cik="0000789019",
        accepted_at=None,
        status="failed",
        error_type="RuntimeError",
        error_detail="boom",
    )

    rows = session.query(FilingAttempt).all()
    assert len(rows) == 1
    assert rows[0].status == "failed"
    assert rows[0].error_type == "RuntimeError"
    assert rows[0].error_detail == "boom"
