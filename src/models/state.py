from datetime import datetime
from sqlalchemy import String, DateTime, func, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base
from src.domain.enums import RouteType

class IngestionState(Base):
    __tablename__ = "ingestion_state"
    
    cik: Mapped[str] = mapped_column(String(10), primary_key=True)
    # Use native string representing the RouteType for simpler migration / DB indexing
    route_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    
    last_acceptance_datetime_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_accession_no: Mapped[str | None] = mapped_column(String(25), nullable=True)
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
