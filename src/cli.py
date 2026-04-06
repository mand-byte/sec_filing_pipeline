from datetime import datetime

import typer

from src.config import Settings
from src.pipeline.routers.holding import HoldingRouter
from src.pipeline.routers.issuer import IssuerRouter
from src.pipeline.routers.owner import OwnerRouter
from src.pipeline.rules import is_filing_eligible
from src.pipeline.scheduler import build_blocking_scheduler, ordered_routers


app = typer.Typer(help="SEC filing pipeline CLI for running phase 1 tasks.")


def _load_run_once_securities() -> list[object]:
    return []


def _run_once_pipeline() -> None:
    typer.echo("run-once placeholder (task6 wiring)")
    router_map = {
        "issuer": IssuerRouter(),
        "owner": OwnerRouter(),
        "holding": HoldingRouter(),
    }
    routers = ordered_routers(router_map)
    typer.echo("route order: " + " -> ".join(router.name for router in routers))

    for security in _load_run_once_securities():
        active = bool(getattr(security, "active", True))
        delisted_utc = getattr(security, "delisted_utc", None)
        accepted_at = getattr(security, "accepted_at", datetime.min)
        if not is_filing_eligible(active, delisted_utc, accepted_at):
            continue

        for router in routers:
            router.run(security=security)


@app.command("run-once")
def run_once() -> None:
    """Run the phase-1 pipeline once."""
    _run_once_pipeline()


@app.command("schedule")
def schedule() -> None:
    """Run the phase-1 scheduler loop."""
    settings = Settings()
    scheduler = build_blocking_scheduler(
        interval_minutes=settings.scheduler_interval_minutes,
        tick_callable=run_once,
    )
    scheduler.start()
