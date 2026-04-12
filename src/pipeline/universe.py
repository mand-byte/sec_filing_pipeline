from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any

import clickhouse_connect

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.config import Settings
from src.db.models import SecurityMaster


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


@dataclass(frozen=True)
class SecurityUniverseRow:
    ticker: str
    composite_figi: str
    cik: str
    active: bool
    delisted_utc: datetime | None


def _dedupe_security_rows(rows: list[SecurityUniverseRow]) -> list[SecurityUniverseRow]:
    deduped: dict[tuple[str, str], SecurityUniverseRow] = {}
    for row in rows:
        key = (row.cik, row.composite_figi)
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = row
            continue
        if row.active and not existing.active:
            deduped[key] = row
    return sorted(deduped.values(), key=lambda row: (row.cik, row.composite_figi))


def _normalize_to_utc(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip().replace("Z", "+00:00")
        if not cleaned:
            return None
        try:
            value = datetime.fromisoformat(cleaned)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "t", "yes", "y"}:
            return True
        if normalized in {"0", "false", "f", "no", "n"}:
            return False
    return False


def _coerce_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore").rstrip("\x00")
    return str(value)


def _load_from_security_master(session: Session) -> list[SecurityUniverseRow]:
    rows = (
        session.query(SecurityMaster)
        .order_by(SecurityMaster.cik.asc(), SecurityMaster.composite_figi.asc())
        .all()
    )
    return _dedupe_security_rows([
        SecurityUniverseRow(
            ticker=row.ticker,
            composite_figi=row.composite_figi,
            cik=row.cik,
            active=bool(row.active),
            delisted_utc=_normalize_to_utc(row.delisted_utc),
        )
        for row in rows
    ])


def _rows_from_clickhouse_result(result: Any) -> list[dict[str, Any]]:
    if result is None:
        return []

    named_results = getattr(result, "named_results", None)
    if callable(named_results):
        try:
            named_results = named_results()
        except Exception:
            named_results = None
    if isinstance(named_results, list):
        normalized_named = [dict(row) for row in named_results if isinstance(row, dict)]
        if normalized_named:
            return normalized_named

    result_rows = getattr(result, "result_rows", None)
    column_names = getattr(result, "column_names", None)
    if isinstance(result_rows, list) and isinstance(column_names, (list, tuple)):
        normalized_rows: list[dict[str, Any]] = []
        for row in result_rows:
            if isinstance(row, (list, tuple)) and len(row) == len(column_names):
                normalized_rows.append(dict(zip(column_names, row)))
        return normalized_rows

    return []


def _load_from_clickhouse(settings: Settings) -> list[SecurityUniverseRow] | None:
    ch_dsn = getattr(settings, "ch_dsn", None)
    if ch_dsn is None:
        return None

    table_name = settings.security_universe_table.strip()
    if not table_name or not _IDENTIFIER_RE.fullmatch(table_name):
        return None

    query = f"""
        SELECT ticker, composite_figi, cik, active, delisted_utc
        FROM {table_name}
        ORDER BY cik ASC, composite_figi ASC
    """

    try:
        client = clickhouse_connect.get_client(dsn=ch_dsn)
        result = client.query(query)
        rows = _rows_from_clickhouse_result(result)
        if hasattr(client, "close"):
            client.close()
    except Exception:
        return None

    normalized_rows = [
        SecurityUniverseRow(
            ticker=_coerce_text(row["ticker"]),
            composite_figi=_coerce_text(row["composite_figi"]),
            cik=_coerce_text(row["cik"]),
            active=_coerce_bool(row["active"]),
            delisted_utc=_normalize_to_utc(row.get("delisted_utc")),
        )
        for row in rows
    ]
    return _dedupe_security_rows(normalized_rows)


def load_security_universe(*, session: Session, settings: Settings) -> list[SecurityUniverseRow]:
    clickhouse_rows = _load_from_clickhouse(settings)
    if clickhouse_rows is not None:
        return clickhouse_rows

    table_name = settings.security_universe_table.strip()
    if not table_name or not _IDENTIFIER_RE.fullmatch(table_name):
        return _load_from_security_master(session)

    query = text(
        f"""
        SELECT ticker, composite_figi, cik, active, delisted_utc
        FROM {table_name}
        ORDER BY cik ASC, composite_figi ASC
        """
    )

    try:
        rows = session.execute(query).mappings().all()
    except SQLAlchemyError:
        try:
            session.rollback()
        except Exception:
            pass
        return _load_from_security_master(session)

    return _dedupe_security_rows([
        SecurityUniverseRow(
            ticker=_coerce_text(row["ticker"]),
            composite_figi=_coerce_text(row["composite_figi"]),
            cik=_coerce_text(row["cik"]),
            active=_coerce_bool(row["active"]),
            delisted_utc=_normalize_to_utc(row.get("delisted_utc")),
        )
        for row in rows
    ])
