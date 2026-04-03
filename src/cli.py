import typer

app = typer.Typer(help="SEC Filing Pipeline")


@app.command("init-db")
def init_db() -> None:
    raise NotImplementedError("init-db command is not implemented yet")


@app.command("owner-sync")
def owner_sync() -> None:
    raise NotImplementedError("owner-sync command is not implemented yet")


@app.command("replay-accession")
def replay_accession(accession_no: str) -> None:
    raise NotImplementedError(accession_no)


if __name__ == "__main__":
    app()
