from datetime import datetime
from typing import Any

from sqlalchemy import select

from src.models.parse_route_log import ParseRouteLog


class ParseRouteLogRepository:
    def __init__(self, session: Any) -> None:
        self.session = session
        self._sqlalchemy_mode = hasattr(self.session, "add") and hasattr(
            self.session, "execute"
        )
        if not self._sqlalchemy_mode and not hasattr(self.session, "rows"):
            self.session.rows = []

    def append(self, row: Any) -> None:
        if self._sqlalchemy_mode:
            if isinstance(row, ParseRouteLog):
                self.session.add(row)
                return

            self.session.add(
                ParseRouteLog(
                    id=row.id,
                    run_id=row.run_id,
                    route_type=row.route_type,
                    filing_id=row.filing_id,
                    accession_no=row.accession_no,
                    cik=row.cik,
                    document_id=row.document_id,
                    document_type=row.document_type,
                    document_filename=row.document_filename,
                    document_path=row.document_path,
                    snapshot_path=row.snapshot_path,
                    source_url=row.source_url,
                    sha256_hex=row.sha256_hex,
                    byte_length=row.byte_length,
                    parser_method=row.parser_method,
                    attempted_at_utc=row.attempted_at_utc,
                    status=row.status,
                    failure_type=row.failure_type,
                    error_message=row.error_message,
                    fallback_reason=row.fallback_reason,
                    decision_state=row.decision_state,
                    selected_candidate=row.selected_candidate,
                )
            )
            return

        self.session.rows.append(row)

    def query(
        self,
        document_type: str | None,
        start_utc: datetime | None,
        end_utc: datetime | None,
        failure_type: str | None,
        limit: int,
        offset: int,
    ) -> list[Any]:
        if self._sqlalchemy_mode:
            stmt = select(ParseRouteLog)
            if document_type is not None:
                stmt = stmt.where(ParseRouteLog.document_type == document_type)
            if start_utc is not None:
                stmt = stmt.where(ParseRouteLog.attempted_at_utc >= start_utc)
            if end_utc is not None:
                stmt = stmt.where(ParseRouteLog.attempted_at_utc <= end_utc)
            if failure_type is not None:
                stmt = stmt.where(ParseRouteLog.failure_type == failure_type)

            stmt = stmt.order_by(ParseRouteLog.attempted_at_utc, ParseRouteLog.id)
            stmt = stmt.offset(offset).limit(limit)
            return list(self.session.execute(stmt).scalars().all())

        filtered = [
            row
            for row in self.session.rows
            if (
                (document_type is None or row.document_type == document_type)
                and (start_utc is None or start_utc <= row.attempted_at_utc)
                and (end_utc is None or row.attempted_at_utc <= end_utc)
                and (failure_type is None or row.failure_type == failure_type)
            )
        ]
        filtered.sort(key=lambda row: (row.attempted_at_utc, row.id))
        return filtered[offset : offset + limit]

    def timeline(self, accession_no: str, document_id: str) -> list[Any]:
        if self._sqlalchemy_mode:
            stmt = (
                select(ParseRouteLog)
                .where(ParseRouteLog.accession_no == accession_no)
                .where(ParseRouteLog.document_id == document_id)
                .order_by(ParseRouteLog.attempted_at_utc, ParseRouteLog.id)
            )
            return list(self.session.execute(stmt).scalars().all())

        rows = [
            row
            for row in self.session.rows
            if row.accession_no == accession_no and row.document_id == document_id
        ]
        rows.sort(key=lambda row: (row.attempted_at_utc, row.id))
        return rows
