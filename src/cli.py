from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import typer

from src.core.config import settings
from src.models import Base
from src.models import filing, parse_route_log, registry, review, state  # noqa: F401
from src.storage.db import SessionLocal, engine
from src.storage.parse_route_log_repo import ParseRouteLogRepository
from src.storage.raw_store import RawStore
from src.storage.sec_download_adapter import SecDownloadAdapter
from src.worker.owner_pipeline import replay_owner_accession

app = typer.Typer(help="SEC Filing Pipeline")
parse_log_app = typer.Typer(help="Inspect parse-route decision logs")


def _parse_optional_iso_datetime(
    value: str | None, option_name: str
) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise typer.BadParameter(
            f"Invalid ISO datetime for {option_name}: {value}"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@app.command("init-db")
def init_db() -> None:
    Base.metadata.create_all(bind=engine)


@app.command("owner-sync")
def owner_sync(cik: str | None = typer.Option(None, "--cik")) -> None:
    if cik is None:
        typer.echo(
            "owner-sync is operational: pass --cik and use replay-accession for deterministic owner filing replays"
        )
        return

    typer.echo(
        "owner-sync minimal wiring is enabled; run replay-accession --cik "
        f"{cik} --accession-no <accession-no> to execute the phase3 flow"
    )


@app.command("replay-accession")
def replay_accession_command(
    accession_no: str,
    cik: str = typer.Option(..., "--cik"),
) -> None:
    run_id = f"replay-{uuid4().hex}"
    attempted_at_utc = datetime.now(timezone.utc)
    session = SessionLocal()
    try:
        repo = ParseRouteLogRepository(session)
        raw_store = RawStore(root=Path(settings.RAW_STORE_DIR))
        adapter = SecDownloadAdapter()
        processed = replay_owner_accession(
            session=session,
            parse_route_logger=repo,
            raw_store=raw_store,
            sec_download_adapter=adapter,
            cik=cik,
            accession_no=accession_no,
            run_id=run_id,
            attempted_at_utc=attempted_at_utc,
        )
        session.commit()
    except RuntimeError as exc:
        session.rollback()
        raise typer.BadParameter(
            "replay failed due to runtime dependency error: "
            f"{exc}. Ensure network access and edgar dependency are available."
        ) from exc
    finally:
        session.close()

    typer.echo(
        f"replay completed for {accession_no}: processed_documents={processed} run_id={run_id}"
    )


@parse_log_app.command("query")
def parse_log_query(
    document_type: str | None = typer.Option(None, "--document-type"),
    from_utc: str | None = typer.Option(None, "--from-utc"),
    to_utc: str | None = typer.Option(None, "--to-utc"),
    failure_type: str | None = typer.Option(None, "--failure-type"),
    limit: int = typer.Option(100, "--limit", min=1),
    offset: int = typer.Option(0, "--offset", min=0),
) -> None:
    start_utc = _parse_optional_iso_datetime(from_utc, "--from-utc")
    end_utc = _parse_optional_iso_datetime(to_utc, "--to-utc")
    session = SessionLocal()
    try:
        repo = ParseRouteLogRepository(session)
        rows = repo.query(
            document_type=document_type,
            start_utc=start_utc,
            end_utc=end_utc,
            failure_type=failure_type,
            limit=limit,
            offset=offset,
        )
    finally:
        session.close()

    for row in rows:
        typer.echo(
            " ".join(
                [
                    f"accession_no={row.accession_no}",
                    f"document_filename={row.document_filename}",
                    f"document_type={row.document_type}",
                    f"document_path={row.document_path}",
                    f"parser_method={row.parser_method}",
                    f"status={row.status}",
                    f"failure_type={row.failure_type}",
                    f"attempted_at_utc={row.attempted_at_utc.isoformat()}",
                ]
            )
        )


@parse_log_app.command("timeline")
def parse_log_timeline(
    accession_no: str = typer.Option(..., "--accession-no"),
    document_id: str = typer.Option(..., "--document-id"),
) -> None:
    session = SessionLocal()
    try:
        repo = ParseRouteLogRepository(session)
        rows = repo.timeline(accession_no=accession_no, document_id=document_id)
    finally:
        session.close()

    for row in rows:
        typer.echo(
            " ".join(
                [
                    f"attempted_at_utc={row.attempted_at_utc.isoformat()}",
                    f"parser_method={row.parser_method}",
                    f"status={row.status}",
                    f"failure_type={row.failure_type}",
                    f"fallback_reason={row.fallback_reason}",
                    f"decision_state={row.decision_state}",
                    f"selected_candidate={row.selected_candidate}",
                ]
            )
        )


app.add_typer(parse_log_app, name="parse-log")


if __name__ == "__main__":
    app()
