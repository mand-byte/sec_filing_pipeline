from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class FilingIndex(Base):
    __tablename__ = "filing_index"

    filing_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    cik: Mapped[str] = mapped_column(String(10), index=True)
    accession_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    form_type_raw: Mapped[str] = mapped_column(String(32))
    form_type_base: Mapped[str] = mapped_column(String(32))
    is_amendment: Mapped[bool] = mapped_column(Boolean, nullable=False)
    route_type: Mapped[str] = mapped_column(String(32), index=True)
    acceptance_datetime_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    filing_date: Mapped[date | None] = mapped_column(Date)
    primary_document: Mapped[str | None] = mapped_column(String(255))
    amendment_group_key: Mapped[str] = mapped_column(String(128), index=True)
    amendment_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FilingDocument(Base):
    __tablename__ = "filing_document"

    document_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    filing_id: Mapped[str] = mapped_column(String(128), index=True)
    accession_no: Mapped[str] = mapped_column(String(32), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(128))
    sha256_hex: Mapped[str] = mapped_column(String(64), index=True)
    byte_length: Mapped[int] = mapped_column(Integer)
    raw_path: Mapped[str] = mapped_column(Text)
    decoded_text_path: Mapped[str | None] = mapped_column(Text)
    parser_snapshot_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ExtractedFact(Base):
    __tablename__ = "extracted_fact"

    fact_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    filing_id: Mapped[str] = mapped_column(String(128), index=True)
    accession_no: Mapped[str] = mapped_column(String(32), index=True)
    cik: Mapped[str | None] = mapped_column(String(10), index=True)
    document_id: Mapped[str | None] = mapped_column(String(128), index=True)
    run_id: Mapped[str | None] = mapped_column(String(64), index=True)
    fact_name: Mapped[str] = mapped_column(String(128), index=True)
    fact_value: Mapped[str] = mapped_column(Text)
    parser_method: Mapped[str] = mapped_column(String(64))
    fallback_reason: Mapped[str | None] = mapped_column(String(64), index=True)
    confidence_score: Mapped[float] = mapped_column(nullable=False)
    confidence_bucket: Mapped[str] = mapped_column(String(16))
    decision_state: Mapped[str] = mapped_column(String(32))
    snippet_text: Mapped[str] = mapped_column(Text)
    snippet_locator: Mapped[str] = mapped_column(Text)
    document_filename: Mapped[str] = mapped_column(String(255))
    validation_results: Mapped[dict] = mapped_column(JSON)
    attempted_methods: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
