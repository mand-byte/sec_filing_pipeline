from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.db.base import Base
from src.db.models import DelistedRouteCompletion, FilingAttempt, PipelineLog, RouteWatermark
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


def test_upsert_filing_attempt_preserves_started_at_and_bumps_updated_at() -> None:
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
    row = session.query(FilingAttempt).one()
    started_at = row.started_at
    first_updated_at = row.updated_at

    repo.upsert_filing_attempt(
        run_id="run-001",
        route="issuer",
        accession_no="0000000000-24-000001",
        cik="0000789019",
        accepted_at=datetime(2024, 5, 2, tzinfo=timezone.utc),
        status="completed",
    )

    updated = session.query(FilingAttempt).one()
    assert updated.started_at == started_at
    assert updated.updated_at.replace(tzinfo=None) >= first_updated_at.replace(tzinfo=None)
    assert updated.status == "completed"


def test_upsert_route_watermark_only_moves_forward() -> None:
    session = _session()
    repo = PipelineRepository(session)

    newer = datetime(2024, 5, 2, 12, tzinfo=timezone.utc)
    older = newer - timedelta(days=1)

    repo.upsert_route_watermark(cik="0000789019", route="issuer", accepted_at=newer)
    repo.upsert_route_watermark(cik="0000789019", route="issuer", accepted_at=older)

    row = session.query(RouteWatermark).one()
    assert row.last_accepted_at == newer.replace(tzinfo=None)


def test_delisted_route_completion_can_be_marked_and_invalidated() -> None:
    session = _session()
    repo = PipelineRepository(session)
    snapshot = datetime(2024, 5, 5, tzinfo=timezone.utc)
    last_seen = datetime(2024, 5, 4, tzinfo=timezone.utc)

    repo.mark_delisted_route_completed(
        composite_figi="BBG000BPH459",
        cik="0000789019",
        route="issuer",
        delisted_utc_snapshot=snapshot,
        last_seen_accepted_at=last_seen,
    )
    repo.invalidate_delisted_route_completion(
        composite_figi="BBG000BPH459",
        cik="0000789019",
        route="issuer",
    )

    row = session.query(DelistedRouteCompletion).one()
    assert row.is_completed is False
    assert row.delisted_utc_snapshot is None
    assert row.last_seen_accepted_at is None
