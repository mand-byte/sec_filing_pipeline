from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import Settings


@lru_cache(maxsize=None)
def _engine_for_dsn(pg_dsn: str) -> Engine:
    """Reuse one SQLAlchemy engine per DSN."""
    return create_engine(pg_dsn)


@lru_cache(maxsize=None)
def _session_factory_for_dsn(pg_dsn: str) -> sessionmaker[Session]:
    """Reuse one configured session factory per DSN."""
    return sessionmaker(
        bind=_engine_for_dsn(pg_dsn),
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )


def build_engine(settings: Settings | None = None) -> Engine:
    """Build or reuse the engine for the current settings."""
    effective_settings = settings or Settings()
    return _engine_for_dsn(str(effective_settings.pg_dsn))


def build_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    """Build or reuse the session factory for the current settings."""
    effective_settings = settings or Settings()
    return _session_factory_for_dsn(str(effective_settings.pg_dsn))


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    """Return the default session factory entrypoint for callers."""
    return build_session_factory(settings)
