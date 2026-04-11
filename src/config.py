from datetime import date
from pathlib import Path
from urllib.parse import quote

from pydantic import Field
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    pg_dsn: str = Field(alias="PG_DSN")
    ch_dsn: str | None = Field(default=None, alias="CH_DSN")
    postgres_host: str | None = Field(default=None, alias="POSTGRES_HOST", exclude=True)
    postgres_port: str | None = Field(default=None, alias="POSTGRES_PORT", exclude=True)
    postgres_db: str | None = Field(default=None, alias="POSTGRES_DB", exclude=True)
    postgres_user: str | None = Field(default=None, alias="POSTGRES_USER", exclude=True)
    postgres_password: str | None = Field(default=None, alias="POSTGRES_PASSWORD", exclude=True)
    clickhouse_host: str | None = Field(default=None, alias="CLICKHOUSE_HOST", exclude=True)
    clickhouse_port: str | None = Field(default=None, alias="CLICKHOUSE_PORT", exclude=True)
    clickhouse_database: str | None = Field(default=None, alias="CLICKHOUSE_DATABASE", exclude=True)
    clickhouse_user: str | None = Field(default=None, alias="CLICKHOUSE_USER", exclude=True)
    clickhouse_password: str | None = Field(default=None, alias="CLICKHOUSE_PASSWORD", exclude=True)
    security_universe_table: str = Field(
        default="data_quant.us_stock_universe",
        alias="SEC_UNIVERSE_TABLE",
    )
    start_date: date = Field(default=date(2014, 1, 1), alias="START_DATE")
    scheduler_interval_minutes: int = Field(default=60, alias="SCHEDULER_INTERVAL_MINUTES", gt=0)
    offline_artifacts_dir: Path = Field(default=Path("artifacts"), alias="OFFLINE_ARTIFACTS_DIR")
    write_offline_artifacts: bool = Field(default=True, alias="WRITE_OFFLINE_ARTIFACTS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @staticmethod
    def _clean_text(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _build_postgres_dsn(cls, values: dict[str, object]) -> str | None:
        host = cls._clean_text(values.get("POSTGRES_HOST") or values.get("postgres_host"))
        database = cls._clean_text(values.get("POSTGRES_DB") or values.get("postgres_db"))
        user = cls._clean_text(values.get("POSTGRES_USER") or values.get("postgres_user"))
        if host is None or database is None or user is None:
            return None

        port = cls._clean_text(values.get("POSTGRES_PORT") or values.get("postgres_port")) or "5432"
        password = cls._clean_text(values.get("POSTGRES_PASSWORD") or values.get("postgres_password"))
        auth = quote(user)
        if password is not None:
            auth = f"{auth}:{quote(password)}"
        return f"postgresql+psycopg://{auth}@{host}:{port}/{database}"

    @classmethod
    def _build_clickhouse_dsn(cls, values: dict[str, object]) -> str | None:
        host = cls._clean_text(values.get("CLICKHOUSE_HOST") or values.get("clickhouse_host"))
        database = cls._clean_text(values.get("CLICKHOUSE_DATABASE") or values.get("clickhouse_database"))
        user = cls._clean_text(values.get("CLICKHOUSE_USER") or values.get("clickhouse_user"))
        if host is None or database is None or user is None:
            return None

        port = cls._clean_text(values.get("CLICKHOUSE_PORT") or values.get("clickhouse_port")) or "8123"
        password = cls._clean_text(values.get("CLICKHOUSE_PASSWORD") or values.get("clickhouse_password"))
        auth = quote(user)
        if password is not None:
            auth = f"{auth}:{quote(password)}"
        return f"clickhouse://{auth}@{host}:{port}/{database}"

    @model_validator(mode="before")
    @classmethod
    def _apply_legacy_runtime_env_compatibility(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        values = dict(data)

        pg_dsn = cls._clean_text(values.get("PG_DSN"))
        if pg_dsn is None:
            legacy_pg_dsn = cls._build_postgres_dsn(values)
            if legacy_pg_dsn is not None:
                values["PG_DSN"] = legacy_pg_dsn
        else:
            values["PG_DSN"] = pg_dsn

        ch_dsn = cls._clean_text(values.get("CH_DSN"))
        if ch_dsn is None:
            legacy_ch_dsn = cls._build_clickhouse_dsn(values)
            if legacy_ch_dsn is not None:
                values["CH_DSN"] = legacy_ch_dsn
        else:
            values["CH_DSN"] = ch_dsn

        table_name = cls._clean_text(values.get("SEC_UNIVERSE_TABLE"))
        if table_name is not None:
            values["SEC_UNIVERSE_TABLE"] = table_name

        return values
