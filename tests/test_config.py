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


def test_settings_builds_text_normalizer_from_legacy_llm_envs(monkeypatch) -> None:
    monkeypatch.setenv("PG_DSN", "sqlite+pysqlite:///:memory:")
    monkeypatch.delenv("TEXT_NORMALIZER_MODE", raising=False)
    monkeypatch.delenv("TEXT_NORMALIZER_BASE_URL", raising=False)
    monkeypatch.delenv("TEXT_NORMALIZER_MODEL", raising=False)
    monkeypatch.delenv("TEXT_NORMALIZER_API_KEY", raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "gpt-5.4")
    monkeypatch.setenv("LLM_AUTH_KEY", "secret")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "12")

    settings = Settings()

    assert settings.text_normalizer_mode == "http_json"
    assert settings.text_normalizer_base_url == "https://example.test/v1"
    assert settings.text_normalizer_model == "gpt-5.4"
    assert settings.text_normalizer_api_key == "secret"
    assert settings.text_normalizer_timeout_seconds == 12.0


def test_explicit_text_normalizer_env_overrides_legacy_llm_envs(monkeypatch) -> None:
    monkeypatch.setenv("PG_DSN", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("TEXT_NORMALIZER_MODE", "unavailable")
    monkeypatch.setenv("TEXT_NORMALIZER_BASE_URL", "https://normalizer.example/v1")
    monkeypatch.setenv("TEXT_NORMALIZER_MODEL", "strict-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://legacy.example/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "legacy-model")

    settings = Settings()

    assert settings.text_normalizer_mode == "unavailable"
    assert settings.text_normalizer_base_url == "https://normalizer.example/v1"
    assert settings.text_normalizer_model == "strict-model"


def test_settings_loads_edgar_identity(monkeypatch) -> None:
    monkeypatch.setenv("PG_DSN", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("EDGAR_IDENTITY", "Example Ops ops@example.test")

    settings = Settings()

    assert settings.edgar_identity == "Example Ops ops@example.test"


def test_settings_loads_edgar_local_download_switch(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PG_DSN", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("EDGAR_DOWNLOAD_FILINGS", "true")
    monkeypatch.setenv("EDGAR_LOCAL_DATA_DIR", str(tmp_path / "edgar_local"))

    settings = Settings()

    assert settings.edgar_download_filings is True
    assert settings.edgar_local_data_dir == (tmp_path / "edgar_local")


def test_settings_maps_edgar_download_filings_alias(monkeypatch) -> None:
    monkeypatch.setenv("PG_DSN", "sqlite+pysqlite:///:memory:")
    monkeypatch.delenv("EDGAR_DOWNLOAD_FILINGS", raising=False)
    monkeypatch.setenv("EDGAR_DOWNLOAD_FILINGS_TO_LOCAL", "true")

    settings = Settings()

    assert settings.edgar_download_filings is True
