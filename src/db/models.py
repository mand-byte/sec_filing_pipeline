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
    """证券主数据表：存储 ticker、CIK、FIGI、上市状态及退市时间等基础主数据。"""
    __tablename__ = "security_master"

    composite_figi: Mapped[str] = mapped_column(String(12), primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    cik: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    delisted_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_updated_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RouteWatermark(Base):
    """路由增量游标表：记录每个 CIK 在 issuer/owner/holding 路线上的最近 accepted_at 水位。"""
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
    """退市路由完成表：标记退市证券在某条路线上是否已经完成历史回填。"""
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
    """Filing 主表：一份 SEC filing 一行，保存文档级公共元数据并作为结果表外键锚点。"""
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


class FilingStatus(Base):
    """Filing 当前状态表：生产库里用于断点续跑与去重判断的全局 filing 状态。"""
    __tablename__ = "filing_status"
    __table_args__ = (
        UniqueConstraint("route", "accession_no", name="uq_filing_status_route_accession"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    route: Mapped[str] = mapped_column(String(16), nullable=False)
    accession_no: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("filing_document.accession_no"),
        nullable=False,
        index=True,
    )
    cik: Mapped[str | None] = mapped_column(String(10), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    latest_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Holding13FSummary(Base):
    """13F 汇总表：保存一份 13F filing 的 summary 级字段与文本量化结果。"""
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
    """13F 持仓行表：一行一个 holding position，保存 13F infotable 的行级结果。"""
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
    """3/4/5 汇总表：保存 Form 3/4/5 filing 级文本量化结果。"""
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
    """3/4/5 交易行表：一行一个 transaction，保存内部人交易数值字段。"""
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
    """3/4/5 持仓行表：一行一个非衍生或衍生持仓对象。"""
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
    """13D/13G 汇总表：保存 filing 级意图、资金来源等文本量化结果。"""
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
    """13D/13G 报告人表：一行一个 reporting person，保存受益持股与投票/处置权数据。"""
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
    """Form 144 汇总表：保存 filing 级 sale plan 文本量化结果。"""
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
    """Form 144 明细表：一行一个 sale notice 或 past-3m sale 记录。"""
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
    """Issuer 定期汇总表：保存 10-K/10-Q/20-F 等定期报告的 filing 级财务与文本量化结果。"""
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
    """Issuer 事件汇总表：保存 8-K/事件型 6-K/并购事件 filing 的 filing 级结果。"""
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
    """Issuer 发行汇总表：保存 S-1/424B4 等发行募资 filing 的 filing 级结果。"""
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
    """Issuer 证券行表：一行一个 security line，保存发行或要约中的证券级价格与数量。"""
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
    """Issuer 提案投票表：一行一个 proposal，保存 8-K/Proxy 的投票结果。"""
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
    """Issuer 高管薪酬表：一行一个 executive compensation row。"""
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
    """Issuer 持有人持股表：一行一个 holder beneficial ownership row。"""
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
    """Issuer Proxy 汇总表：保存 DEF 14A 等 proxy filing 的 filing 级治理/薪酬文本量化结果。"""
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


class PipelineLog(Base):
    """运行日志表：记录每次 run 的阶段日志、错误类型与详细错误信息。"""
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
    """Filing 处理状态表：记录某次 run 中每个 accession 在某条 route 上的处理状态。"""
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
    """审核任务表：记录需要人工确认或修正的字段级 review 任务。"""
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
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assignee: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewDecision(Base):
    """审核决策表：记录 review task 的最终人工决策、修正值和 reviewer。"""
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
    """Golden case 表：定义人工校验/评估使用的 filing 级真值案例。"""
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
    """Golden subject 表：定义 golden case 内部的主体粒度，如 transaction/proposal/position。"""
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
    """Golden truth 表：保存 case+subject+field 粒度的真值记录。"""
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
    """Golden invariant 表：保存 accounting / consistency invariant 的检验结果。"""
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
    """Golden candidate 表：记录某次 eval run 中每个候选抽取值及其 provenance。"""
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
    """Golden eval run 表：记录一次完整 golden 评估运行的元数据与汇总。"""
    __tablename__ = "golden_eval_run"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    config_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    git_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GoldenEvalResult(Base):
    """Golden eval result 表：记录 run 对每个 case/subject/field 的评估结果。"""
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
    """Golden review packet 表：保存需人工复核的评估包与回放数据。"""
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


PRODUCTION_TABLE_NAMES = {
    "security_master",
    "route_watermark",
    "delisted_route_completion",
    "filing_document",
    "filing_status",
    "holding_13f_summary",
    "holding_13f_position",
    "owner_345_summary",
    "owner_345_transaction",
    "owner_345_position",
    "owner_13dg_summary",
    "owner_13dg_reporting_person",
    "owner_144_summary",
    "owner_144_notice",
    "issuer_periodic_summary",
    "issuer_event_summary",
    "issuer_offering_summary",
    "issuer_security_line",
    "issuer_proposal_vote",
    "issuer_exec_comp",
    "issuer_holder_ownership",
    "issuer_proxy_summary",
    "review_task",
    "review_decision",
    "golden_case",
    "golden_subject",
    "golden_truth",
}

AUDIT_TABLE_NAMES = {
    table.name
    for table in Base.metadata.sorted_tables
}
