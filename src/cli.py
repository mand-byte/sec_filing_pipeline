from datetime import datetime

import typer

from src.config import Settings
from src.pipeline.routers.holding import HoldingRouter
from src.pipeline.routers.issuer import IssuerRouter
from src.pipeline.routers.owner import OwnerRouter
from src.pipeline.rules import is_filing_eligible
from src.pipeline.scheduler import build_blocking_scheduler, make_run_id, ordered_routers, run_single_tick


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

    eligible_securities = []
    for security in _load_run_once_securities():
        active = bool(getattr(security, "active", True))
        delisted_utc = getattr(security, "delisted_utc", None)
        accepted_at = getattr(security, "accepted_at", datetime.min)
        if is_filing_eligible(active, delisted_utc, accepted_at):
            eligible_securities.append(security)

    class _RunOnceRepo:
        def __init__(self, securities: list[object]) -> None:
            self._accession_by_cik = {
                getattr(security, "cik", None): getattr(security, "accession_no", None)
                for security in securities
                if getattr(security, "cik", None) is not None
            }

        def write_log(self, **kwargs) -> None:
            cik = kwargs.get("cik")
            accession_no = kwargs.get("accession_no")
            if accession_no is None and cik is not None:
                accession_no = self._accession_by_cik.get(cik)

            keys = ("route", "stage", "message", "error_type", "cik")
            parts = [f"{key}={kwargs[key]}" for key in keys if kwargs.get(key) is not None]
            if accession_no is not None:
                parts.append(f"accession_no={accession_no}")
            typer.echo("run-once error: " + " ".join(parts), err=True)

    run_single_tick(
        run_id=make_run_id(),
        securities=eligible_securities,
        routers=routers,
        repo=_RunOnceRepo(eligible_securities),
    )


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
