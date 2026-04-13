from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from collections.abc import Callable
import re

import clickhouse_connect
from sqlalchemy import Engine, inspect, select, func
from sqlalchemy.orm import Session

from src.config import Settings
from src.db.models import SecurityMaster
from src.db.session import build_engine, get_session_factory


_QUALIFIED_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")
_CORE_TABLES = {
    "security_master",
    "filing_document",
    "extracted_fact",
    "extraction_evidence",
    "pipeline_log",
    "filing_attempt",
    "route_watermark",
}


@dataclass(frozen=True)
class RuntimePreflightCheck:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class RuntimePreflightResult:
    passed: bool
    checks: list[RuntimePreflightCheck]

    def asdict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the preflight result."""
        return {
            "passed": self.passed,
            "checks": [asdict(check) for check in self.checks],
        }


def _check(name: str, status: str, detail: str) -> RuntimePreflightCheck:
    """Build one normalized preflight check row."""
    return RuntimePreflightCheck(name=name, status=status, detail=detail)


def _split_qualified_name(value: str) -> tuple[str | None, str]:
    """Split an optional database-qualified table name."""
    cleaned = value.strip()
    if "." not in cleaned:
        return None, cleaned
    database, table = cleaned.split(".", 1)
    return database, table


def run_runtime_preflight(
    *,
    settings: Settings | None = None,
    engine: Engine | None = None,
    clickhouse_client_factory: Callable[..., object] | None = None,
) -> RuntimePreflightResult:
    """Validate DB, EDGAR, text-normalizer, and universe-source readiness."""
    effective_settings = settings or Settings()
    effective_engine = engine or build_engine(effective_settings)
    checks: list[RuntimePreflightCheck] = []

    try:
        inspector = inspect(effective_engine)
        tables = set(inspector.get_table_names())
        missing_tables = sorted(_CORE_TABLES - tables)
        if missing_tables:
            checks.append(_check("postgres_schema", "fail", f"missing core tables: {', '.join(missing_tables)}"))
        else:
            checks.append(_check("postgres_schema", "pass", f"core schema ready with {len(tables)} tables"))
    except Exception as exc:
        checks.append(_check("postgres_schema", "fail", f"postgres schema inspection failed: {exc}"))
        return RuntimePreflightResult(passed=False, checks=checks)

    session_factory = get_session_factory(effective_settings)
    with session_factory() as session:
        security_master_rows = 0
        try:
            security_master_rows = int(session.scalar(select(func.count()).select_from(SecurityMaster)) or 0)
        except Exception:
            security_master_rows = 0

    identity = (effective_settings.edgar_identity or "").strip()
    if identity:
        checks.append(_check("edgar_identity", "pass", "EDGAR_IDENTITY configured"))
    else:
        checks.append(_check("edgar_identity", "fail", "EDGAR_IDENTITY missing"))

    if effective_settings.text_normalizer_mode == "http_json":
        missing = []
        if not (effective_settings.text_normalizer_base_url or "").strip():
            missing.append("TEXT_NORMALIZER_BASE_URL")
        if not (effective_settings.text_normalizer_model or "").strip():
            missing.append("TEXT_NORMALIZER_MODEL")
        if missing:
            checks.append(_check("text_normalizer", "fail", f"missing provider config: {', '.join(missing)}"))
        else:
            checks.append(
                _check(
                    "text_normalizer",
                    "pass",
                    f"http_json configured for model {(effective_settings.text_normalizer_model or '').strip()}",
                )
            )
    else:
        checks.append(_check("text_normalizer", "warn", f"text normalizer mode is {effective_settings.text_normalizer_mode}"))

    if not effective_settings.ch_dsn:
        if security_master_rows > 0:
            checks.append(_check("security_universe_source", "pass", f"using security_master fallback with {security_master_rows} row(s)"))
        else:
            checks.append(_check("security_universe_source", "fail", "CH_DSN missing and security_master is empty"))
        return RuntimePreflightResult(
            passed=all(check.status != "fail" for check in checks),
            checks=checks,
        )

    client_factory = clickhouse_client_factory or clickhouse_connect.get_client
    try:
        client = client_factory(dsn=effective_settings.ch_dsn)
    except Exception as exc:
        checks.append(_check("clickhouse_connectivity", "fail", f"clickhouse connection failed: {exc}"))
        return RuntimePreflightResult(passed=False, checks=checks)

    try:
        client.query("SELECT 1")
        checks.append(_check("clickhouse_connectivity", "pass", "clickhouse connectivity ok"))

        table_name = effective_settings.security_universe_table.strip()
        if not table_name or not _QUALIFIED_IDENTIFIER_RE.fullmatch(table_name):
            checks.append(_check("security_universe_source", "fail", f"invalid SEC_UNIVERSE_TABLE: {table_name!r}"))
        else:
            exists_rows = client.query(f"EXISTS TABLE {table_name}").result_rows
            exists = bool(exists_rows and exists_rows[0] and int(exists_rows[0][0]) == 1)
            if exists:
                checks.append(_check("security_universe_source", "pass", f"configured universe table exists: {table_name}"))
            elif security_master_rows > 0:
                checks.append(
                    _check(
                        "security_universe_source",
                        "warn",
                        f"{table_name} missing in ClickHouse; runtime can fallback to security_master with {security_master_rows} row(s)",
                    )
                )
            else:
                database, table = _split_qualified_name(table_name)
                hint = ""
                if database is not None:
                    similar_rows = client.query(
                        f"SELECT database, name FROM system.tables WHERE name = '{table}' ORDER BY database, name"
                    ).result_rows
                    if similar_rows:
                        formatted = ", ".join(f"{db}.{name}" for db, name in similar_rows[:5])
                        hint = f"; similar tables: {formatted}"
                checks.append(_check("security_universe_source", "fail", f"configured universe table missing: {table_name}{hint}"))
    finally:
        if hasattr(client, "close"):
            client.close()

    return RuntimePreflightResult(
        passed=all(check.status != "fail" for check in checks),
        checks=checks,
    )
