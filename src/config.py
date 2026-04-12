from datetime import date
import os
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
    llm_base_url: str | None = Field(default=None, alias="LLM_BASE_URL", exclude=True)
    llm_auth_key: str | None = Field(default=None, alias="LLM_AUTH_KEY", exclude=True)
    llm_model_name: str | None = Field(default=None, alias="LLM_MODEL_NAME", exclude=True)
    llm_timeout_seconds: str | None = Field(default=None, alias="LLM_TIMEOUT_SECONDS", exclude=True)
    edgar_identity: str | None = Field(default=None, alias="EDGAR_IDENTITY")
    security_universe_table: str = Field(
        default="data_quant.us_stock_universe",
        alias="SEC_UNIVERSE_TABLE",
    )
    start_date: date = Field(default=date(2014, 1, 1), alias="START_DATE")
    scheduler_interval_minutes: int = Field(default=60, alias="SCHEDULER_INTERVAL_MINUTES", gt=0)
    offline_artifacts_dir: Path = Field(default=Path("artifacts"), alias="OFFLINE_ARTIFACTS_DIR")
    write_offline_artifacts: bool = Field(default=True, alias="WRITE_OFFLINE_ARTIFACTS")
    text_normalizer_mode: str = Field(default="unavailable", alias="TEXT_NORMALIZER_MODE")
    text_normalizer_base_url: str | None = Field(default=None, alias="TEXT_NORMALIZER_BASE_URL")
    text_normalizer_api_key: str | None = Field(default=None, alias="TEXT_NORMALIZER_API_KEY")
    text_normalizer_model: str | None = Field(default=None, alias="TEXT_NORMALIZER_MODEL")
    text_normalizer_timeout_seconds: float = Field(default=30.0, alias="TEXT_NORMALIZER_TIMEOUT_SECONDS", gt=0)

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

        explicit_legacy_pg = any(
            os.environ.get(name)
            for name in ("POSTGRES_HOST", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_PORT")
        )
        explicit_pg_dsn = cls._clean_text(os.environ.get("PG_DSN"))
        pg_dsn = cls._clean_text(values.get("PG_DSN"))
        if explicit_legacy_pg and explicit_pg_dsn is None:
            legacy_pg_dsn = cls._build_postgres_dsn(values)
            if legacy_pg_dsn is not None:
                values["PG_DSN"] = legacy_pg_dsn
        elif pg_dsn is None:
            legacy_pg_dsn = cls._build_postgres_dsn(values)
            if legacy_pg_dsn is not None:
                values["PG_DSN"] = legacy_pg_dsn
        else:
            values["PG_DSN"] = pg_dsn

        explicit_legacy_ch = any(
            os.environ.get(name)
            for name in (
                "CLICKHOUSE_HOST",
                "CLICKHOUSE_DATABASE",
                "CLICKHOUSE_USER",
                "CLICKHOUSE_PASSWORD",
                "CLICKHOUSE_PORT",
            )
        )
        explicit_ch_dsn = cls._clean_text(os.environ.get("CH_DSN"))
        ch_dsn = cls._clean_text(values.get("CH_DSN"))
        if explicit_legacy_ch and explicit_ch_dsn is None:
            legacy_ch_dsn = cls._build_clickhouse_dsn(values)
            if legacy_ch_dsn is not None:
                values["CH_DSN"] = legacy_ch_dsn
        elif ch_dsn is None:
            legacy_ch_dsn = cls._build_clickhouse_dsn(values)
            if legacy_ch_dsn is not None:
                values["CH_DSN"] = legacy_ch_dsn
        else:
            values["CH_DSN"] = ch_dsn

        table_name = cls._clean_text(values.get("SEC_UNIVERSE_TABLE"))
        if table_name is not None:
            values["SEC_UNIVERSE_TABLE"] = table_name

        explicit_legacy_llm = any(
            os.environ.get(name)
            for name in ("LLM_BASE_URL", "LLM_MODEL_NAME", "LLM_AUTH_KEY", "LLM_TIMEOUT_SECONDS")
        )
        explicit_text_normalizer_mode = cls._clean_text(os.environ.get("TEXT_NORMALIZER_MODE"))
        configured_text_normalizer_mode = cls._clean_text(values.get("TEXT_NORMALIZER_MODE"))
        legacy_llm_base_url = cls._clean_text(values.get("LLM_BASE_URL") or values.get("llm_base_url"))
        legacy_llm_model = cls._clean_text(values.get("LLM_MODEL_NAME") or values.get("llm_model_name"))
        legacy_llm_auth_key = cls._clean_text(values.get("LLM_AUTH_KEY") or values.get("llm_auth_key"))
        legacy_llm_timeout_seconds = cls._clean_text(values.get("LLM_TIMEOUT_SECONDS") or values.get("llm_timeout_seconds"))

        if explicit_legacy_llm and explicit_text_normalizer_mode is None:
            if legacy_llm_base_url and legacy_llm_model:
                values["TEXT_NORMALIZER_MODE"] = "http_json"
                values.setdefault("TEXT_NORMALIZER_BASE_URL", legacy_llm_base_url)
                values.setdefault("TEXT_NORMALIZER_MODEL", legacy_llm_model)
                if legacy_llm_auth_key is not None:
                    values.setdefault("TEXT_NORMALIZER_API_KEY", legacy_llm_auth_key)
                if legacy_llm_timeout_seconds is not None:
                    values.setdefault("TEXT_NORMALIZER_TIMEOUT_SECONDS", legacy_llm_timeout_seconds)
        elif configured_text_normalizer_mode is None and legacy_llm_base_url and legacy_llm_model:
            values["TEXT_NORMALIZER_MODE"] = "http_json"
            values.setdefault("TEXT_NORMALIZER_BASE_URL", legacy_llm_base_url)
            values.setdefault("TEXT_NORMALIZER_MODEL", legacy_llm_model)
            if legacy_llm_auth_key is not None:
                values.setdefault("TEXT_NORMALIZER_API_KEY", legacy_llm_auth_key)
            if legacy_llm_timeout_seconds is not None:
                values.setdefault("TEXT_NORMALIZER_TIMEOUT_SECONDS", legacy_llm_timeout_seconds)

        return values
