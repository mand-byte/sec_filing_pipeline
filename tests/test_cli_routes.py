from __future__ import annotations

from datetime import date
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import src.cli as cli_module
from src.db.base import Base
from src.db.models import FilingAttempt, PipelineLog, RouteWatermark
from src.pipeline.route_runtime import RouteProcessor
from src.pipeline.route_runtime import FilingBundle
from src.pipeline.routers.holding import HoldingRouter
from src.pipeline.routers.issuer import IssuerRouter
from src.pipeline.routers.owner import OwnerRouter
from src.pipeline.services import EvidenceInput, FactInput
from src.pipeline.types import FilingRecord


runner = CliRunner()


def _session_factory(db_path: str):
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False)


def _filing(accession_no: str, accepted_at: datetime) -> FilingRecord:
    return FilingRecord(
        accession_no=accession_no,
        cik="0000789019",
        ticker="MSFT",
        form_type="4",
        filed_at=None,
        accepted_at=accepted_at,
        period_end=None,
        is_amendment=False,
        amendment_no=None,
    )


def test_run_once_route_option_dispatches_selected_route(monkeypatch) -> None:
    calls: list[tuple[str | None, Path | None]] = []

    def fake_run_once_pipeline(*, route: str | None = None, artifacts_dir: Path | None = None) -> None:
        calls.append((route, artifacts_dir))

    monkeypatch.setattr(cli_module, "_run_once_pipeline", fake_run_once_pipeline)

    result = runner.invoke(cli_module.app, ["run-once", "--route", "owner"])

    assert result.exit_code == 0
    assert calls == [("owner", None)]


def test_run_owner_command_dispatches_owner_route(monkeypatch) -> None:
    calls: list[tuple[str | None, Path | None]] = []

    def fake_run_once_pipeline(*, route: str | None = None, artifacts_dir: Path | None = None) -> None:
        calls.append((route, artifacts_dir))

    monkeypatch.setattr(cli_module, "_run_once_pipeline", fake_run_once_pipeline)

    result = runner.invoke(cli_module.app, ["run-owner"])

    assert result.exit_code == 0
    assert calls == [("owner", None)]


def test_run_once_rejects_unknown_route() -> None:
    result = runner.invoke(cli_module.app, ["run-once", "--route", "bad-route"])

    assert result.exit_code != 0
    assert "route must be one of: issuer, owner, holding" in result.output


