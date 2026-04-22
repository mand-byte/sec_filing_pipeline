from functools import lru_cache
from typing import Literal

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from src.config import Settings


DbRole = Literal["prod", "audit"]


@lru_cache(maxsize=None)
def _engine_for_dsn(pg_dsn: str, *, role: DbRole = "prod") -> Engine:
    """Reuse one SQLAlchemy engine per DSN."""
    engine_kwargs: dict[str, object] = {}
    try:
        backend_name = make_url(pg_dsn).get_backend_name()
    except Exception:
        backend_name = ""

    if backend_name == "postgresql":
        engine_kwargs.update(
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args={
                "options": (
                    f"-c application_name=sec_filing_pipeline_{role} "
                    "-c lock_timeout=60000 "
                    "-c idle_in_transaction_session_timeout=300000"
                )
            },
        )

    return create_engine(pg_dsn, **engine_kwargs)


@lru_cache(maxsize=None)
def _session_factory_for_dsn(pg_dsn: str, *, role: DbRole = "prod") -> sessionmaker[Session]:
    """Reuse one configured session factory per DSN."""
    return sessionmaker(
        bind=_engine_for_dsn(pg_dsn, role=role),
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )


def _dsn_for_role(settings: Settings, *, role: DbRole) -> str:
    """Resolve the DSN for one logical database role."""
    if role == "audit":
        return str(settings.audit_pg_dsn or settings.pg_dsn)
    return str(settings.pg_dsn)


def build_engine(settings: Settings | None = None, *, role: DbRole = "prod") -> Engine:
    """Build or reuse the engine for the requested database role."""
    effective_settings = settings or Settings()
    return _engine_for_dsn(_dsn_for_role(effective_settings, role=role), role=role)


def build_session_factory(settings: Settings | None = None, *, role: DbRole = "prod") -> sessionmaker[Session]:
    """Build or reuse the session factory for the requested database role."""
    effective_settings = settings or Settings()
    return _session_factory_for_dsn(_dsn_for_role(effective_settings, role=role), role=role)


def get_session_factory(settings: Settings | None = None, *, role: DbRole = "prod") -> sessionmaker[Session]:
    """Return the default session factory entrypoint for callers."""
    return build_session_factory(settings, role=role)
