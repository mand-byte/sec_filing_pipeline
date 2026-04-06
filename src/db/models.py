from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class SecurityMaster(Base):
    __tablename__ = "security_master"

    ticker: Mapped[str] = mapped_column(String(32), primary_key=True)
    cik: Mapped[str | None] = mapped_column(String(20), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class RouteWatermark(Base):
    __tablename__ = "route_watermark"

    route: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_accession_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DelistedRouteCompletion(Base):
    __tablename__ = "delisted_route_completion"

    ticker: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("security_master.ticker", ondelete="CASCADE"),
        primary_key=True,
    )
    route: Mapped[str] = mapped_column(String(64), primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FilingDocument(Base):
    __tablename__ = "filing_document"

    accession_no: Mapped[str] = mapped_column(String(32), primary_key=True)
    ticker: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("security_master.ticker", ondelete="SET NULL"),
        nullable=True,
    )
    route: Mapped[str] = mapped_column(String(64), nullable=False)
    filing_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    form_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ExtractedFact(Base):
    __tablename__ = "extracted_fact"
    __table_args__ = (
        UniqueConstraint("accession_no", "route", "field_name", name="uq_extracted_fact_accession_route_field"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    accession_no: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no", ondelete="CASCADE"),
        nullable=False,
    )
    route: Mapped[str] = mapped_column(String(64), nullable=False)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    field_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    as_of_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ExtractionEvidence(Base):
    __tablename__ = "extraction_evidence"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    extracted_fact_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("extracted_fact.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    locator: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PipelineLog(Base):
    __tablename__ = "pipeline_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    route: Mapped[str | None] = mapped_column(String(64), nullable=True)
    accession_no: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no", ondelete="SET NULL"),
        nullable=True,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ReviewTask(Base):
    __tablename__ = "review_task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    extracted_fact_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("extracted_fact.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ReviewDecision(Base):
    __tablename__ = "review_decision"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    review_task_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("review_task.id", ondelete="CASCADE"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
