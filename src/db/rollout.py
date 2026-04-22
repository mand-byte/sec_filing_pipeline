from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlalchemy import inspect

from src.db.base import Base
from src.db.models import AUDIT_TABLE_NAMES, PRODUCTION_TABLE_NAMES


def migration_dir() -> Path:
    """Return the checked-in directory that holds rollout SQL assets."""
    return Path(__file__).resolve().parent / "migrations"


def migration_readme_path() -> Path:
    """Return the README that documents the rollout assets."""
    return migration_dir() / "README.md"


def migration_asset_paths() -> list[Path]:
    """List migration SQL assets in deterministic filename order."""
    return sorted(
        path
        for path in migration_dir().glob("*.sql")
        if path.is_file()
    )


def migration_sql(path: Path) -> str:
    """Read one migration SQL asset from disk."""
    return path.read_text(encoding="utf-8")


def split_sql_statements(sql_text: str) -> list[str]:
    """Split a SQL script into executable statements while respecting quotes."""
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_double_quote = False

    for char in sql_text:
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote

        if char == ";" and not in_single_quote and not in_double_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            continue

        current.append(char)

    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)

    return statements


@dataclass(frozen=True)
class RolloutApplyResult:
    applied: bool
    dry_run: bool
    dialect: str
    migration_count: int
    statement_count: int
    migrations: list[dict[str, Any]]


@dataclass(frozen=True)
class DbInitResult:
    applied: bool
    dialect: str
    table_count: int
    tables: list[str]


def _dialect_name(engine: Engine) -> str:
    """Return the SQLAlchemy dialect name for an engine."""
    dialect = getattr(engine, "dialect", None)
    name = getattr(dialect, "name", None)
    return str(name or "unknown")


def _require_supported_dialect(engine: Engine) -> str:
    """Require a PostgreSQL engine for rollout-asset execution."""
    dialect_name = _dialect_name(engine)
    if dialect_name != "postgresql":
        raise RuntimeError(f"db rollout apply requires PostgreSQL engine, got: {dialect_name}")
    return dialect_name


def rollout_plan() -> list[dict[str, Any]]:
    """Describe the rollout assets and statement counts without executing them."""
    plan: list[dict[str, Any]] = []
    for path in migration_asset_paths():
        statements = split_sql_statements(migration_sql(path))
        plan.append(
            {
                "name": path.name,
                "path": str(path),
                "statement_count": len(statements),
            }
        )
    return plan


def dry_run_rollout_result() -> RolloutApplyResult:
    """Build the dry-run payload for DB rollout assets."""
    plan = rollout_plan()
    return RolloutApplyResult(
        applied=False,
        dry_run=True,
        dialect="unresolved",
        migration_count=len(plan),
        statement_count=int(sum(item["statement_count"] for item in plan)),
        migrations=plan,
    )


def apply_rollout_assets(*, engine: Engine, dry_run: bool = False) -> RolloutApplyResult:
    """Apply checked-in rollout SQL assets to a PostgreSQL engine."""
    dialect_name = _require_supported_dialect(engine)
    plan = rollout_plan()
    statement_count = int(sum(item["statement_count"] for item in plan))

    if dry_run:
        return RolloutApplyResult(
            applied=False,
            dry_run=True,
            dialect=dialect_name,
            migration_count=len(plan),
            statement_count=statement_count,
            migrations=plan,
        )

    with engine.begin() as connection:
        for path in migration_asset_paths():
            for statement in split_sql_statements(migration_sql(path)):
                connection.exec_driver_sql(statement)

    return RolloutApplyResult(
        applied=True,
        dry_run=False,
        dialect=dialect_name,
        migration_count=len(plan),
        statement_count=statement_count,
        migrations=plan,
    )


def init_database_schema(*, engine: Engine, scope: str = "all") -> DbInitResult:
    """Create the base SQLAlchemy schema for the configured engine."""
    if scope == "prod":
        selected_table_names = PRODUCTION_TABLE_NAMES
    elif scope == "audit":
        selected_table_names = AUDIT_TABLE_NAMES
    else:
        selected_table_names = {table.name for table in Base.metadata.sorted_tables}

    selected_tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.name in selected_table_names
    ]
    Base.metadata.create_all(engine, tables=selected_tables)
    inspector = inspect(engine)
    tables = sorted(inspector.get_table_names())
    return DbInitResult(
        applied=True,
        dialect=_dialect_name(engine),
        table_count=len(tables),
        tables=tables,
    )


def describe_rollout_assets() -> dict[str, Any]:
    """Describe the rollout directory, README, and migration asset plan."""
    readme_path = migration_readme_path()
    instructions = None
    if readme_path.exists():
        instructions = readme_path.read_text(encoding="utf-8").strip()

    return {
        "migration_dir": str(migration_dir()),
        "readme_path": str(readme_path),
        "instructions": instructions,
        "migrations": rollout_plan(),
    }
