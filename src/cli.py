import typer

from src.models import Base
from src.models import filing, registry, review, state  # noqa: F401
from src.storage.db import engine

app = typer.Typer(help="SEC Filing Pipeline")
parse_log_app = typer.Typer(help="Inspect parse-route decision logs")


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


@parse_log_app.command("query")
def parse_log_query(
    document_type: str | None = typer.Option(None, "--document-type"),
    from_utc: str | None = typer.Option(None, "--from-utc"),
    to_utc: str | None = typer.Option(None, "--to-utc"),
    failure_type: str | None = typer.Option(None, "--failure-type"),
    limit: int = typer.Option(100, "--limit"),
    offset: int = typer.Option(0, "--offset"),
) -> None:
    typer.echo(
        "query parse route logs by filters "
        f"document_type={document_type} from_utc={from_utc} to_utc={to_utc} "
        f"failure_type={failure_type} limit={limit} offset={offset}"
    )


@parse_log_app.command("timeline")
def parse_log_timeline(
    accession_no: str | None = typer.Option(None, "--accession-no"),
    document_id: str | None = typer.Option(None, "--document-id"),
) -> None:
    typer.echo(
        "show parse route decision timeline "
        f"accession_no={accession_no} document_id={document_id}"
    )


app.add_typer(parse_log_app, name="parse-log")


if __name__ == "__main__":
    app()
