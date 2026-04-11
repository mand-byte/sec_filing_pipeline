from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from src.config import Settings


def test_settings_loads_clickhouse_and_universe_env_aliases(monkeypatch) -> None:
    monkeypatch.setenv("PG_DSN", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("CH_DSN", "clickhouse://default@localhost/default")
    monkeypatch.setenv("SEC_UNIVERSE_TABLE", "data_quant.custom_universe")

    settings = Settings()

    assert settings.pg_dsn == "sqlite+pysqlite:///:memory:"
    assert settings.ch_dsn == "clickhouse://default@localhost/default"
    assert settings.security_universe_table == "data_quant.custom_universe"


def test_settings_builds_legacy_postgres_and_clickhouse_dsns(monkeypatch) -> None:
    monkeypatch.delenv("PG_DSN", raising=False)
    monkeypatch.delenv("CH_DSN", raising=False)
    monkeypatch.setenv("POSTGRES_HOST", "db.internal")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_DB", " sec_filing ")
    monkeypatch.setenv("POSTGRES_USER", "hubber")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("CLICKHOUSE_HOST", "ch.internal")
    monkeypatch.setenv("CLICKHOUSE_PORT", "9000")
    monkeypatch.setenv("CLICKHOUSE_DATABASE", " quant_data ")
    monkeypatch.setenv("CLICKHOUSE_USER", "analytics")
    monkeypatch.setenv("CLICKHOUSE_PASSWORD", "secret")

    settings = Settings()

    assert settings.pg_dsn == "postgresql+psycopg://hubber:secret@db.internal:5433/sec_filing"
    assert settings.ch_dsn == "clickhouse://analytics:secret@ch.internal:9000/quant_data"


def test_settings_loads_start_date_alias(monkeypatch) -> None:
    monkeypatch.setenv("PG_DSN", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("START_DATE", "2024-05-06")

    settings = Settings()

    assert settings.start_date == date(2024, 5, 6)


def test_settings_rejects_invalid_start_date_shape(monkeypatch) -> None:
    monkeypatch.setenv("PG_DSN", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("START_DATE", "2024/05/06")

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    assert "START_DATE" in str(exc_info.value)
