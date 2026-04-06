from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class SecurityMaster(Base):
    __tablename__ = "security_master"

    composite_figi: Mapped[str] = mapped_column(String(12), primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    cik: Mapped[str] = mapped_column(String(10), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    delisted_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_updated_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RouteWatermark(Base):
    __tablename__ = "route_watermark"
    __table_args__ = (
        UniqueConstraint("cik", "route", name="uq_route_watermark_cik_route"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cik: Mapped[str] = mapped_column(String(10), nullable=False)
    route: Mapped[str] = mapped_column(String(16), nullable=False)
    last_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DelistedRouteCompletion(Base):
    __tablename__ = "delisted_route_completion"
    __table_args__ = (
        UniqueConstraint("composite_figi", "cik", "route", name="uq_delisted_completion_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    composite_figi: Mapped[str] = mapped_column(String(12), nullable=False)
    cik: Mapped[str] = mapped_column(String(10), nullable=False)
    route: Mapped[str] = mapped_column(String(16), nullable=False)
    delisted_utc_snapshot: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FilingDocument(Base):
    __tablename__ = "filing_document"

    accession_no: Mapped[str] = mapped_column(String(32), primary_key=True)
    cik: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    ticker: Mapped[str | None] = mapped_column(String(32), nullable=True)
    form_type: Mapped[str] = mapped_column(String(32), nullable=False)
    filed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_amendment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    amendment_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExtractedFact(Base):
    __tablename__ = "extracted_fact"
    __table_args__ = (
        UniqueConstraint("accession_no", "route", "field_name", name="uq_fact_accession_route_field"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accession_no: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no"),
        nullable=False,
        index=True,
    )
    route: Mapped[str] = mapped_column(String(16), nullable=False)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    value_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExtractionEvidence(Base):
    __tablename__ = "extraction_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accession_no: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no"),
        nullable=False,
        index=True,
    )
    route: Mapped[str] = mapped_column(String(16), nullable=False)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    locator_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    source_section: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_item_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_xpath: Mapped[str | None] = mapped_column(Text, nullable=True)
    xbrl_concept: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_span: Mapped[str] = mapped_column(Text, nullable=False)
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PipelineLog(Base):
    __tablename__ = "pipeline_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    route: Mapped[str] = mapped_column(String(16), nullable=False)
    cik: Mapped[str | None] = mapped_column(String(10), nullable=True)
    accession_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReviewTask(Base):
    __tablename__ = "review_task"

    task_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accession_no: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no"),
        nullable=False,
        index=True,
    )
    route: Mapped[str] = mapped_column(String(16), nullable=False)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    assignee: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewDecision(Base):
    __tablename__ = "review_decision"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("review_task.task_id"),
        nullable=False,
        index=True,
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    corrected_value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
