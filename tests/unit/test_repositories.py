from dataclasses import fields
from datetime import datetime, timezone
from typing import get_args

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.dml import Insert

from src.db.base import Base
from src.db.models import DelistedRouteCompletion, PipelineLog, RouteWatermark
from src.db.repositories import PipelineRepository
from src.pipeline.types import FilingRecord, RouteName


def _install_commit_spy(session: Session, monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    calls = {"count": 0}
    original_commit = session.commit

    def commit_wrapper() -> None:
        calls["count"] += 1
        original_commit()

    monkeypatch.setattr(session, "commit", commit_wrapper)
    return calls


def _install_failing_commit_with_rollback_spy(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, int]:
    calls = {"commit": 0, "rollback": 0}
    original_rollback = session.rollback

    def commit_wrapper() -> None:
        calls["commit"] += 1
        raise RuntimeError("commit failed")

    def rollback_wrapper() -> None:
        calls["rollback"] += 1
        original_rollback()

    monkeypatch.setattr(session, "commit", commit_wrapper)
    monkeypatch.setattr(session, "rollback", rollback_wrapper)
    return calls


def _as_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value

    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _force_postgresql_dialect(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session.bind.dialect, "name", "postgresql")


def _install_execute_spy(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    calls: dict[str, object] = {"count": 0, "statements": []}

    def execute_wrapper(statement, *args, **kwargs):
        calls["count"] = int(calls["count"]) + 1
        calls["statements"].append(statement)
        return None

    monkeypatch.setattr(session, "execute", execute_wrapper)
    return calls


@pytest.fixture
def db_session() -> Session:
    import src.db.models  # noqa: F401

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with session_factory() as session:
        yield session


def test_filing_record_matches_task3_plan_shape():
    assert get_args(RouteName) == ("issuer", "owner", "holding")
    assert [field.name for field in fields(FilingRecord)] == [
        "accession_no",
        "cik",
        "ticker",
        "form_type",
        "filed_at",
        "accepted_at",
        "period_end",
        "is_amendment",
        "amendment_no",
    ]


def test_repository_exposes_session_and_keyword_only_contract(db_session: Session):
    repo = PipelineRepository(db_session)

    assert repo.session is db_session

    with pytest.raises(TypeError):
        repo.upsert_route_watermark("0000000001", "issuer", datetime(2025, 1, 1, 10, 0, 0))

    with pytest.raises(TypeError):
        repo.mark_delisted_route_completed("BBG000000001", "0000000001", "owner", None, None)

    with pytest.raises(TypeError):
        repo.write_log("run-001", "issuer", "extract", "info", "ok")


def test_get_route_watermark_returns_none_when_row_missing(db_session: Session):
    repo = PipelineRepository(db_session)

    assert repo.get_route_watermark("0000000001", "issuer") is None


def test_upsert_route_watermark_inserts_updates_max_and_commits(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = PipelineRepository(db_session)
    commit_calls = _install_commit_spy(repo.session, monkeypatch)

    older = datetime(2025, 1, 1, 10, 0, 0)
    newer = datetime(2025, 1, 2, 10, 0, 0)

    repo.upsert_route_watermark(cik="0000000001", route="issuer", accepted_at=older)

    first_row = db_session.scalar(
        select(RouteWatermark).where(
            RouteWatermark.cik == "0000000001",
            RouteWatermark.route == "issuer",
        )
    )
    assert first_row is not None
    first_updated_at = first_row.updated_at

    repo.upsert_route_watermark(cik="0000000001", route="issuer", accepted_at=newer)

    second_row = db_session.scalar(
        select(RouteWatermark).where(
            RouteWatermark.cik == "0000000001",
            RouteWatermark.route == "issuer",
        )
    )
    assert second_row is not None
    second_updated_at = second_row.updated_at

    repo.upsert_route_watermark(cik="0000000001", route="issuer", accepted_at=older)

    third_row = db_session.scalar(
        select(RouteWatermark).where(
            RouteWatermark.cik == "0000000001",
            RouteWatermark.route == "issuer",
        )
    )
    assert third_row is not None

    repo.upsert_route_watermark(cik="0000000001", route="issuer", accepted_at=newer)

    fourth_row = db_session.scalar(
        select(RouteWatermark).where(
            RouteWatermark.cik == "0000000001",
            RouteWatermark.route == "issuer",
        )
    )
    assert fourth_row is not None

    assert commit_calls["count"] == 4
    assert repo.get_route_watermark("0000000001", "issuer") == newer
    assert _as_naive_utc(second_updated_at) >= _as_naive_utc(first_updated_at)
    assert third_row.last_accepted_at == newer
    assert fourth_row.last_accepted_at == newer
    assert _as_naive_utc(third_row.updated_at) == _as_naive_utc(second_updated_at)
    assert _as_naive_utc(fourth_row.updated_at) == _as_naive_utc(second_updated_at)

    row_count = db_session.scalar(
        select(func.count())
        .select_from(RouteWatermark)
        .where(RouteWatermark.cik == "0000000001", RouteWatermark.route == "issuer")
    )
    assert row_count == 1


def test_upsert_route_watermark_handles_mixed_aware_and_naive_datetimes_in_fallback_path(
    db_session: Session,
):
    repo = PipelineRepository(db_session)

    first_aware = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
    same_naive = datetime(2025, 1, 1, 10, 0)
    older_naive = datetime(2025, 1, 1, 9, 59)
    newer_naive = datetime(2025, 1, 1, 10, 1)

    repo.upsert_route_watermark(cik="0000000002", route="issuer", accepted_at=first_aware)
    repo.upsert_route_watermark(cik="0000000002", route="issuer", accepted_at=same_naive)
    repo.upsert_route_watermark(cik="0000000002", route="issuer", accepted_at=older_naive)

    before_newer = repo.get_route_watermark("0000000002", "issuer")
    assert before_newer is not None
    assert _as_naive_utc(before_newer) == _as_naive_utc(first_aware)

    repo.upsert_route_watermark(cik="0000000002", route="issuer", accepted_at=newer_naive)

    final_value = repo.get_route_watermark("0000000002", "issuer")
    assert final_value is not None
    assert _as_naive_utc(final_value) == newer_naive


def test_upsert_route_watermark_uses_postgres_on_conflict_stmt_and_commits(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = PipelineRepository(db_session)
    _force_postgresql_dialect(repo.session, monkeypatch)
    execute_calls = _install_execute_spy(repo.session, monkeypatch)
    commit_calls = _install_commit_spy(repo.session, monkeypatch)

    older = datetime(2025, 1, 1, 10, 0, 0)
    newer = datetime(2025, 1, 2, 10, 0, 0)

    repo.upsert_route_watermark(cik="0000000003", route="issuer", accepted_at=older)
    repo.upsert_route_watermark(cik="0000000003", route="issuer", accepted_at=newer)

    assert execute_calls["count"] == 2
    assert commit_calls["count"] == 2

    statements = execute_calls["statements"]
    first_stmt = statements[0]
    second_stmt = statements[1]

    assert isinstance(first_stmt, Insert)
    assert isinstance(second_stmt, Insert)

    first_sql = str(first_stmt.compile(dialect=postgresql.dialect()))
    second_sql = str(second_stmt.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT ON CONSTRAINT uq_route_watermark_cik_route DO UPDATE" in first_sql
    assert "excluded.last_accepted_at > route_watermark.last_accepted_at" in first_sql
    assert "ON CONFLICT ON CONSTRAINT uq_route_watermark_cik_route DO UPDATE" in second_sql


def test_mark_delisted_route_completed_uses_postgres_on_conflict_stmt_and_commits(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = PipelineRepository(db_session)
    _force_postgresql_dialect(repo.session, monkeypatch)
    execute_calls = _install_execute_spy(repo.session, monkeypatch)
    commit_calls = _install_commit_spy(repo.session, monkeypatch)

    repo.mark_delisted_route_completed(
        composite_figi="BBG000000009",
        cik="0000000009",
        route="owner",
        delisted_utc_snapshot=datetime(2025, 2, 1, 9, 0, 0),
        last_seen_accepted_at=datetime(2025, 1, 31, 23, 59, 0),
    )

    assert execute_calls["count"] == 1
    assert commit_calls["count"] == 1

    stmt = execute_calls["statements"][0]
    assert isinstance(stmt, Insert)

    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT ON CONSTRAINT uq_delisted_completion_key DO UPDATE" in sql


def test_mark_delisted_route_completed_upserts_completion_state_and_commits(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = PipelineRepository(db_session)
    commit_calls = _install_commit_spy(repo.session, monkeypatch)

    first_snapshot = datetime(2025, 2, 1, 9, 0, 0)
    first_last_seen = datetime(2025, 1, 31, 23, 59, 0)

    before_first = datetime.now(timezone.utc)
    repo.mark_delisted_route_completed(
        composite_figi="BBG000000001",
        cik="0000000001",
        route="owner",
        delisted_utc_snapshot=first_snapshot,
        last_seen_accepted_at=first_last_seen,
    )
    after_first = datetime.now(timezone.utc)

    first_row = db_session.scalar(
        select(DelistedRouteCompletion).where(
            DelistedRouteCompletion.composite_figi == "BBG000000001",
            DelistedRouteCompletion.cik == "0000000001",
            DelistedRouteCompletion.route == "owner",
        )
    )
    assert first_row is not None
    first_completed_at = first_row.completed_at

    second_snapshot = datetime(2025, 2, 2, 9, 0, 0)
    second_last_seen = datetime(2025, 2, 1, 18, 0, 0)

    before_second = datetime.now(timezone.utc)
    repo.mark_delisted_route_completed(
        composite_figi="BBG000000001",
        cik="0000000001",
        route="owner",
        delisted_utc_snapshot=second_snapshot,
        last_seen_accepted_at=second_last_seen,
    )
    after_second = datetime.now(timezone.utc)

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
    assert row.completed_at is not None
    assert row.updated_at is not None
    assert row.completed_at == row.updated_at

    assert _as_naive_utc(before_first) <= _as_naive_utc(first_completed_at) <= _as_naive_utc(after_first)
    assert _as_naive_utc(before_second) <= _as_naive_utc(row.completed_at) <= _as_naive_utc(after_second)
    assert _as_naive_utc(row.completed_at) >= _as_naive_utc(first_completed_at)

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
    commit_calls = _install_commit_spy(repo.session, monkeypatch)

    before = datetime.now(timezone.utc)
    repo.write_log(
        run_id="run-001",
        route="holding",
        cik="0000000001",
        accession_no="0000000001-25-000001",
        stage="extract",
        level="info",
        message="ok",
        error_type=None,
    )
    after = datetime.now(timezone.utc)

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
    assert _as_naive_utc(before) <= _as_naive_utc(row.created_at) <= _as_naive_utc(after)


def test_postgres_upsert_paths_rollback_on_commit_failure(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = PipelineRepository(db_session)
    _force_postgresql_dialect(repo.session, monkeypatch)
    execute_calls = _install_execute_spy(repo.session, monkeypatch)
    calls = _install_failing_commit_with_rollback_spy(repo.session, monkeypatch)

    with pytest.raises(RuntimeError, match="commit failed"):
        repo.upsert_route_watermark(
            cik="0000000010",
            route="issuer",
            accepted_at=datetime(2025, 1, 2, 10, 0, 0),
        )

    assert execute_calls["count"] == 1
    assert calls["commit"] == 1
    assert calls["rollback"] == 1

    with pytest.raises(RuntimeError, match="commit failed"):
        repo.mark_delisted_route_completed(
            composite_figi="BBG000000010",
            cik="0000000010",
            route="owner",
            delisted_utc_snapshot=datetime(2025, 2, 1, 9, 0, 0),
            last_seen_accepted_at=datetime(2025, 1, 31, 23, 59, 0),
        )

    assert execute_calls["count"] == 2
    assert calls["commit"] == 2
    assert calls["rollback"] == 2


@pytest.mark.parametrize(
    ("method_name", "kwargs"),
    [
        (
            "upsert_route_watermark",
            {"cik": "0000000001", "route": "issuer", "accepted_at": datetime(2025, 1, 1, 10, 0, 0)},
        ),
        (
            "mark_delisted_route_completed",
            {
                "composite_figi": "BBG000000001",
                "cik": "0000000001",
                "route": "owner",
                "delisted_utc_snapshot": datetime(2025, 2, 1, 9, 0, 0),
                "last_seen_accepted_at": datetime(2025, 1, 31, 23, 59, 0),
            },
        ),
        (
            "write_log",
            {
                "run_id": "run-rollback-001",
                "route": "holding",
                "cik": "0000000001",
                "accession_no": "0000000001-25-000001",
                "stage": "extract",
                "level": "error",
                "message": "boom",
                "error_type": "CommitError",
            },
        ),
    ],
)
def test_mutating_methods_rollback_on_commit_failure(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    kwargs: dict,
):
    repo = PipelineRepository(db_session)
    calls = _install_failing_commit_with_rollback_spy(repo.session, monkeypatch)

    with pytest.raises(RuntimeError, match="commit failed"):
        getattr(repo, method_name)(**kwargs)

    assert calls["commit"] == 1
    assert calls["rollback"] == 1
