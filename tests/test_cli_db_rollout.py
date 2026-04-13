from __future__ import annotations

import json
from types import SimpleNamespace

from typer.testing import CliRunner

import src.cli as cli_module
from src.db.rollout import DbInitResult, RolloutApplyResult


runner = CliRunner()


def test_cli_db_rollout_assets_lists_checked_in_sql_and_readme() -> None:
    result = runner.invoke(cli_module.app, ["db-rollout-assets"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["readme_path"].endswith("src/db/migrations/README.md")
    assert payload["migrations"] == [
        {
            "name": "20260411_add_evidence_locator_and_filing_attempt.sql",
            "path": payload["migrations"][0]["path"],
            "statement_count": 10,
        }
    ]
    assert payload["migrations"][0]["path"].endswith(
        "src/db/migrations/20260411_add_evidence_locator_and_filing_attempt.sql"
    )


def test_cli_db_rollout_apply_dry_run_outputs_plan(monkeypatch) -> None:
    monkeypatch.setattr(cli_module, "Settings", lambda: (_ for _ in ()).throw(AssertionError("Settings should not be used for dry-run")))
    monkeypatch.setattr(cli_module, "build_engine", lambda settings: (_ for _ in ()).throw(AssertionError("Engine should not be built for dry-run")))

    result = runner.invoke(cli_module.app, ["db-rollout-apply", "--dry-run"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["applied"] is False
    assert payload["dry_run"] is True
    assert payload["dialect"] == "unresolved"
    assert payload["statement_count"] == 10


def test_cli_db_rollout_apply_executes_against_configured_engine(monkeypatch) -> None:
    engine = SimpleNamespace()
    monkeypatch.setattr(cli_module, "Settings", lambda: object())
    monkeypatch.setattr(cli_module, "build_engine", lambda settings: engine)

    captured: dict[str, object] = {}

    def fake_apply_rollout_assets(*, engine, dry_run: bool) -> object:
        captured["engine"] = engine
        captured["dry_run"] = dry_run
        return RolloutApplyResult(
            applied=True,
            dry_run=False,
            dialect="postgresql",
            migration_count=1,
            statement_count=10,
            migrations=[],
        )

    monkeypatch.setattr(cli_module, "apply_rollout_assets", fake_apply_rollout_assets)

    result = runner.invoke(cli_module.app, ["db-rollout-apply"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert captured["engine"] is engine
    assert captured["dry_run"] is False
    assert payload["applied"] is True


def test_cli_db_init_bootstraps_base_schema(monkeypatch) -> None:
    engine = SimpleNamespace()
    monkeypatch.setattr(cli_module, "Settings", lambda: object())
    monkeypatch.setattr(cli_module, "build_engine", lambda settings: engine)

    captured: dict[str, object] = {}

    def fake_init_database_schema(*, engine) -> object:
        captured["engine"] = engine
        return DbInitResult(
            applied=True,
            dialect="sqlite",
            table_count=3,
            tables=["filing_document", "extracted_fact", "pipeline_log"],
        )

    monkeypatch.setattr(cli_module, "init_database_schema", fake_init_database_schema)

    result = runner.invoke(cli_module.app, ["db-init"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert captured["engine"] is engine
    assert payload["applied"] is True
    assert payload["table_count"] == 3


def test_ensure_runtime_schema_ready_bootstraps_and_applies_rollout_once(monkeypatch) -> None:
    cli_module._SCHEMA_READY_DSNS.clear()
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    settings = SimpleNamespace(pg_dsn="postgresql+psycopg://user:pass@db/sec_filing")
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(cli_module, "build_engine", lambda provided_settings: engine)
    monkeypatch.setattr(
        cli_module,
        "init_database_schema",
        lambda *, engine: calls.append(("init", engine)) or DbInitResult(
            applied=True,
            dialect="postgresql",
            table_count=18,
            tables=[],
        ),
    )
    monkeypatch.setattr(
        cli_module,
        "apply_rollout_assets",
        lambda *, engine, dry_run: calls.append(("rollout", engine)) or RolloutApplyResult(
            applied=True,
            dry_run=False,
            dialect="postgresql",
            migration_count=1,
            statement_count=10,
            migrations=[],
        ),
    )

    cli_module._ensure_runtime_schema_ready(settings)
    cli_module._ensure_runtime_schema_ready(settings)

    assert calls == [("init", engine), ("rollout", engine)]


def test_ensure_runtime_schema_ready_noops_without_pg_dsn(monkeypatch) -> None:
    cli_module._SCHEMA_READY_DSNS.clear()
    settings = SimpleNamespace()
    monkeypatch.setattr(cli_module, "build_engine", lambda provided_settings: (_ for _ in ()).throw(AssertionError("should not build engine")))

    cli_module._ensure_runtime_schema_ready(settings)
