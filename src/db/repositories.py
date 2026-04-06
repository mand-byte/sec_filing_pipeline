from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.db.models import DelistedRouteCompletion, PipelineLog, RouteWatermark
from src.pipeline.types import RouteName


class PipelineRepository:
    def __init__(self, session: Session):
        self.session = session

    def _is_postgresql(self) -> bool:
        bind = self.session.get_bind()
        return bind is not None and bind.dialect.name == "postgresql"

    def _commit_with_rollback(self) -> None:
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def get_route_watermark(self, cik: str, route: RouteName) -> datetime | None:
        row = self.session.scalar(
            select(RouteWatermark).where(
                RouteWatermark.cik == cik,
                RouteWatermark.route == route,
            )
        )
        if row is None:
            return None

        return row.last_accepted_at

    def upsert_route_watermark(self, *, cik: str, route: RouteName, accepted_at: datetime) -> None:
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
            elif row.last_accepted_at is None or accepted_at > row.last_accepted_at:
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
    ) -> None:
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
                created_at=now,
            )
        )
        self._commit_with_rollback()