def test_backfill_command_dispatches_selected_options(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_backfill_pipeline(
        *,
        route: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        tickers: tuple[str, ...] = (),
        ciks: tuple[str, ...] = (),
        limit: int | None = None,
        ignore_existing_watermarks: bool = True,
        artifacts_dir: Path | None = None,
    ) -> None:
        captured.update(
            {
                "route": route,
                "start_date": start_date,
                "end_date": end_date,
                "tickers": tickers,
                "ciks": ciks,
                "limit": limit,
                "ignore_existing_watermarks": ignore_existing_watermarks,
                "artifacts_dir": artifacts_dir,
            }
        )

    monkeypatch.setattr(cli_module, "_run_backfill_pipeline", fake_run_backfill_pipeline)

    result = runner.invoke(
        cli_module.app,
        [
            "backfill",
            "--route",
            "issuer",
            "--start-date",
            "2024-01-15",
            "--end-date",
            "2024-12-31",
            "--ticker",
            "msft",
            "--ticker",
            "aapl",
            "--cik",
            "0000789019",
            "--limit",
            "2",
            "--artifacts",
            "/tmp/runtime-artifacts",
            "--respect-watermarks",
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "route": "issuer",
        "start_date": date(2024, 1, 15),
        "end_date": date(2024, 12, 31),
        "tickers": ("MSFT", "AAPL"),
        "ciks": ("0000789019",),
        "limit": 2,
        "ignore_existing_watermarks": False,
        "artifacts_dir": Path("/tmp/runtime-artifacts"),
    }


def test_backfill_cohort_dispatches_named_seed_routes(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_run_backfill_pipeline(
        *,
        route: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        tickers: tuple[str, ...] = (),
        ciks: tuple[str, ...] = (),
        limit: int | None = None,
        ignore_existing_watermarks: bool = True,
        artifacts_dir: Path | None = None,
    ) -> str:
        calls.append(
            {
                "route": route,
                "start_date": start_date,
                "end_date": end_date,
                "tickers": tickers,
                "ciks": ciks,
                "limit": limit,
                "ignore_existing_watermarks": ignore_existing_watermarks,
                "artifacts_dir": artifacts_dir,
            }
        )
        return f"{route}-run-id"

    monkeypatch.setattr(cli_module, "_run_backfill_pipeline", fake_run_backfill_pipeline)
    monkeypatch.setattr(
        cli_module,
        "Settings",
        lambda: SimpleNamespace(write_offline_artifacts=True, offline_artifacts_dir=Path("/tmp/cohorts")),
    )
    monkeypatch.setattr(cli_module, "_write_backfill_cohort_manifest", lambda **kwargs: Path("/tmp/cohorts/manifest.json"))

    result = runner.invoke(
        cli_module.app,
        [
            "backfill-cohort",
            "--cohort",
            "phase1_deterministic",
            "--start-date",
            "2024-01-15",
            "--end-date",
            "2024-12-31",
            "--limit",
            "3",
            "--artifacts",
            "/tmp/cohorts",
        ],
    )

    assert result.exit_code == 0
    assert "backfill cohort: phase1_deterministic" in result.stdout
    assert "cohort manifest: /tmp/cohorts/manifest.json" in result.stdout
    assert [call["route"] for call in calls] == ["issuer", "owner", "holding"]
    assert all(call["start_date"] == date(2024, 1, 15) for call in calls)
    assert all(call["end_date"] == date(2024, 12, 31) for call in calls)
    assert all(call["tickers"] == ("MSFT", "AAPL", "AMZN", "NVDA", "TSLA") for call in calls)
    assert all(call["limit"] == 3 for call in calls)
    assert all(call["artifacts_dir"] == Path("/tmp/cohorts") for call in calls)


def test_backfill_cohort_accepts_route_override(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_run_backfill_pipeline(
        *,
        route: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        tickers: tuple[str, ...] = (),
        ciks: tuple[str, ...] = (),
        limit: int | None = None,
        ignore_existing_watermarks: bool = True,
        artifacts_dir: Path | None = None,
    ) -> str:
        calls.append({"route": route, "tickers": tickers, "end_date": end_date, "artifacts_dir": artifacts_dir})
        return "issuer-run-id"

    monkeypatch.setattr(cli_module, "_run_backfill_pipeline", fake_run_backfill_pipeline)
    monkeypatch.setattr(
        cli_module,
        "Settings",
        lambda: SimpleNamespace(write_offline_artifacts=False, offline_artifacts_dir=Path("/tmp/cohorts")),
    )

    result = runner.invoke(
        cli_module.app,
        [
            "backfill-cohort",
            "--cohort",
            "phase2_financial",
            "--route",
            "issuer",
        ],
    )

    assert result.exit_code == 0
    assert calls == [
        {
            "route": "issuer",
            "tickers": ("JPM", "BAC", "WFC", "GS", "MS", "C", "JEF", "LAZ"),
            "end_date": None,
            "artifacts_dir": Path("/tmp/cohorts"),
        }
    ]


def test_schedule_route_option_builds_filtered_tick(monkeypatch) -> None:
    captured: dict[str, object] = {}
    calls: list[tuple[str | None, Path | None]] = []

    class FakeScheduler:
        def start(self) -> None:
            captured["started"] = True

    def fake_run_once_pipeline(*, route: str | None = None, artifacts_dir: Path | None = None) -> None:
        calls.append((route, artifacts_dir))

    def fake_build_blocking_scheduler(*, interval_minutes: int, tick_callable: object) -> FakeScheduler:
        captured["interval_minutes"] = interval_minutes
        captured["tick_callable"] = tick_callable
        return FakeScheduler()

    monkeypatch.setattr(
        cli_module,
        "Settings",
        lambda: SimpleNamespace(scheduler_interval_minutes=7),
    )
    monkeypatch.setattr(cli_module, "_run_once_pipeline", fake_run_once_pipeline)
    monkeypatch.setattr(cli_module, "build_blocking_scheduler", fake_build_blocking_scheduler)

    result = runner.invoke(cli_module.app, ["schedule", "--route", "holding"])

    assert result.exit_code == 0
    assert captured["interval_minutes"] == 7
    assert captured["started"] is True

    tick_callable = captured["tick_callable"]
    assert callable(tick_callable)
    tick_callable()
    assert calls == [("holding", None)]


def test_cli_no_args_defaults_to_schedule_loop(monkeypatch) -> None:
    calls: list[tuple[str | None, Path | None]] = []

    def fake_schedule(route: str | None = None, artifacts: Path | None = None) -> None:
        calls.append((route, artifacts))

    monkeypatch.setattr(cli_module, "schedule", fake_schedule)

    result = runner.invoke(cli_module.app, [])

    assert result.exit_code == 0
    assert calls == [(None, None)]


def test_schedule_command_tick_runs_db_backed_pipeline_and_writes_artifacts(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}
    factory = _session_factory(str(tmp_path / "schedule_cli.db"))
    accepted_at = datetime(2024, 5, 9, tzinfo=timezone.utc)
    bundle = FilingBundle(
        filing=_filing("0000000000-24-000103", accepted_at),
        facts=[
            FactInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                value_numeric=175.0,
                confidence=0.99,
            )
        ],
        evidences=[
            EvidenceInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                locator_kind="obj",
                source_span="transactions[0].shares",
                raw_value="175",
                normalized_value="175.0",
            )
        ],
    )
    security = SimpleNamespace(
        cik="0000789019",
        ticker="MSFT",
        active=True,
        composite_figi="FIGI1",
        delisted_utc=None,
        filing_bundles_by_route={"issuer": [bundle]},
    )

    class FakeScheduler:
        def __init__(self, *, tick_callable: object):
            self._tick_callable = tick_callable

        def start(self) -> None:
            captured["started"] = True
            self._tick_callable()

    def fake_build_blocking_scheduler(*, interval_minutes: int, tick_callable: object) -> FakeScheduler:
        captured["interval_minutes"] = interval_minutes
        captured["tick_callable"] = tick_callable
        return FakeScheduler(tick_callable=tick_callable)

    monkeypatch.setattr(
        cli_module,
        "Settings",
        lambda: SimpleNamespace(
            scheduler_interval_minutes=7,
            start_date=date(2024, 1, 1),
            write_offline_artifacts=True,
            offline_artifacts_dir=tmp_path / "artifacts",
        ),
    )
    monkeypatch.setattr(cli_module, "get_session_factory", lambda settings: factory)
    monkeypatch.setattr(cli_module, "_load_run_once_securities", lambda session, settings: [security])
    monkeypatch.setattr(cli_module, "build_blocking_scheduler", fake_build_blocking_scheduler)
    monkeypatch.setattr(cli_module, "make_run_id", lambda: "schedule-cli-db-backed")

    result = runner.invoke(cli_module.app, ["schedule", "--route", "issuer"])

    assert result.exit_code == 0
    assert captured["interval_minutes"] == 7
    assert captured["started"] is True

    run_dir = tmp_path / "artifacts" / "schedule-cli-db-backed"
    with factory() as session:
        attempts = session.query(FilingAttempt).order_by(FilingAttempt.id.asc()).all()
        logs = session.query(PipelineLog).order_by(PipelineLog.id.asc()).all()
        watermark = session.query(RouteWatermark).one()

    assert (run_dir / "summary.json").exists()
    assert [attempt.status for attempt in attempts] == ["completed"]
    assert [log.message for log in logs] == [
        "filing persisted",
        "route processed: eligible=1 persisted=1 failed=0 skipped_before_watermark=0 skipped_ineligible=0",
    ]
    assert watermark.last_accepted_at == accepted_at.replace(tzinfo=None)


def test_backfill_command_replays_before_existing_watermark_and_preserves_incremental_skip(tmp_path, monkeypatch) -> None:
    factory = _session_factory(str(tmp_path / "backfill_cli.db"))
    older_accepted_at = datetime(2024, 5, 3, tzinfo=timezone.utc)
    older_bundle = FilingBundle(
        filing=_filing("0000000000-24-000103B", older_accepted_at),
        facts=[
            FactInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                value_numeric=90.0,
                confidence=0.99,
            )
        ],
        evidences=[
            EvidenceInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                locator_kind="obj",
                source_span="transactions[0].shares",
                raw_value="90",
                normalized_value="90.0",
            )
        ],
    )
    security = SimpleNamespace(
        cik="0000789019",
        ticker="MSFT",
        active=True,
        composite_figi="FIGI1",
        delisted_utc=None,
        filing_bundles_by_route={"issuer": [older_bundle]},
    )

    monkeypatch.setattr(
        cli_module,
        "Settings",
        lambda: SimpleNamespace(
            start_date=date(2024, 1, 1),
            write_offline_artifacts=True,
            offline_artifacts_dir=tmp_path / "artifacts",
        ),
    )
    monkeypatch.setattr(cli_module, "get_session_factory", lambda settings: factory)
    monkeypatch.setattr(cli_module, "_load_run_once_securities", lambda session, settings: [security])

    run_ids = iter(["backfill-cli-db-backed", "run-once-after-backfill"])
    monkeypatch.setattr(cli_module, "make_run_id", lambda: next(run_ids))

    with factory() as session:
        session.add(
            RouteWatermark(
                cik="0000789019",
                route="issuer",
                last_accepted_at=datetime(2024, 5, 10, tzinfo=timezone.utc),
                updated_at=datetime(2024, 5, 10, tzinfo=timezone.utc),
            )
        )
        session.commit()

    backfill_result = runner.invoke(
        cli_module.app,
        ["backfill", "--route", "issuer", "--ticker", "MSFT", "--start-date", "2024-01-01"],
    )
    assert backfill_result.exit_code == 0
    assert "backfill mode: start_date=2024-01-01 ignore_existing_watermarks=True" in backfill_result.stdout

    run_once_result = runner.invoke(cli_module.app, ["run-once", "--route", "issuer"])
    assert run_once_result.exit_code == 0

    backfill_run_dir = tmp_path / "artifacts" / "backfill-cli-db-backed"
    run_once_dir = tmp_path / "artifacts" / "run-once-after-backfill"
    backfill_manifest = json.loads((backfill_run_dir / "manifest.json").read_text(encoding="utf-8"))
    run_once_summary = json.loads((run_once_dir / "summary.json").read_text(encoding="utf-8"))

    with factory() as session:
        attempts = session.query(FilingAttempt).order_by(FilingAttempt.id.asc()).all()
        logs = session.query(PipelineLog).order_by(PipelineLog.id.asc()).all()
        watermark = session.query(RouteWatermark).one()

    assert backfill_manifest["mode"] == "backfill"
    assert backfill_manifest["ignore_existing_watermarks"] is True
    assert backfill_manifest["filters"]["tickers"] == ["MSFT"]
    assert backfill_manifest["selected_security_count"] == 1
    assert [attempt.run_id for attempt in attempts] == ["backfill-cli-db-backed"]
    assert [attempt.status for attempt in attempts] == ["completed"]
    assert [log.message for log in logs] == [
        "filing persisted",
        "route processed: eligible=1 persisted=1 failed=0 skipped_before_watermark=0 skipped_ineligible=0",
        "route processed: eligible=0 persisted=0 failed=0 skipped_before_watermark=1 skipped_ineligible=0",
    ]
    assert run_once_summary["coverage"]["filing_attempts"]["total"] == 0
    assert watermark.last_accepted_at == datetime(2024, 5, 10, tzinfo=timezone.utc).replace(tzinfo=None)


