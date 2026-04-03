from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.config import settings

engine = create_engine(str(settings.POSTGRES_DSN), future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
