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
    typer.echo(
        "run src.worker.owner_pipeline.persist_owner_submission from this command"
    )


@app.command("replay-accession")
def replay_accession(accession_no: str) -> None:
    typer.echo(f"load archived raw payload and rerun parser for {accession_no}")


if __name__ == "__main__":
    app()
