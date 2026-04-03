from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class IngestionState(Base):
    __tablename__ = "ingestion_state"

    cik: Mapped[str] = mapped_column(String(10), primary_key=True)
    route_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    last_acceptance_datetime_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_accession_no: Mapped[str | None] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
