from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from src.models.state import IngestionState


def _ensure_utc_aware(dt: datetime | None) -> datetime | None:
    """Normalize datetime to UTC-aware for safe comparison.

    SQLite may reload datetimes as naive (no timezone), while callers pass
    UTC-aware datetimes. This function ensures both are comparable.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class IngestionStateRepository:
    def __init__(self, session: Any) -> None:
        self.session = session
        self._sqlalchemy_mode = hasattr(self.session, "add") and hasattr(
            self.session, "execute"
        )

    def _pending_state(self, cik: str, route_type: str) -> IngestionState | None:
        pending_rows = getattr(self.session, "new", None)
        if pending_rows is None:
            return None

        for row in pending_rows:
            if (
                isinstance(row, IngestionState)
                and row.cik == cik
                and row.route_type == route_type
            ):
                return row
        return None

    def get_or_create(self, cik: str, route_type: str) -> IngestionState:
        if self._sqlalchemy_mode:
            pending = self._pending_state(cik, route_type)
            if pending is not None:
                return pending

            stmt = select(IngestionState).where(
                IngestionState.cik == cik, IngestionState.route_type == route_type
            )
            result = self.session.execute(stmt).scalar_one_or_none()
            if result is not None:
                return result
            state = IngestionState(cik=cik, route_type=route_type)
            self.session.add(state)
            return state

        rows = getattr(self.session, "ingestion_states", [])
        for row in rows:
            if row.cik == cik and row.route_type == route_type:
                return row
        state = IngestionState(cik=cik, route_type=route_type)
        rows.append(state)
        setattr(self.session, "ingestion_states", rows)
        return state

    def advance(
        self,
        state: IngestionState,
        accession_no: str,
        acceptance_datetime_utc: datetime,
    ) -> IngestionState:
        # Normalize persisted datetime to UTC-aware for comparison
        current_acceptance = _ensure_utc_aware(state.last_acceptance_datetime_utc)
        current_accession = state.last_accession_no or ""

        should_advance = current_acceptance is None
        if current_acceptance is not None:
            if acceptance_datetime_utc > current_acceptance:
                should_advance = True
            elif (
                acceptance_datetime_utc == current_acceptance
                and accession_no > current_accession
            ):
                should_advance = True

        if should_advance:
            state.last_accession_no = accession_no
            state.last_acceptance_datetime_utc = acceptance_datetime_utc

        return state
