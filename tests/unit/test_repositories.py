from datetime import datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from src.db.base import Base
from src.db.models import DelistedRouteCompletion, PipelineLog, RouteWatermark
from src.db.repositories import PipelineRepository


def _install_commit_spy(session: Session, monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    calls = {"count": 0}
    original_commit = session.commit

    def commit_wrapper() -> None:
        calls["count"] += 1
        original_commit()

    monkeypatch.setattr(session, "commit", commit_wrapper)
    return calls


@pytest.fixture
def db_session() -> Session:
    import src.db.models  # noqa: F401

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with session_factory() as session:
        yield session


def test_get_route_watermark_returns_none_when_row_missing(db_session: Session):
    repo = PipelineRepository(db_session)

    assert repo.get_route_watermark("0000000001", "issuer") is None


def test_upsert_route_watermark_inserts_updates_max_and_commits(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = PipelineRepository(db_session)
    commit_calls = _install_commit_spy(db_session, monkeypatch)

    older = datetime(2025, 1, 1, 10, 0, 0)
    newer = datetime(2025, 1, 2, 10, 0, 0)

    repo.upsert_route_watermark("0000000001", "issuer", older)
    repo.upsert_route_watermark("0000000001", "issuer", newer)
    repo.upsert_route_watermark("0000000001", "issuer", older)

    assert commit_calls["count"] == 3
    assert repo.get_route_watermark("0000000001", "issuer") == newer

    row_count = db_session.scalar(
        select(func.count())
        .select_from(RouteWatermark)
        .where(RouteWatermark.cik == "0000000001", RouteWatermark.route == "issuer")
    )
    assert row_count == 1


def test_mark_delisted_route_completed_upserts_completion_state_and_commits(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = PipelineRepository(db_session)
    commit_calls = _install_commit_spy(db_session, monkeypatch)

    first_snapshot = datetime(2025, 2, 1, 9, 0, 0)
    first_last_seen = datetime(2025, 1, 31, 23, 59, 0)
    first_completed_at = datetime(2025, 2, 1, 9, 30, 0)

    second_snapshot = datetime(2025, 2, 2, 9, 0, 0)
    second_last_seen = datetime(2025, 2, 1, 18, 0, 0)
    second_completed_at = datetime(2025, 2, 2, 9, 30, 0)

    repo.mark_delisted_route_completed(
        composite_figi="BBG000000001",
        cik="0000000001",
        route="owner",
        delisted_utc_snapshot=first_snapshot,
        last_seen_accepted_at=first_last_seen,
        completed_at=first_completed_at,
    )
    repo.mark_delisted_route_completed(
        composite_figi="BBG000000001",
        cik="0000000001",
        route="owner",
        delisted_utc_snapshot=second_snapshot,
        last_seen_accepted_at=second_last_seen,
        completed_at=second_completed_at,
    )

    assert commit_calls["count"] == 2

    row = db_session.scalar(
        select(DelistedRouteCompletion).where(
            DelistedRouteCompletion.composite_figi == "BBG000000001",
            DelistedRouteCompletion.cik == "0000000001",
            DelistedRouteCompletion.route == "owner",
        )
    )
    assert row is not None
    assert row.is_completed is True
    assert row.delisted_utc_snapshot == second_snapshot
    assert row.last_seen_accepted_at == second_last_seen
    assert row.completed_at == second_completed_at

    row_count = db_session.scalar(
        select(func.count())
        .select_from(DelistedRouteCompletion)
        .where(
            DelistedRouteCompletion.composite_figi == "BBG000000001",
            DelistedRouteCompletion.cik == "0000000001",
            DelistedRouteCompletion.route == "owner",
        )
    )
    assert row_count == 1


def test_write_log_inserts_pipeline_log_row_and_commits(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = PipelineRepository(db_session)
    commit_calls = _install_commit_spy(db_session, monkeypatch)

    created_at = datetime(2025, 3, 1, 12, 0, 0)

    repo.write_log(
        run_id="run-001",
        route="holding",
        cik="0000000001",
        accession_no="0000000001-25-000001",
        stage="extract",
        level="info",
        message="ok",
        error_type=None,
        created_at=created_at,
    )

    assert commit_calls["count"] == 1

    row = db_session.scalar(
        select(PipelineLog).where(
            PipelineLog.run_id == "run-001",
            PipelineLog.route == "holding",
        )
    )

    assert row is not None
    assert row.cik == "0000000001"
    assert row.accession_no == "0000000001-25-000001"
    assert row.stage == "extract"
    assert row.level == "info"
    assert row.message == "ok"
    assert row.error_type is None
    assert row.created_at == created_at
