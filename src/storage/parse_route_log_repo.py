from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any


class ParseRouteLogRepository:
    def __init__(self, session: Any) -> None:
        self.session = session
        if not hasattr(self.session, "rows"):
            self.session.rows = []

    def append(self, row: Any) -> None:
        self.session.rows.append(row)

    def query(
        self,
        document_type: str,
        start_utc: datetime,
        end_utc: datetime,
        failure_type: str | None,
        limit: int,
        offset: int,
    ) -> list[Any]:
        filtered = [
            row
            for row in self.session.rows
            if row.document_type == document_type
            and start_utc <= row.attempted_at_utc <= end_utc
            and row.failure_type == failure_type
        ]
        filtered.sort(key=lambda row: row.attempted_at_utc)
        return filtered[offset : offset + limit]

    def timeline(self, accession_no: str, document_id: str) -> list[Any]:
        rows = [
            row
            for row in self.session.rows
            if row.accession_no == accession_no and row.document_id == document_id
        ]
        rows.sort(key=lambda row: row.attempted_at_utc)
        return rows
