from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from typer.testing import CliRunner

import src.cli as cli_module
from src.pipeline.route_runtime import RouteProcessor
from src.pipeline.routers.holding import HoldingRouter
from src.pipeline.routers.issuer import IssuerRouter
from src.pipeline.routers.owner import OwnerRouter


runner = CliRunner()


def test_run_once_route_option_dispatches_selected_route(monkeypatch) -> None:
    calls: list[str | None] = []

    def fake_run_once_pipeline(*, route: str | None = None) -> None:
        calls.append(route)

    monkeypatch.setattr(cli_module, "_run_once_pipeline", fake_run_once_pipeline)

    result = runner.invoke(cli_module.app, ["run-once", "--route", "owner"])

    assert result.exit_code == 0
    assert calls == ["owner"]


def test_run_owner_command_dispatches_owner_route(monkeypatch) -> None:
    calls: list[str | None] = []

    def fake_run_once_pipeline(*, route: str | None = None) -> None:
        calls.append(route)

    monkeypatch.setattr(cli_module, "_run_once_pipeline", fake_run_once_pipeline)

    result = runner.invoke(cli_module.app, ["run-owner"])

    assert result.exit_code == 0
    assert calls == ["owner"]


def test_run_once_rejects_unknown_route() -> None:
    result = runner.invoke(cli_module.app, ["run-once", "--route", "bad-route"])

    assert result.exit_code != 0
    assert "route must be one of: issuer, owner, holding" in result.output


def test_schedule_route_option_builds_filtered_tick(monkeypatch) -> None:
    captured: dict[str, object] = {}
    calls: list[str | None] = []

    class FakeScheduler:
        def start(self) -> None:
            captured["started"] = True

    def fake_run_once_pipeline(*, route: str | None = None) -> None:
        calls.append(route)

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
    assert calls == ["holding"]


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
