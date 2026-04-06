from src.config import Settings


def test_settings_reads_environment_variables(monkeypatch):
    monkeypatch.setenv("SEC_POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/sec")
    monkeypatch.setenv("SEC_CLICKHOUSE_DSN", "clickhouse://default:@localhost:8123/default")
    monkeypatch.setenv("SEC_USER_AGENT", "sec-filing-pipeline-test/1.0")

    settings = Settings()

    assert settings.postgres_dsn == "postgresql://postgres:postgres@localhost:5432/sec"
    assert settings.clickhouse_dsn == "clickhouse://default:@localhost:8123/default"
    assert settings.user_agent == "sec-filing-pipeline-test/1.0"
