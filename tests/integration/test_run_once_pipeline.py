from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from typer.testing import CliRunner

import src.cli as cli
from src.cli import app
from src.db.base import Base
from src.db.models import (
    DelistedRouteCompletion,
    ExtractedFact,
    ExtractionEvidence,
    FilingDocument,
    PipelineLog,
    RouteWatermark,
)
from src.pipeline.services import EvidenceInput, FactInput
from src.pipeline.types import FilingRecord


runner = CliRunner()


def _as_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value

    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _build_session_factory() -> sessionmaker:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _patch_runtime(monkeypatch, session_factory: sessionmaker, securities: list[SimpleNamespace]) -> None:
    monkeypatch.setenv("PG_DSN", "sqlite+pysqlite:///:memory:")
    monkeypatch.setattr(cli, "get_session_factory", lambda settings: session_factory, raising=False)
    monkeypatch.setattr(cli, "_load_run_once_securities", lambda session: securities, raising=False)


class _RecordingRouter:
    def __init__(self, name: str, calls: list[tuple[str, str]]):
        self.name = name
        self._calls = calls

    def run(self, *, security: SimpleNamespace, context) -> None:
        del context
        self._calls.append((self.name, security.cik))


class _FailingOwnerRouter(_RecordingRouter):
    def __init__(self, calls: list[tuple[str, str]]):
        super().__init__("owner", calls)

    def run(self, *, security: SimpleNamespace, context) -> None:
        super().run(security=security, context=context)
        raise RuntimeError("owner router exploded")


def _bundle(*, accession_no: str, cik: str, accepted_at: datetime) -> cli.FilingBundle:
    filing = FilingRecord(
        accession_no=accession_no,
        cik=cik,
        ticker="ABC",
        form_type="10-K",
        filed_at=None,
        accepted_at=accepted_at,
        period_end=None,
        is_amendment=False,
        amendment_no=None,
    )
    return cli.FilingBundle(
        filing=filing,
        facts=[FactInput(field_name="total_revenue", value_numeric=123.0, confidence=0.9)],
        evidences=[
            EvidenceInput(
                field_name="total_revenue",
                locator_kind="span",
                source_span="Revenue table",
                raw_value="123",
                normalized_value="123.0",
            )
        ],
    )


def test_run_once_persists_filing_fact_evidence_and_watermark(monkeypatch):
    session_factory = _build_session_factory()
    calls: list[tuple[str, str]] = []

    class _IssuerRouter(_RecordingRouter):
        def __init__(self):
            super().__init__("issuer", calls)

    class _OwnerRouter(_RecordingRouter):
        def __init__(self):
            super().__init__("owner", calls)

    class _HoldingRouter(_RecordingRouter):
        def __init__(self):
            super().__init__("holding", calls)

    accepted_at = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    security = SimpleNamespace(
        cik="0000320193",
        composite_figi="BBG000000001",
        active=True,
        delisted_utc=None,
        filing_bundles_by_route={
            "issuer": [_bundle(accession_no="0000320193-25-000001", cik="0000320193", accepted_at=accepted_at)],
            "owner": [],
            "holding": [],
        },
    )

    _patch_runtime(monkeypatch, session_factory, [security])
    monkeypatch.setattr(cli, "IssuerRouter", _IssuerRouter, raising=False)
    monkeypatch.setattr(cli, "OwnerRouter", _OwnerRouter, raising=False)
    monkeypatch.setattr(cli, "HoldingRouter", _HoldingRouter, raising=False)

    result = runner.invoke(app, ["run-once"])

    assert result.exit_code == 0
    assert "route order: issuer -> owner -> holding" in result.stdout
    assert calls == [
        ("issuer", "0000320193"),
        ("owner", "0000320193"),
        ("holding", "0000320193"),
    ]

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(FilingDocument)) == 1
        assert session.scalar(select(func.count()).select_from(ExtractedFact)) == 1
        assert session.scalar(select(func.count()).select_from(ExtractionEvidence)) == 1

        persisted_log = session.scalar(
            select(PipelineLog).where(
                PipelineLog.route == "issuer",
                PipelineLog.stage == "persist",
                PipelineLog.level == "INFO",
                PipelineLog.message == "filing persisted",
            )
        )
        assert persisted_log is not None
        assert persisted_log.accession_no == "0000320193-25-000001"

        watermark = session.scalar(
            select(RouteWatermark).where(
                RouteWatermark.cik == "0000320193",
                RouteWatermark.route == "issuer",
            )
        )
        assert watermark is not None
        assert _as_naive_utc(watermark.last_accepted_at) == _as_naive_utc(accepted_at)