def test_schedule_command_tick_preserves_failure_isolation_and_watermark(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}
    factory = _session_factory(str(tmp_path / "schedule_cli_failure.db"))
    first_accepted_at = datetime(2024, 5, 10, tzinfo=timezone.utc)
    second_accepted_at = datetime(2024, 5, 11, tzinfo=timezone.utc)
    valid_bundle = FilingBundle(
        filing=_filing("0000000000-24-000104", first_accepted_at),
        facts=[
            FactInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                value_numeric=200.0,
                confidence=0.99,
            )
        ],
        evidences=[
            EvidenceInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                locator_kind="obj",
                source_span="transactions[0].shares",
                raw_value="200",
                normalized_value="200.0",
            )
        ],
    )
    failing_bundle = FilingBundle(
        filing=_filing("0000000000-24-000105", second_accepted_at),
        facts=[
            FactInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                value_numeric=250.0,
                confidence=0.99,
            )
        ],
        evidences=[],
    )
    security = SimpleNamespace(
        cik="0000789019",
        ticker="MSFT",
        active=True,
        composite_figi="FIGI1",
        delisted_utc=None,
        filing_bundles_by_route={"issuer": [valid_bundle, failing_bundle]},
    )

    class FakeScheduler:
        def __init__(self, *, tick_callable: object):
            self._tick_callable = tick_callable

        def start(self) -> None:
            captured["started"] = True
            self._tick_callable()

    def fake_build_blocking_scheduler(*, interval_minutes: int, tick_callable: object) -> FakeScheduler:
        captured["interval_minutes"] = interval_minutes
        return FakeScheduler(tick_callable=tick_callable)

    monkeypatch.setattr(
        cli_module,
        "Settings",
        lambda: SimpleNamespace(
            scheduler_interval_minutes=9,
            start_date=date(2024, 1, 1),
            write_offline_artifacts=True,
            offline_artifacts_dir=tmp_path / "artifacts",
        ),
    )
    monkeypatch.setattr(cli_module, "get_session_factory", lambda settings: factory)
    monkeypatch.setattr(cli_module, "_load_run_once_securities", lambda session, settings: [security])
    monkeypatch.setattr(cli_module, "build_blocking_scheduler", fake_build_blocking_scheduler)
    monkeypatch.setattr(cli_module, "make_run_id", lambda: "schedule-cli-failure-db-backed")

    result = runner.invoke(cli_module.app, ["schedule", "--route", "issuer"])

    assert result.exit_code == 0
    assert captured["interval_minutes"] == 9
    assert captured["started"] is True

    run_dir = tmp_path / "artifacts" / "schedule-cli-failure-db-backed"
    with factory() as session:
        attempts = session.query(FilingAttempt).order_by(FilingAttempt.id.asc()).all()
        logs = session.query(PipelineLog).order_by(PipelineLog.id.asc()).all()
        watermark = session.query(RouteWatermark).one()

    assert (run_dir / "summary.json").exists()
    assert [attempt.status for attempt in attempts] == ["completed", "failed"]
    assert [log.message for log in logs] == [
        "filing persisted",
        "filing persistence failed",
        "route processed: eligible=2 persisted=1 failed=1 skipped_before_watermark=0 skipped_ineligible=0",
    ]
    assert watermark.last_accepted_at == first_accepted_at.replace(tzinfo=None)


