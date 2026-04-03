import logging
import typer

app = typer.Typer(help="SEC Filing Pipeline")

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


@app.command("init-db")
def init_db() -> None:
    raise NotImplementedError("init-db command is not implemented yet")


@app.command("owner-sync")
def owner_sync() -> None:
    raise NotImplementedError("owner-sync command is not implemented yet")


@app.command("replay-accession")
def replay_accession() -> None:
    raise NotImplementedError("replay-accession command is not implemented yet")


if __name__ == "__main__":
    app()
