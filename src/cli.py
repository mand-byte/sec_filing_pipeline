import threading

import typer

from src.config import Settings
from src.pipeline.scheduler import build_blocking_scheduler


app = typer.Typer(help="SEC filing pipeline CLI for running phase 1 tasks.")


def _resolve_scheduler_interval_minutes() -> int:
    return Settings(PG_DSN="postgresql://placeholder").scheduler_interval_minutes


def _noop_tick() -> None:
    return None


@app.command("run-once")
def run_once() -> None:
    """Run the phase-1 pipeline once."""
    typer.echo("run-once placeholder (task6 wiring)")


@app.command("schedule")
def schedule() -> None:
    """Run the phase-1 scheduler loop."""
    interval_minutes = _resolve_scheduler_interval_minutes()
    scheduler = build_blocking_scheduler(
        interval_minutes=interval_minutes,
        tick_callable=_noop_tick,
    )
    threading.Thread(target=scheduler.start, daemon=True).start()
    typer.echo("schedule placeholder")
