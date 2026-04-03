import typer

from src.models import Base
from src.models import filing, registry, review, state  # noqa: F401
from src.storage.db import engine

app = typer.Typer(help="SEC Filing Pipeline")


@app.command("init-db")
def init_db() -> None:
    Base.metadata.create_all(bind=engine)


@app.command("owner-sync")
def owner_sync() -> None:
    raise NotImplementedError("owner-sync command is not implemented yet")


@app.command("replay-accession")
def replay_accession(accession_no: str) -> None:
    raise NotImplementedError(accession_no)


if __name__ == "__main__":
    app()
