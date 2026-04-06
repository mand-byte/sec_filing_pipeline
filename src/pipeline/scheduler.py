from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Protocol

from apscheduler.schedulers.blocking import BlockingScheduler


ROUTE_ORDER = ("issuer", "owner", "holding")


class Router(Protocol):
    name: str

    def run(self, *, security: Any) -> None: ...


def ordered_routers(router_map: dict[str, object]) -> list[object]:
    return [router_map[route_name] for route_name in ROUTE_ORDER if route_name in router_map]


def run_single_tick(
    run_id: str,
    securities: Iterable[Any],
    routers: Iterable[Router],
    repo: Any,
) -> None:
    for security in securities:
        for router in routers:
            try:
                router.run(security=security)
            except Exception as exc:
                try:
                    repo.write_log(
                        run_id=run_id,
                        route=getattr(router, "name", router.__class__.__name__),
                        cik=getattr(security, "cik", None),
                        stage="extract",
                        level="ERROR",
                        message="router failed",
                        error_type=exc.__class__.__name__,
                    )
                except Exception:
                    pass
                continue


def build_blocking_scheduler(
    interval_minutes: int,
    tick_callable: Callable[[], None],
) -> BlockingScheduler:
    scheduler = BlockingScheduler()
    scheduler.add_job(
        tick_callable,
        trigger="interval",
        minutes=interval_minutes,
        id="phase1-tick",
    )
    return scheduler


def make_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
