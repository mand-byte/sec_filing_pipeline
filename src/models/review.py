from datetime import datetime

from sqlalchemy import DateTime, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class ReviewQueueItem(Base):
    __tablename__ = "review_queue"

    review_item_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    filing_id: Mapped[str | None] = mapped_column(String(128), index=True)
    accession_no: Mapped[str] = mapped_column(String(32), index=True)
    document_id: Mapped[str | None] = mapped_column(String(128), index=True)
    fact_id: Mapped[str | None] = mapped_column(String(160), index=True)
    run_id: Mapped[str | None] = mapped_column(String(64), index=True)
    parser_method: Mapped[str | None] = mapped_column(String(64), index=True)
    decision_state: Mapped[str | None] = mapped_column(String(32), index=True)
    review_reason: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String(32), default="open")
    note: Mapped[str | None] = mapped_column(Text)