def test_run_once_rerun_is_idempotent_for_primary_outputs(monkeypatch):
    session_factory = _build_session_factory()

    accepted_at = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    security = SimpleNamespace(
        cik="0000789019",
        composite_figi="BBG000000002",
        active=True,
        delisted_utc=None,
        filing_bundles_by_route={
            "issuer": [_bundle(accession_no="0000789019-25-000001", cik="0000789019", accepted_at=accepted_at)],
            "owner": [],
            "holding": [],
        },
    )

    _patch_runtime(monkeypatch, session_factory, [security])

    first = runner.invoke(app, ["run-once"])
    second = runner.invoke(app, ["run-once"])

    assert first.exit_code == 0
    assert second.exit_code == 0

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(FilingDocument)) == 1
        assert session.scalar(select(func.count()).select_from(ExtractedFact)) == 1
        assert session.scalar(select(func.count()).select_from(ExtractionEvidence)) == 1


def test_run_once_logs_router_error_and_continues(monkeypatch):
    session_factory = _build_session_factory()
    calls: list[tuple[str, str]] = []

    class _IssuerRouter(_RecordingRouter):
        def __init__(self):
            super().__init__("issuer", calls)

    class _HoldingRouter(_RecordingRouter):
        def __init__(self):
            super().__init__("holding", calls)

    accepted_at = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    security = SimpleNamespace(
        cik="0001652044",
        composite_figi="BBG000000003",
        active=True,
        delisted_utc=None,
        filing_bundles_by_route={
            "issuer": [_bundle(accession_no="0001652044-25-000001", cik="0001652044", accepted_at=accepted_at)],
            "owner": [],
            "holding": [],
        },
    )

    _patch_runtime(monkeypatch, session_factory, [security])
    monkeypatch.setattr(cli, "IssuerRouter", _IssuerRouter, raising=False)
    monkeypatch.setattr(cli, "OwnerRouter", lambda: _FailingOwnerRouter(calls), raising=False)
    monkeypatch.setattr(cli, "HoldingRouter", _HoldingRouter, raising=False)

    result = runner.invoke(app, ["run-once"])

    assert result.exit_code == 0
    assert calls == [
        ("issuer", "0001652044"),
        ("owner", "0001652044"),
        ("holding", "0001652044"),
    ]

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(FilingDocument)) == 1

        owner_error_log = session.scalar(
            select(PipelineLog).where(
                PipelineLog.route == "owner",
                PipelineLog.stage == "extract",
                PipelineLog.level == "ERROR",
            )
        )
        assert owner_error_log is not None
        assert owner_error_log.message == "router failed"
        assert owner_error_log.error_type == "RuntimeError"
        assert owner_error_log.cik == "0001652044"

        issuer_success_log = session.scalar(
            select(PipelineLog).where(
                PipelineLog.route == "issuer",
                PipelineLog.stage == "persist",
                PipelineLog.level == "INFO",
            )
        )
        assert issuer_success_log is not None


