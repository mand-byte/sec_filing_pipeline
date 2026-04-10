from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re

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


def _load_from_security_master(session: Session) -> list[SecurityUniverseRow]:
    rows = (
        session.query(SecurityMaster)
        .order_by(SecurityMaster.cik.asc(), SecurityMaster.composite_figi.asc())
        .all()
    )
    return [
        SecurityUniverseRow(
            ticker=row.ticker,
            composite_figi=row.composite_figi,
            cik=row.cik,
            active=bool(row.active),
            delisted_utc=_normalize_to_utc(row.delisted_utc),
        )
        for row in rows
    ]


def load_security_universe(*, session: Session, settings: Settings) -> list[SecurityUniverseRow]:
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
        return _load_from_security_master(session)

    return [
        SecurityUniverseRow(
            ticker=str(row["ticker"]),
            composite_figi=str(row["composite_figi"]),
            cik=str(row["cik"]),
            active=_coerce_bool(row["active"]),
            delisted_utc=_normalize_to_utc(row.get("delisted_utc")),
        )
        for row in rows
    ]
