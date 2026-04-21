from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.db.models import DelistedRouteCompletion, FilingAttempt, PipelineLog, RouteWatermark
from src.pipeline.types import RouteName


def _normalize_to_utc(value: datetime) -> datetime:
    """Normalize datetimes to UTC before comparing persistence timestamps."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


class PipelineRepository:
    def __init__(self, session: Session):
        """Persist runtime watermarks, logs, and filing attempts."""
        self.session = session

    def _is_postgresql(self) -> bool:
        """Check whether the current session is bound to PostgreSQL."""
        bind = self.session.get_bind()
        return bind is not None and bind.dialect.name == "postgresql"

    def _commit_with_rollback(self) -> None:
        """Commit the current transaction and roll back on failure."""
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def get_route_watermark(self, cik: str, route: RouteName) -> datetime | None:
        """Fetch the stored watermark for one CIK/route pair."""
        row = self.session.scalar(
            select(RouteWatermark).where(
                RouteWatermark.cik == cik,
                RouteWatermark.route == route,
            )
        )
        if row is None:
            return None

        return row.last_accepted_at

    def get_delisted_route_completion(
        self,
        *,
        composite_figi: str,
        cik: str,
        route: RouteName,
    ) -> DelistedRouteCompletion | None:
        """Fetch the persisted completion marker for a delisted security route."""
        return self.session.scalar(
            select(DelistedRouteCompletion).where(
                DelistedRouteCompletion.composite_figi == composite_figi,
                DelistedRouteCompletion.cik == cik,
                DelistedRouteCompletion.route == route,
            )
        )

    def upsert_route_watermark(self, *, cik: str, route: RouteName, accepted_at: datetime) -> None:
        """Advance a route watermark when a newer filing has been processed."""
        now = datetime.now(timezone.utc)

        if self._is_postgresql():
            stmt = pg_insert(RouteWatermark).values(
                cik=cik,
                route=route,
                last_accepted_at=accepted_at,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_route_watermark_cik_route",
                set_={
                    "last_accepted_at": stmt.excluded.last_accepted_at,
                    "updated_at": stmt.excluded.updated_at,
                },
                where=(RouteWatermark.last_accepted_at.is_(None))
                | (stmt.excluded.last_accepted_at > RouteWatermark.last_accepted_at),
            )
            self.session.execute(stmt)
        else:
            row = self.session.scalar(
                select(RouteWatermark).where(
                    RouteWatermark.cik == cik,
                    RouteWatermark.route == route,
                )
            )

            if row is None:
                self.session.add(
                    RouteWatermark(
                        cik=cik,
                        route=route,
                        last_accepted_at=accepted_at,
                        updated_at=now,
                    )
                )
            elif row.last_accepted_at is None or (
                _normalize_to_utc(accepted_at) > _normalize_to_utc(row.last_accepted_at)
            ):
                row.last_accepted_at = accepted_at
                row.updated_at = now

        self._commit_with_rollback()

    def mark_delisted_route_completed(
        self,
        *,
        composite_figi: str,
        cik: str,
        route: RouteName,
        delisted_utc_snapshot: datetime | None,
        last_seen_accepted_at: datetime | None,
    ) -> None:
        """Persist that a delisted security's route has been fully processed."""
        now = datetime.now(timezone.utc)

        if self._is_postgresql():
            stmt = pg_insert(DelistedRouteCompletion).values(
                composite_figi=composite_figi,
                cik=cik,
                route=route,
                delisted_utc_snapshot=delisted_utc_snapshot,
                last_seen_accepted_at=last_seen_accepted_at,
                is_completed=True,
                completed_at=now,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_delisted_completion_key",
                set_={
                    "delisted_utc_snapshot": stmt.excluded.delisted_utc_snapshot,
                    "last_seen_accepted_at": stmt.excluded.last_seen_accepted_at,
                    "is_completed": stmt.excluded.is_completed,
                    "completed_at": stmt.excluded.completed_at,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            self.session.execute(stmt)
        else:
            row = self.session.scalar(
                select(DelistedRouteCompletion).where(
                    DelistedRouteCompletion.composite_figi == composite_figi,
                    DelistedRouteCompletion.cik == cik,
                    DelistedRouteCompletion.route == route,
                )
            )

            if row is None:
                self.session.add(
                    DelistedRouteCompletion(
                        composite_figi=composite_figi,
                        cik=cik,
                        route=route,
                        delisted_utc_snapshot=delisted_utc_snapshot,
                        last_seen_accepted_at=last_seen_accepted_at,
                        is_completed=True,
                        completed_at=now,
                        updated_at=now,
                    )
                )
            else:
                row.delisted_utc_snapshot = delisted_utc_snapshot
                row.last_seen_accepted_at = last_seen_accepted_at
                row.is_completed = True
                row.completed_at = now
                row.updated_at = now

        self._commit_with_rollback()

    def invalidate_delisted_route_completion(
        self,
        *,
        composite_figi: str,
        cik: str,
        route: RouteName,
    ) -> None:
        """Clear a delisted-route completion marker so work can resume."""
        now = datetime.now(timezone.utc)
        row = self.session.scalar(
            select(DelistedRouteCompletion).where(
                DelistedRouteCompletion.composite_figi == composite_figi,
                DelistedRouteCompletion.cik == cik,
                DelistedRouteCompletion.route == route,
            )
        )

        if row is None:
            return

        row.is_completed = False
        row.delisted_utc_snapshot = None
        row.last_seen_accepted_at = None
        row.completed_at = None
        row.updated_at = now
        self._commit_with_rollback()

    def write_log(
        self,
        *,
        run_id: str,
        route: RouteName,
        stage: str,
        level: str,
        message: str,
        cik: str | None = None,
        accession_no: str | None = None,
        error_type: str | None = None,
        error_detail: str | None = None,
    ) -> None:
        """Persist one pipeline log record."""
        now = datetime.now(timezone.utc)

        self.session.add(
            PipelineLog(
                run_id=run_id,
                route=route,
                cik=cik,
                accession_no=accession_no,
                stage=stage,
                level=level,
                message=message,
                error_type=error_type,
                error_detail=error_detail,
                created_at=now,
            )
        )
        self._commit_with_rollback()

    def upsert_filing_attempt(
        self,
        *,
        run_id: str,
        route: RouteName,
        accession_no: str,
        cik: str | None,
        accepted_at: datetime | None,
        status: str,
        error_type: str | None = None,
        error_detail: str | None = None,
    ) -> None:
        """Insert or update the filing-attempt status for one runtime run."""
        now = datetime.now(timezone.utc)
        row = self.session.scalar(
            select(FilingAttempt).where(
                FilingAttempt.run_id == run_id,
                FilingAttempt.route == route,
                FilingAttempt.accession_no == accession_no,
            )
        )

        if row is None:
            self.session.add(
                FilingAttempt(
                    run_id=run_id,
                    route=route,
                    accession_no=accession_no,
                    cik=cik,
                    accepted_at=accepted_at,
                    status=status,
                    error_type=error_type,
                    error_detail=error_detail,
                    started_at=now,
                    updated_at=now,
                )
            )
        else:
            row.cik = cik
            row.accepted_at = accepted_at
            row.status = status
            row.error_type = error_type
            row.error_detail = error_detail
            row.updated_at = now

        self._commit_with_rollback()

    def latest_filing_attempt(self, *, route: RouteName, accession_no: str) -> FilingAttempt | None:
        """Return the latest attempt row for one route/accession across all runs."""
        return self.session.scalar(
            select(FilingAttempt).where(
                FilingAttempt.route == route,
                FilingAttempt.accession_no == accession_no,
            ).order_by(FilingAttempt.updated_at.desc(), FilingAttempt.id.desc())
        )

    def fail_stale_in_progress_attempt(
        self,
        *,
        route: RouteName,
        accession_no: str,
        older_than: datetime,
        error_type: str,
        error_detail: str,
    ) -> bool:
        """Mark the latest in-progress attempt failed when it is older than the cutoff."""
        row = self.latest_filing_attempt(route=route, accession_no=accession_no)
        if row is None or row.status != "in_progress":
            return False
        if _normalize_to_utc(row.updated_at) >= _normalize_to_utc(older_than):
            return False

        row.status = "failed"
        row.error_type = error_type
        row.error_detail = error_detail
        row.updated_at = datetime.now(timezone.utc)
        self._commit_with_rollback()
        return True

    def is_filing_completed(self, *, route: RouteName, accession_no: str) -> bool:
        """Return True when the latest DB attempt for this route/accession is completed."""
        row = self.latest_filing_attempt(route=route, accession_no=accession_no)
        if row is None:
            return False
        return row.status == "completed"
