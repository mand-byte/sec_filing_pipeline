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


class Holding13FSummary(Base):
    __tablename__ = "holding_13f_summary"

    accession_no: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no"),
        primary_key=True,
    )
    info_table_entry_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    info_table_value_total_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    other_included_managers_count: Mapped[float | None] = mapped_column(Float, nullable=True)
    manager_structure_quant_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    manager_structure_quant_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    amendment_scope_quant_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    amendment_scope_quant_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_map_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Holding13FPosition(Base):
    __tablename__ = "holding_13f_position"
    __table_args__ = (
        UniqueConstraint("accession_no", "subject_key", name="uq_holding_13f_position_accession_subject"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accession_no: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no"),
        nullable=False,
        index=True,
    )
    subject_key: Mapped[str] = mapped_column(String(128), nullable=False)
    position_index: Mapped[int] = mapped_column(Integer, nullable=False)
    position_value_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    shares_or_principal_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    sole_voting_auth_shares: Mapped[float | None] = mapped_column(Float, nullable=True)
    shared_voting_auth_shares: Mapped[float | None] = mapped_column(Float, nullable=True)
    none_voting_auth_shares: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_map_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Owner345Summary(Base):
    __tablename__ = "owner_345_summary"

    accession_no: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no"),
        primary_key=True,
    )
    insider_transaction_quant_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    insider_transaction_quant_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    insider_role_ownership_structure_quant_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    insider_role_ownership_structure_quant_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_map_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Owner345Transaction(Base):
    __tablename__ = "owner_345_transaction"
    __table_args__ = (
        UniqueConstraint("accession_no", "subject_key", name="uq_owner_345_transaction_accession_subject"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accession_no: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no"),
        nullable=False,
        index=True,
    )
    subject_key: Mapped[str] = mapped_column(String(128), nullable=False)
    transaction_index: Mapped[int] = mapped_column(Integer, nullable=False)
    transaction_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    shares_acquired_or_disposed: Mapped[float | None] = mapped_column(Float, nullable=True)
    transaction_price_per_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    shares_owned_following_txn: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_map_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Owner345Position(Base):
    __tablename__ = "owner_345_position"
    __table_args__ = (
        UniqueConstraint("accession_no", "subject_key", name="uq_owner_345_position_accession_subject"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accession_no: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no"),
        nullable=False,
        index=True,
    )
    subject_key: Mapped[str] = mapped_column(String(128), nullable=False)
    position_index: Mapped[int] = mapped_column(Integer, nullable=False)
    position_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    non_derivative_shares_owned: Mapped[float | None] = mapped_column(Float, nullable=True)
    derivative_underlying_shares: Mapped[float | None] = mapped_column(Float, nullable=True)
    exercise_or_conversion_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_map_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Owner13DGSummary(Base):
    __tablename__ = "owner_13dg_summary"

    accession_no: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no"),
        primary_key=True,
    )
    beneficial_ownership_intent_quant_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    beneficial_ownership_intent_quant_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_of_funds_quant_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_of_funds_quant_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_map_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Owner13DGReportingPerson(Base):
    __tablename__ = "owner_13dg_reporting_person"
    __table_args__ = (
        UniqueConstraint("accession_no", "subject_key", name="uq_owner_13dg_person_accession_subject"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accession_no: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no"),
        nullable=False,
        index=True,
    )
    subject_key: Mapped[str] = mapped_column(String(128), nullable=False)
    reporting_person_index: Mapped[int] = mapped_column(Integer, nullable=False)
    beneficially_owned_shares: Mapped[float | None] = mapped_column(Float, nullable=True)
    beneficial_ownership_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    sole_voting_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    shared_voting_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    sole_dispositive_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    shared_dispositive_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    aggregate_purchase_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_of_funds_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_map_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Owner144Summary(Base):
    __tablename__ = "owner_144_summary"

    accession_no: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no"),
        primary_key=True,
    )
    rule144_sale_plan_quant_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule144_sale_plan_quant_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_map_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Owner144Notice(Base):
    __tablename__ = "owner_144_notice"
    __table_args__ = (
        UniqueConstraint("accession_no", "subject_key", name="uq_owner_144_notice_accession_subject"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accession_no: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no"),
        nullable=False,
        index=True,
    )
    subject_key: Mapped[str] = mapped_column(String(128), nullable=False)
    notice_index: Mapped[int] = mapped_column(Integer, nullable=False)
    notice_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    proposed_sale_shares: Mapped[float | None] = mapped_column(Float, nullable=True)
    proposed_sale_market_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    shares_sold_past_3m: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_value_sold_past_3m: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_map_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IssuerPeriodicSummary(Base):
    __tablename__ = "issuer_periodic_summary"

    accession_no: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no"),
        primary_key=True,
    )
    total_revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    operating_income: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_income: Mapped[float | None] = mapped_column(Float, nullable=True)
    diluted_eps: Mapped[float | None] = mapped_column(Float, nullable=True)
    cash_and_equivalents: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_debt: Mapped[float | None] = mapped_column(Float, nullable=True)
    operating_cash_flow: Mapped[float | None] = mapped_column(Float, nullable=True)
    capex: Mapped[float | None] = mapped_column(Float, nullable=True)
    shares_outstanding: Mapped[float | None] = mapped_column(Float, nullable=True)
    filing_delay_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    mdna_outlook_quant_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    mdna_outlook_quant_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_factor_quant_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_factor_quant_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    delay_reason_quant_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    delay_reason_quant_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_map_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IssuerEventSummary(Base):
    __tablename__ = "issuer_event_summary"

    accession_no: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no"),
        primary_key=True,
    )
    deal_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    financing_commitment_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    termination_fee: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_event_quant_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_event_quant_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    tender_going_private_quant_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    tender_going_private_quant_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_map_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IssuerOfferingSummary(Base):
    __tablename__ = "issuer_offering_summary"

    accession_no: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no"),
        primary_key=True,
    )
    gross_proceeds: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_proceeds: Mapped[float | None] = mapped_column(Float, nullable=True)
    underwriter_discount_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    financing_commitment_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    use_of_proceeds_quant_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    use_of_proceeds_quant_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_factor_quant_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_factor_quant_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_map_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IssuerSecurityLine(Base):
    __tablename__ = "issuer_security_line"
    __table_args__ = (
        UniqueConstraint("accession_no", "subject_key", name="uq_issuer_security_line_accession_subject"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accession_no: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no"),
        nullable=False,
        index=True,
    )
    subject_key: Mapped[str] = mapped_column(String(128), nullable=False)
    security_index: Mapped[int] = mapped_column(Integer, nullable=False)
    offering_price_per_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    securities_offered_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    offer_price_per_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    tender_shares_sought: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_map_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IssuerProposalVote(Base):
    __tablename__ = "issuer_proposal_vote"
    __table_args__ = (
        UniqueConstraint("accession_no", "subject_key", name="uq_issuer_proposal_vote_accession_subject"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accession_no: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no"),
        nullable=False,
        index=True,
    )
    subject_key: Mapped[str] = mapped_column(String(128), nullable=False)
    proposal_index: Mapped[int] = mapped_column(Integer, nullable=False)
    proposal_votes_for: Mapped[float | None] = mapped_column(Float, nullable=True)
    proposal_votes_against: Mapped[float | None] = mapped_column(Float, nullable=True)
    proposal_votes_abstain: Mapped[float | None] = mapped_column(Float, nullable=True)
    proposal_broker_non_votes: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_map_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IssuerExecComp(Base):
    __tablename__ = "issuer_exec_comp"
    __table_args__ = (
        UniqueConstraint("accession_no", "subject_key", name="uq_issuer_exec_comp_accession_subject"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accession_no: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no"),
        nullable=False,
        index=True,
    )
    subject_key: Mapped[str] = mapped_column(String(128), nullable=False)
    exec_index: Mapped[int] = mapped_column(Integer, nullable=False)
    exec_total_comp: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_map_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IssuerHolderOwnership(Base):
    __tablename__ = "issuer_holder_ownership"
    __table_args__ = (
        UniqueConstraint("accession_no", "subject_key", name="uq_issuer_holder_ownership_accession_subject"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    accession_no: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no"),
        nullable=False,
        index=True,
    )
    subject_key: Mapped[str] = mapped_column(String(128), nullable=False)
    holder_index: Mapped[int] = mapped_column(Integer, nullable=False)
    holder_beneficial_ownership_shares: Mapped[float | None] = mapped_column(Float, nullable=True)
    holder_beneficial_ownership_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_map_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IssuerProxySummary(Base):
    __tablename__ = "issuer_proxy_summary"

    accession_no: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no"),
        primary_key=True,
    )
    shares_outstanding: Mapped[float | None] = mapped_column(Float, nullable=True)
    proxy_proposal_quant_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    proxy_proposal_quant_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    comp_policy_quant_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    comp_policy_quant_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_map_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
    source_heading_path_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_block_offsets_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    adequacy_signals_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_history_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    selection_trace_json: Mapped[str | None] = mapped_column(Text, nullable=True)
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
