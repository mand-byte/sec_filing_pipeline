from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class ParseRouteLog(Base):
    __tablename__ = "parse_route_log"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    route_type: Mapped[str] = mapped_column(String(32), index=True)
    filing_id: Mapped[str] = mapped_column(String(128), index=True)
    accession_no: Mapped[str] = mapped_column(String(32), index=True)
    cik: Mapped[str] = mapped_column(String(10), index=True)
    document_id: Mapped[str] = mapped_column(String(128), index=True)

    document_type: Mapped[str] = mapped_column(String(32), index=True)
    document_filename: Mapped[str] = mapped_column(String(255))
    document_path: Mapped[str] = mapped_column(Text)
    snapshot_path: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    sha256_hex: Mapped[str] = mapped_column(String(64), index=True)
    byte_length: Mapped[int] = mapped_column(Integer)

    parser_method: Mapped[str] = mapped_column(String(64), index=True)
    attempted_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    status: Mapped[str] = mapped_column(String(16), index=True)

    failure_type: Mapped[str | None] = mapped_column(String(16), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    fallback_reason: Mapped[str | None] = mapped_column(String(64), index=True)

    decision_state: Mapped[str | None] = mapped_column(String(32), index=True)
    selected_candidate: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index(
            "ix_parse_route_log_doc_type_attempted", "document_type", "attempted_at_utc"
        ),
        Index(
            "ix_parse_route_log_failure_attempted", "failure_type", "attempted_at_utc"
        ),
        Index(
            "ix_parse_route_log_timeline",
            "accession_no",
            "document_id",
            "attempted_at_utc",
        ),
    )
