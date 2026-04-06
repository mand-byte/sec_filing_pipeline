from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    postgres_dsn: str
    clickhouse_dsn: str
    user_agent: str

    model_config = SettingsConfigDict(env_prefix="SEC_")
