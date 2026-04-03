import typer
import logging
from src.storage.db import engine
from src.models.base import Base

# Import all models so metadata is populated
from src.models.state import IngestionState  # noqa: F401

app = typer.Typer(help="SEC Filing Pipeline Phase 1")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

@app.command()
def init_db():
    """Initializes the PostgreSQL database schema if not present."""
    logger.info("Initializing database schemas...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized successfully.")

@app.command()
def verify_universe():
    """Tests the ClickHouse connection and fetches active CIKs count."""
    try:
        from src.storage.universe import fetch_active_ciks
        logger.info("Fetching universe targets from ClickHouse...")
        ciks = fetch_active_ciks()
        logger.info(f"Successfully fetched {len(ciks)} active CIKs targets.")
    except Exception as e:
        logger.error(f"Failed to fetch universe: {e}")

if __name__ == "__main__":
    app()
