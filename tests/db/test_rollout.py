from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.db.rollout import (
    apply_rollout_assets,
    describe_rollout_assets,
    dry_run_rollout_result,
    migration_asset_paths,
    migration_readme_path,
    migration_sql,
    rollout_plan,
    split_sql_statements,
)


def test_rollout_assets_include_checked_in_migration_and_readme() -> None:
    payload = describe_rollout_assets()

    assert migration_readme_path().name == "README.md"
    assert any(path.name == "20260411_add_evidence_locator_and_filing_attempt.sql" for path in migration_asset_paths())
    assert payload["readme_path"].endswith("src/db/migrations/README.md")
    assert "safe on existing databases" in payload["instructions"]
    assert payload["migrations"] == [
        {
            "name": "20260411_add_evidence_locator_and_filing_attempt.sql",
            "path": str(migration_asset_paths()[0]),
            "statement_count": 10,
        }
    ]


def test_split_sql_statements_returns_individual_rollout_commands() -> None:
    statements = split_sql_statements(migration_sql(migration_asset_paths()[0]))

    assert len(statements) == 10
    assert statements[0].startswith("-- Schema rollout")
    assert statements[-1].startswith("CREATE INDEX IF NOT EXISTS ix_filing_attempt_accession_no")


def test_rollout_plan_includes_statement_counts() -> None:
    assert rollout_plan() == [
        {
            "name": "20260411_add_evidence_locator_and_filing_attempt.sql",
            "path": str(migration_asset_paths()[0]),
            "statement_count": 10,
        }
    ]


def test_dry_run_rollout_result_does_not_require_engine() -> None:
    result = dry_run_rollout_result()

    assert result.applied is False
    assert result.dry_run is True
    assert result.dialect == "unresolved"
    assert result.statement_count == 10


def test_apply_rollout_assets_executes_each_statement_in_order() -> None:
    executed: list[str] = []

    class FakeConnection:
        def exec_driver_sql(self, statement: str) -> None:
            executed.append(statement)

    class FakeBegin:
        def __enter__(self) -> FakeConnection:
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    class FakeEngine:
        dialect = SimpleNamespace(name="postgresql")

        def begin(self) -> FakeBegin:
            return FakeBegin()

    result = apply_rollout_assets(engine=FakeEngine(), dry_run=False)

    assert result.applied is True
    assert result.dry_run is False
    assert result.statement_count == 10
    assert len(executed) == 10
    assert executed[0].startswith("-- Schema rollout")
    assert executed[-1].startswith("CREATE INDEX IF NOT EXISTS ix_filing_attempt_accession_no")


def test_apply_rollout_assets_rejects_non_postgresql_engine() -> None:
    class FakeEngine:
        dialect = SimpleNamespace(name="sqlite")

    with pytest.raises(RuntimeError, match="requires PostgreSQL engine"):
        apply_rollout_assets(engine=FakeEngine(), dry_run=False)
