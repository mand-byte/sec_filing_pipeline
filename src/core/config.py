from pathlib import Path

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    ENVIRONMENT: str = "development"

    POSTGRES_DSN: PostgresDsn | str = Field(
        default="postgresql+psycopg://user:pass@localhost:5432/sec_db"
    )

    CLICKHOUSE_HOST: str = "localhost"
    CLICKHOUSE_PORT: int = 8123
    CLICKHOUSE_USER: str = "default"
    CLICKHOUSE_PASSWORD: str = ""
    CLICKHOUSE_DB: str = "quant_data"

    RAW_STORE_DIR: Path = Path("./raw_data")

    SEC_API_USER_AGENT: str = "Sample Company (contact@sample.com)"
    SEC_RATE_LIMIT_PER_SECOND: float = 10.0


settings = Settings()
