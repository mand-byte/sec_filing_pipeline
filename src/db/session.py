from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import Settings


def get_engine(settings: Settings | None = None):
    effective_settings = settings or Settings()
    return create_engine(effective_settings.pg_dsn)


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(settings),
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )
