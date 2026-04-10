from __future__ import annotations

from src.config import Settings


def test_settings_loads_clickhouse_and_universe_env_aliases(monkeypatch) -> None:
    monkeypatch.setenv("PG_DSN", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("CH_DSN", "clickhouse://default@localhost/default")
    monkeypatch.setenv("SEC_UNIVERSE_TABLE", "data_quant.custom_universe")

    settings = Settings()

    assert settings.pg_dsn == "sqlite+pysqlite:///:memory:"
    assert settings.ch_dsn == "clickhouse://default@localhost/default"
    assert settings.security_universe_table == "data_quant.custom_universe"
