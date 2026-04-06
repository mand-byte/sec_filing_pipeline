from datetime import date
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    pg_dsn: str = Field(alias="PG_DSN")
    start_date: date = Field(default=date(2014, 1, 1), alias="START_DATE")
    scheduler_interval_minutes: int = Field(default=60, alias="SCHEDULER_INTERVAL_MINUTES", gt=0)
    offline_artifacts_dir: Path = Field(default=Path("artifacts"), alias="OFFLINE_ARTIFACTS_DIR")
    write_offline_artifacts: bool = Field(default=True, alias="WRITE_OFFLINE_ARTIFACTS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