def test_run_once_skips_completed_delisted_route_until_snapshot_changes(monkeypatch):
    session_factory = _build_session_factory()
    cutoff = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    calls: list[tuple[str, str]] = []

    class _IssuerRouter(_RecordingRouter):
        def __init__(self):
            super().__init__("issuer", calls)

    class _OwnerRouter(_RecordingRouter):
        def __init__(self):
            super().__init__("owner", calls)

    class _HoldingRouter(_RecordingRouter):
        def __init__(self):
            super().__init__("holding", calls)

    security = SimpleNamespace(
        cik="0001067983",
        composite_figi="BBG000000004",
        active=False,
        delisted_utc=cutoff,
        filing_bundles_by_route={
            "issuer": [_bundle(accession_no="0001067983-25-000001", cik="0001067983", accepted_at=cutoff)],
            "owner": [],
            "holding": [],
        },
    )

    with session_factory() as session:
        session.add(
            DelistedRouteCompletion(
                composite_figi="BBG000000004",
                cik="0001067983",
                route="issuer",
                delisted_utc_snapshot=cutoff,
                last_seen_accepted_at=cutoff,
                is_completed=True,
                completed_at=cutoff,
                updated_at=cutoff,
            )
        )
        session.commit()

    _patch_runtime(monkeypatch, session_factory, [security])
    monkeypatch.setattr(cli, "IssuerRouter", _IssuerRouter, raising=False)
    monkeypatch.setattr(cli, "OwnerRouter", _OwnerRouter, raising=False)
    monkeypatch.setattr(cli, "HoldingRouter", _HoldingRouter, raising=False)

    first = runner.invoke(app, ["run-once"])
    assert first.exit_code == 0

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(FilingDocument)) == 0
        issuer_wm = session.scalar(
            select(RouteWatermark).where(
                RouteWatermark.cik == "0001067983",
                RouteWatermark.route == "issuer",
            )
        )
        assert issuer_wm is None

    security.delisted_utc = cutoff + timedelta(days=1)

    second = runner.invoke(app, ["run-once"])
    assert second.exit_code == 0

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(FilingDocument)) == 1
        issuer_wm = session.scalar(
            select(RouteWatermark).where(
                RouteWatermark.cik == "0001067983",
                RouteWatermark.route == "issuer",
            )
        )
        assert issuer_wm is not None
        assert _as_naive_utc(issuer_wm.last_accepted_at) == _as_naive_utc(cutoff)


def test_run_once_invalidates_delisted_completion_when_security_reactivates(monkeypatch):
    session_factory = _build_session_factory()
    now = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)

    security = SimpleNamespace(
        cik="0001467373",
        composite_figi="BBG000000005",
        active=True,
        delisted_utc=None,
        filing_bundles_by_route={"issuer": [], "owner": [], "holding": []},
    )

    with session_factory() as session:
        session.add(
            DelistedRouteCompletion(
                composite_figi="BBG000000005",
                cik="0001467373",
                route="issuer",
                delisted_utc_snapshot=now,
                last_seen_accepted_at=now,
                is_completed=True,
                completed_at=now,
                updated_at=now,
            )
        )
        session.commit()

    _patch_runtime(monkeypatch, session_factory, [security])

    result = runner.invoke(app, ["run-once"])

    assert result.exit_code == 0

    with session_factory() as session:
        completion = session.scalar(
            select(DelistedRouteCompletion).where(
                DelistedRouteCompletion.composite_figi == "BBG000000005",
                DelistedRouteCompletion.cik == "0001467373",
                DelistedRouteCompletion.route == "issuer",
            )
        )
        assert completion is not None
        assert completion.is_completed is False
        assert completion.delisted_utc_snapshot is None
        assert completion.last_seen_accepted_at is None
        assert completion.completed_at is None


def test_run_once_uses_start_date_when_watermark_missing(monkeypatch):
    session_factory = _build_session_factory()
    security = SimpleNamespace(
        cik="0001467373",
        composite_figi="BBG000000005",
        active=True,
        delisted_utc=None,
        filing_bundles_by_route={},
    )

    seen_starts: list[tuple[str, datetime]] = []

    def _capture_load_route_filing_bundles(*, security, route, start_accepted_at):
        del security
        seen_starts.append((route, start_accepted_at))
        return []

    _patch_runtime(monkeypatch, session_factory, [security])
    monkeypatch.setenv("START_DATE", "2016-02-03")
    monkeypatch.setattr(cli, "_load_route_filing_bundles", _capture_load_route_filing_bundles, raising=False)

    result = runner.invoke(app, ["run-once"])

    assert result.exit_code == 0
    expected = datetime(2016, 2, 3, 0, 0, tzinfo=timezone.utc)
    assert [route for route, _ in seen_starts] == ["issuer", "owner", "holding"]
    assert all(_as_naive_utc(start) == _as_naive_utc(expected) for _, start in seen_starts)
