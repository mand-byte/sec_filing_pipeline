from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
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
    cik: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
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
        UniqueConstraint("accession_no", "route", "field_name", "subject_key", name="uq_fact_accession_route_field_subject"),
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
    subject_key: Mapped[str] = mapped_column(String(128), nullable=False, default="document", server_default="document")
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
    subject_key: Mapped[str] = mapped_column(String(128), nullable=False, default="document", server_default="document")
    locator_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    source_section: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_item_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_xpath: Mapped[str | None] = mapped_column(Text, nullable=True)
    xbrl_concept: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_span: Mapped[str] = mapped_column(Text, nullable=False)
    source_locator_json: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FilingAttempt(Base):
    __tablename__ = "filing_attempt"
    __table_args__ = (
        UniqueConstraint("run_id", "route", "accession_no", name="uq_filing_attempt_run_route_accession"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    route: Mapped[str] = mapped_column(String(16), nullable=False)
    accession_no: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    cik: Mapped[str | None] = mapped_column(String(10), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
    subject_key: Mapped[str] = mapped_column(String(128), nullable=False, default="document", server_default="document")
    primary_evidence_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("extraction_evidence.id"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
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
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    corrected_value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GoldenCase(Base):
    __tablename__ = "golden_case"

    case_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    accession_no: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    cik: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    form_type: Mapped[str] = mapped_column(String(32), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    truth_cutoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_amendment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    amendment_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_accession_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_snapshot_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GoldenSubject(Base):
    __tablename__ = "golden_subject"
    __table_args__ = (
        UniqueConstraint("case_id", "subject_key", name="uq_golden_subject_case_subject_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("golden_case.case_id"),
        nullable=False,
        index=True,
    )
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_key: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_subject_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GoldenTruth(Base):
    __tablename__ = "golden_truth"
    __table_args__ = (
        UniqueConstraint(
            "case_id",
            "subject_id",
            "field_name",
            "truth_tier",
            "truth_source",
            name="uq_golden_truth_case_subject_field_tier_source",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("golden_case.case_id"),
        nullable=False,
        index=True,
    )
    subject_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("golden_subject.id"),
        nullable=False,
        index=True,
    )
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    truth_tier: Mapped[str] = mapped_column(String(16), nullable=False)
    truth_source: Mapped[str] = mapped_column(String(64), nullable=False)
    is_applicable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(38, 10), nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GoldenInvariantResult(Base):
    __tablename__ = "golden_invariant_result"
    __table_args__ = (
        UniqueConstraint(
            "case_id",
            "subject_id",
            "invariant_name",
            name="uq_golden_invariant_case_subject_name",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("golden_case.case_id"),
        nullable=False,
        index=True,
    )
    subject_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("golden_subject.id"),
        nullable=False,
        index=True,
    )
    invariant_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    expected_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GoldenCandidate(Base):
    __tablename__ = "golden_candidate"
    __table_args__ = (
        UniqueConstraint(
            "eval_run_id",
            "case_id",
            "subject_id",
            "field_name",
            "candidate_key",
            name="uq_golden_candidate_run_case_subject_field_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    eval_run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("golden_eval_run.run_id"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("golden_case.case_id"),
        nullable=False,
        index=True,
    )
    subject_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("golden_subject.id"),
        nullable=False,
        index=True,
    )
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    candidate_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(38, 10), nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GoldenEvalRun(Base):
    __tablename__ = "golden_eval_run"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    config_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    git_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GoldenEvalResult(Base):
    __tablename__ = "golden_eval_result"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "case_id",
            "subject_id",
            "field_name",
            name="uq_golden_eval_result_run_case_subject_field",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("golden_eval_run.run_id"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("golden_case.case_id"),
        nullable=False,
        index=True,
    )
    subject_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("golden_subject.id"),
        nullable=False,
        index=True,
    )
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    matched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    truth_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    truth_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GoldenReviewPacket(Base):
    __tablename__ = "golden_review_packet"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "case_id",
            "subject_id",
            "field_name",
            name="uq_golden_review_packet_run_case_subject_field",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("golden_eval_run.run_id"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("golden_case.case_id"),
        nullable=False,
        index=True,
    )
    subject_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("golden_subject.id"),
        nullable=False,
        index=True,
    )
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    packet_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
