import typer


app = typer.Typer()


@app.command("run-once")
def run_once() -> None:
    """Run the phase-1 pipeline once."""
    return None
