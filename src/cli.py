import typer


app = typer.Typer(help="SEC filing pipeline CLI for running phase 1 tasks.")


@app.command("run-once")
def run_once() -> None:
    """Run the phase-1 pipeline once."""
    typer.echo("run-once placeholder")


@app.command("schedule")
def schedule() -> None:
    """Run the phase-1 scheduler loop."""
    typer.echo("schedule placeholder")