def test_route_routers_delegate_to_shared_processor() -> None:
    calls: list[tuple[str, str, object]] = []

    class FakeProcessor:
        def run(self, *, security: object, route: str, run_id: str) -> None:
            calls.append((route, run_id, security))

    security = object()
    context = {"run_id": "run-123", "route": "ignored", "repo": object()}

    for router in (IssuerRouter(FakeProcessor()), OwnerRouter(FakeProcessor()), HoldingRouter(FakeProcessor())):
        router.run(security=security, context=context)

    assert calls == [
        ("issuer", "run-123", security),
        ("owner", "run-123", security),
        ("holding", "run-123", security),
    ]


def test_run_once_pipeline_uses_run_single_tick_as_only_execution_backbone(monkeypatch) -> None:
    tick_calls: list[dict[str, object]] = []
    processor_calls: list[tuple[str, str, object]] = []

    class FakeSessionContext:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    class FakeSessionFactory:
        def __call__(self) -> FakeSessionContext:
            return FakeSessionContext()

    def fake_run_single_tick(*, run_id: str, securities: object, routers: object, repo: object) -> None:
        tick_calls.append(
            {
                "run_id": run_id,
                "securities": list(securities),
                "routes": [router.name for router in routers],
                "repo": repo,
            }
        )

    def fake_processor_run(self: RouteProcessor, *, security: object, route: str, run_id: str) -> None:
        processor_calls.append((route, run_id, security))

    monkeypatch.setattr(
        cli_module,
        "Settings",
        lambda: SimpleNamespace(
            start_date=date(2024, 1, 1),
            write_offline_artifacts=False,
        ),
    )
    monkeypatch.setattr(cli_module, "get_session_factory", lambda settings: FakeSessionFactory())
    monkeypatch.setattr(
        cli_module,
        "_load_run_once_securities",
        lambda session, settings: [SimpleNamespace(cik="0000789019", active=True, composite_figi="FIGI1", delisted_utc=None)],
    )
    monkeypatch.setattr(cli_module, "run_single_tick", fake_run_single_tick)
    monkeypatch.setattr(RouteProcessor, "run", fake_processor_run)

    cli_module._run_once_pipeline(route="issuer")

    assert len(tick_calls) == 1
    assert tick_calls[0]["routes"] == ["issuer"]
    assert processor_calls == []
