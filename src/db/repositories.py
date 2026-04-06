from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import DelistedRouteCompletion, PipelineLog, RouteWatermark
from src.pipeline.types import RouteName


class PipelineRepository:
    def __init__(self, session: Session):
        self.session = session

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
        row = self.session.scalar(
            select(RouteWatermark).where(
                RouteWatermark.cik == cik,
                RouteWatermark.route == route,
            )
        )

        now = datetime.now(timezone.utc)

        if row is None:
            self.session.add(
                RouteWatermark(
                    cik=cik,
                    route=route,
                    last_accepted_at=accepted_at,
                    updated_at=now,
                )
            )
        else:
            if row.last_accepted_at is None or accepted_at > row.last_accepted_at:
                row.last_accepted_at = accepted_at
                row.updated_at = now

        self.session.commit()

    def mark_delisted_route_completed(
        self,
        *,
        composite_figi: str,
        cik: str,
        route: RouteName,
        delisted_utc_snapshot: datetime | None,
        last_seen_accepted_at: datetime | None,
    ) -> None:
        row = self.session.scalar(
            select(DelistedRouteCompletion).where(
                DelistedRouteCompletion.composite_figi == composite_figi,
                DelistedRouteCompletion.cik == cik,
                DelistedRouteCompletion.route == route,
            )
        )

        now = datetime.now(timezone.utc)

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

        self.session.commit()

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
        self.session.commit()
