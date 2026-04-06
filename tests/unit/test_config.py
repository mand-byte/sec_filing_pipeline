from datetime import date

import pytest
from pydantic import ValidationError

from src.config import Settings


def test_settings_maps_start_date_from_environment(monkeypatch):
    monkeypatch.setenv("PG_DSN", "postgresql://postgres:postgres@localhost:5432/sec")
    monkeypatch.setenv("START_DATE", "2020-02-29")

    settings = Settings(_env_file=None)

    assert settings.start_date == date(2020, 2, 29)


def test_settings_requires_pg_dsn(monkeypatch):
    monkeypatch.delenv("PG_DSN", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    assert any(error["loc"][0] in {"PG_DSN", "pg_dsn"} for error in exc_info.value.errors())


def test_settings_includes_offline_artifact_fields(monkeypatch):
    monkeypatch.setenv("PG_DSN", "postgresql://postgres:postgres@localhost:5432/sec")

    settings = Settings(_env_file=None)

    assert settings.offline_artifacts_dir.name == "artifacts"
    assert settings.write_offline_artifacts is True
