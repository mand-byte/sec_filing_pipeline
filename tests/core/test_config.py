from pathlib import Path

from src.cli import app
from src.core import Settings


def test_settings_use_explicit_raw_store_dir() -> None:
    settings = Settings(
        POSTGRES_DSN="postgresql+psycopg://user:pass@localhost:5432/sec_db",
        RAW_STORE_DIR=Path("/tmp/sec-raw-store"),
        SEC_API_USER_AGENT="Example Corp (sec@example.com)",
    )

    assert (
        str(settings.POSTGRES_DSN)
        == "postgresql+psycopg://user:pass@localhost:5432/sec_db"
    )
    assert settings.RAW_STORE_DIR == Path("/tmp/sec-raw-store")
    assert settings.SEC_API_USER_AGENT == "Example Corp (sec@example.com)"


def test_settings_exposes_rate_limit_per_second_field() -> None:
    settings = Settings()

    assert settings.SEC_RATE_LIMIT_PER_SECOND == 10.0


def test_cli_app_has_expected_commands() -> None:
    command_names = {command.name for command in app.registered_commands}
    expected = {"init-db", "owner-sync", "replay-accession"}

    assert expected.issubset(command_names)
