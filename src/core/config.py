from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import PostgresDsn, HttpUrl, Field
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    
    # Environment
    ENVIRONMENT: str = "development"
    
    # PostgreSQL - local or managed instance
    POSTGRES_DSN: PostgresDsn | str = Field(default="postgresql+psycopg://user:pass@localhost:5432/sec_db")
    
    # ClickHouse - read only universe source
    CLICKHOUSE_HOST: str = "localhost"
    CLICKHOUSE_PORT: int = 8123
    CLICKHOUSE_USER: str = "default"
    CLICKHOUSE_PASSWORD: str = ""
    CLICKHOUSE_DB: str = "quant_data"
    
    # Raw Storage Array
    RAW_STORE_DIR: Path = Path("./raw_data")
    
    # Pipeline Settings
    SEC_API_USER_AGENT: str = "Sample Company (contact@sample.com)"

settings = Settings()
