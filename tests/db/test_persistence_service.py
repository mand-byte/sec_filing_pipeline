from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.db.base import Base
from src.db.models import (
    ExtractedFact,
    ExtractionEvidence,
    FilingDocument,
    IssuerEventSummary,
    IssuerExecComp,
    IssuerHolderOwnership,
    IssuerOfferingSummary,
    IssuerPeriodicSummary,
    IssuerProposalVote,
    IssuerProxySummary,
    IssuerSecurityLine,
    Owner13DGReportingPerson,
    Owner13DGSummary,
    Owner144Notice,
    Owner144Summary,
    Owner345Position,
    Owner345Summary,
    Owner345Transaction,
    Holding13FPosition,
    Holding13FSummary,
    ReviewTask,
)
from src.pipeline.services import EvidenceInput, FactInput, PersistenceService
from src.pipeline.types import FilingRecord


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False)()


def _filing() -> FilingRecord:
    return FilingRecord(
        accession_no="0000000000-24-000010",
        cik="0000789019",
        ticker="MSFT",
        form_type="4",
        filed_at=None,
        accepted_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
        period_end=None,
        is_amendment=False,
        amendment_no=None,
    )


def _holding_filing(form_type: str = "13F-HR") -> FilingRecord:
    return FilingRecord(
        accession_no="0000000000-24-000013",
        cik="0000789019",
        ticker="MSFT",
        form_type=form_type,
        filed_at=None,
        accepted_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
        period_end=None,
        is_amendment=form_type.endswith("/A"),
        amendment_no=1 if form_type.endswith("/A") else None,
    )


def _issuer_filing(form_type: str = "8-K") -> FilingRecord:
    return FilingRecord(
        accession_no="0000000000-24-000014",
        cik="0000789019",
        ticker="MSFT",
        form_type=form_type,
        filed_at=None,
        accepted_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
        period_end=None,
        is_amendment=False,
        amendment_no=None,
    )


def _custom_filing(*, accession_no: str, form_type: str) -> FilingRecord:
    return FilingRecord(
        accession_no=accession_no,
        cik="0000789019",
        ticker="MSFT",
        form_type=form_type,
        filed_at=None,
        accepted_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
        period_end=None,
        is_amendment=form_type.endswith("/A"),
        amendment_no=1 if form_type.endswith("/A") else None,
    )


def _normalize_to_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def test_persist_filing_bundle_supports_multiple_subject_keys() -> None:
    session = _session()
    service = PersistenceService(session)

    service.persist_filing_bundle(
        filing=_filing(),
        route="owner",
        facts=[
            FactInput(field_name="shares_acquired_or_disposed", subject_key="txn:1", value_numeric=100.0),
            FactInput(field_name="shares_acquired_or_disposed", subject_key="txn:2", value_numeric=200.0),
        ],
        evidences=[
            EvidenceInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                locator_kind="obj",
                source_span="transactions[0].shares",
                source_locator_json='{"kind":"obj","path":"transactions[0].shares"}',
                raw_value="100",
                normalized_value="100.0",
            ),
            EvidenceInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:2",
                locator_kind="obj",
                source_span="transactions[1].shares",
                source_locator_json='{"kind":"obj","path":"transactions[1].shares"}',
                raw_value="200",
                normalized_value="200.0",
            ),
        ],
    )

    txns = session.query(Owner345Transaction).order_by(Owner345Transaction.subject_key).all()
    assert len(txns) == 2
    assert [txn.subject_key for txn in txns] == ["txn:1", "txn:2"]
    assert '"source_locator_json": "{\\"kind\\":\\"obj\\",\\"path\\":\\"transactions[0].shares\\"}"' in txns[0].evidence_map_json
    assert '"source_locator_json": "{\\"kind\\":\\"obj\\",\\"path\\":\\"transactions[1].shares\\"}"' in txns[1].evidence_map_json
    assert session.query(ExtractedFact).all() == []
    assert session.query(ExtractionEvidence).all() == []


def test_persist_filing_bundle_derives_source_locator_json_when_missing() -> None:
    session = _session()
    service = PersistenceService(session)

    service.persist_filing_bundle(
        filing=_filing(),
        route="issuer",
        facts=[FactInput(field_name="total_revenue", value_numeric=1000.0)],
        evidences=[
            EvidenceInput(
                field_name="total_revenue",
                locator_kind="xbrl_xml",
                source_span="instant=2024-03-31",
                source_xpath="rev-best",
                xbrl_concept="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                raw_value="1000",
                normalized_value="1000.0",
            )
        ],
    )

    summary = session.query(IssuerPeriodicSummary).one()
    assert '"locator_kind": "xbrl_xml"' in summary.evidence_map_json
    assert '"source_xpath": "rev-best"' in summary.evidence_map_json
    assert '"xbrl_concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"' in summary.evidence_map_json


def test_persist_filing_bundle_preserves_rich_text_evidence_metadata() -> None:
    session = _session()
    service = PersistenceService(session)

    service.persist_filing_bundle(
        filing=_filing(),
        route="issuer",
        facts=[FactInput(field_name="current_event_quant", value_text="event", confidence=0.99)],
        evidences=[
            EvidenceInput(
                field_name="current_event_quant",
                locator_kind="section_window",
                source_span="12:17",
                source_xpath="sections[Current report]",
                source_locator_json='{"locator_kind":"section_window"}',
                source_heading_path_json='["Current report"]',
                source_block_offsets_json='{"source_start":12,"source_end":17}',
                adequacy_signals_json='{"window_found":true}',
                retry_history_json="[]",
                selection_trace_json='{"selected_value":"event"}',
                raw_value="event",
                normalized_value="event",
            )
        ],
    )

    summary = session.query(IssuerEventSummary).one()
    assert '"source_heading_path_json": "[\\"Current report\\"]"' in summary.evidence_map_json
    assert '"source_block_offsets_json": "{\\"source_start\\":12,\\"source_end\\":17}"' in summary.evidence_map_json
    assert '"adequacy_signals_json": "{\\"window_found\\":true}"' in summary.evidence_map_json
    assert '"retry_history_json": "[]"' in summary.evidence_map_json
    assert '"selection_trace_json": "{\\"selected_value\\":\\"event\\"}"' in summary.evidence_map_json


def test_persist_filing_bundle_truncates_bounded_evidence_metadata() -> None:
    session = _session()
    service = PersistenceService(session)
    long_section = "Section " + ("A" * 200)
    long_item = "1." + ("2" * 50)
    long_concept = "us-gaap:" + ("Revenue" * 30)

    service.persist_filing_bundle(
        filing=_filing(),
        route="issuer",
        facts=[FactInput(field_name="current_event_quant", value_text="event", confidence=0.99)],
        evidences=[
            EvidenceInput(
                field_name="current_event_quant",
                locator_kind="section_window",
                source_span="12:17",
                source_section=long_section,
                source_item_no=long_item,
                xbrl_concept=long_concept,
                source_xpath="sections[Current report]",
                raw_value="event",
                normalized_value="event",
            )
        ],
    )

    summary = session.query(IssuerEventSummary).one()
    assert long_section[:128] in summary.evidence_map_json
    assert long_item[:32] in summary.evidence_map_json
    assert long_concept[:128] in summary.evidence_map_json


def test_persist_filing_bundle_flushes_filing_document_before_evidence_rows() -> None:
    session = _session()
    service = PersistenceService(session)
    flush_snapshots: list[list[str]] = []
    original_flush = session.flush

    def recording_flush(*args, **kwargs):
        flush_snapshots.append(sorted(type(obj).__name__ for obj in session.new))
        return original_flush(*args, **kwargs)

    session.flush = recording_flush  # type: ignore[method-assign]

    service.persist_filing_bundle(
        filing=_filing(),
        route="issuer",
        facts=[FactInput(field_name="current_event_quant", value_text="event", confidence=0.99)],
        evidences=[
            EvidenceInput(
                field_name="current_event_quant",
                locator_kind="section_window",
                source_span="12:17",
                source_xpath="sections[Current report]",
                raw_value="event",
                normalized_value="event",
            )
        ],
    )

    assert flush_snapshots[0] == ["FilingDocument"]


def test_persist_filing_bundle_updates_existing_subject_key_row() -> None:
    session = _session()
    service = PersistenceService(session)
    filing = _filing()

    service.persist_filing_bundle(
        filing=filing,
        route="owner",
        facts=[FactInput(field_name="transaction_price_per_share", subject_key="txn:1", value_numeric=10.0)],
        evidences=[
            EvidenceInput(
                field_name="transaction_price_per_share",
                subject_key="txn:1",
                locator_kind="obj",
                source_span="transactions[0].price",
                raw_value="10",
                normalized_value="10.0",
            )
        ],
    )
    service.persist_filing_bundle(
        filing=filing,
        route="owner",
        facts=[FactInput(field_name="transaction_price_per_share", subject_key="txn:1", value_numeric=11.0)],
        evidences=[
            EvidenceInput(
                field_name="transaction_price_per_share",
                subject_key="txn:1",
                locator_kind="obj",
                source_span="transactions[0].price",
                raw_value="11",
                normalized_value="11.0",
            )
        ],
    )

    txns = session.query(Owner345Transaction).all()
    assert len(txns) == 1
    assert txns[0].subject_key == "txn:1"
    assert txns[0].transaction_price_per_share == 11.0


def test_persist_filing_bundle_supports_holding_position_rows() -> None:
    session = _session()
    service = PersistenceService(session)

    service.persist_filing_bundle(
        filing=_holding_filing(),
        route="holding",
        facts=[
            FactInput(field_name="position_value_usd", subject_key="position:1", value_numeric=1250000.0),
            FactInput(field_name="shares_or_principal_amount", subject_key="position:1", value_numeric=1000.0),
            FactInput(field_name="position_value_usd", subject_key="position:2", value_numeric=750000.0),
            FactInput(field_name="shares_or_principal_amount", subject_key="position:2", value_numeric=600.0),
            FactInput(field_name="info_table_entry_total", subject_key="document", value_numeric=2.0),
            FactInput(field_name="info_table_value_total_usd", subject_key="document", value_numeric=2000000.0),
        ],
        evidences=[
            EvidenceInput(
                field_name="position_value_usd",
                subject_key="position:1",
                locator_kind="obj",
                source_span="infotable[0].Value",
                raw_value="1250",
                normalized_value="1250000.0",
            ),
            EvidenceInput(
                field_name="shares_or_principal_amount",
                subject_key="position:1",
                locator_kind="obj",
                source_span="infotable[0].SharesPrnAmount",
                raw_value="1000",
                normalized_value="1000.0",
            ),
            EvidenceInput(
                field_name="position_value_usd",
                subject_key="position:2",
                locator_kind="obj",
                source_span="infotable[1].Value",
                raw_value="750",
                normalized_value="750000.0",
            ),
            EvidenceInput(
                field_name="shares_or_principal_amount",
                subject_key="position:2",
                locator_kind="obj",
                source_span="infotable[1].SharesPrnAmount",
                raw_value="600",
                normalized_value="600.0",
            ),
            EvidenceInput(
                field_name="info_table_entry_total",
                subject_key="document",
                locator_kind="obj",
                source_span="summary_page.tableEntryTotal",
                raw_value="2",
                normalized_value="2.0",
            ),
            EvidenceInput(
                field_name="info_table_value_total_usd",
                subject_key="document",
                locator_kind="obj",
                source_span="summary_page.tableValueTotal",
                raw_value="2000",
                normalized_value="2000000.0",
            ),
        ],
    )

    summary = session.query(Holding13FSummary).one()
    positions = session.query(Holding13FPosition).order_by(Holding13FPosition.position_index.asc()).all()

    assert summary.accession_no == "0000000000-24-000013"
    assert summary.info_table_entry_total == 2.0
    assert summary.info_table_value_total_usd == 2000000.0
    assert positions[0].subject_key == "position:1"
    assert positions[0].position_value_usd == 1250000.0
    assert positions[0].shares_or_principal_amount == 1000.0
    assert positions[1].subject_key == "position:2"
    assert positions[1].position_value_usd == 750000.0
    assert positions[1].shares_or_principal_amount == 600.0
    assert session.query(ExtractedFact).all() == []
    assert session.query(ExtractionEvidence).all() == []


def test_persist_filing_bundle_populates_owner_345_specialized_tables() -> None:
    session = _session()
    service = PersistenceService(session)

    service.persist_filing_bundle(
        filing=_filing(),
        route="owner",
        facts=[
            FactInput(field_name="insider_transaction_quant", subject_key="document", value_text="buy", value_json='{"transaction_type":"purchase"}'),
            FactInput(field_name="insider_role_ownership_structure_quant", subject_key="document", value_text="director", value_json='{"is_director":true}'),
            FactInput(field_name="shares_acquired_or_disposed", subject_key="txn:1", value_numeric=100.0),
            FactInput(field_name="transaction_price_per_share", subject_key="txn:1", value_numeric=10.0),
            FactInput(field_name="shares_owned_following_txn", subject_key="txn:1", value_numeric=500.0),
            FactInput(field_name="non_derivative_shares_owned", subject_key="nhold:1", value_numeric=500.0),
        ],
        evidences=[
            EvidenceInput(field_name="insider_transaction_quant", subject_key="document", locator_kind="section_window", source_span="buy", raw_value="buy", normalized_value="buy"),
            EvidenceInput(field_name="insider_role_ownership_structure_quant", subject_key="document", locator_kind="section_window", source_span="director", raw_value="director", normalized_value="director"),
            EvidenceInput(field_name="shares_acquired_or_disposed", subject_key="txn:1", locator_kind="obj", source_span="transactions[0].shares", raw_value="100", normalized_value="100.0"),
            EvidenceInput(field_name="transaction_price_per_share", subject_key="txn:1", locator_kind="obj", source_span="transactions[0].price", raw_value="10", normalized_value="10.0"),
            EvidenceInput(field_name="shares_owned_following_txn", subject_key="txn:1", locator_kind="obj", source_span="transactions[0].balance", raw_value="500", normalized_value="500.0"),
            EvidenceInput(field_name="non_derivative_shares_owned", subject_key="nhold:1", locator_kind="obj", source_span="holdings[0].shares", raw_value="500", normalized_value="500.0"),
        ],
    )

    summary = session.query(Owner345Summary).one()
    txn = session.query(Owner345Transaction).one()
    pos = session.query(Owner345Position).one()
    assert summary.insider_transaction_quant_text == "buy"
    assert summary.insider_role_ownership_structure_quant_json == '{"is_director":true}'
    assert txn.subject_key == "txn:1"
    assert txn.transaction_kind == "non_derivative"
    assert txn.shares_acquired_or_disposed == 100.0
    assert pos.subject_key == "nhold:1"
    assert pos.position_kind == "non_derivative"
    assert pos.non_derivative_shares_owned == 500.0
    assert session.query(ExtractedFact).count() == 0


def test_persist_filing_bundle_populates_owner_13dg_and_144_specialized_tables() -> None:
    session = _session()
    service = PersistenceService(session)

    service.persist_filing_bundle(
        filing=_custom_filing(accession_no="0000000000-24-000015", form_type="13D"),
        route="owner",
        facts=[
            FactInput(field_name="beneficial_ownership_intent_quant", subject_key="document", value_text="activist", value_json='{"stance":"activist"}'),
            FactInput(field_name="source_of_funds_quant", subject_key="document", value_text="Cash", value_json='{"cash_pct":100}'),
            FactInput(field_name="beneficially_owned_shares", subject_key="filer:1", value_numeric=1000.0),
            FactInput(field_name="beneficial_ownership_pct", subject_key="filer:1", value_numeric=5.0),
            FactInput(field_name="proposed_sale_shares", subject_key="sale_notice:1", value_numeric=100.0),
            FactInput(field_name="market_value_sold_past_3m", subject_key="sold_past_3m:1", value_numeric=2500.0),
            FactInput(field_name="rule144_sale_plan_quant", subject_key="document", value_text="diversification", value_json='{"sale_reason":"diversification"}'),
        ],
        evidences=[
            EvidenceInput(field_name="beneficial_ownership_intent_quant", subject_key="document", locator_kind="section_window", source_span="activist", raw_value="activist", normalized_value="activist"),
            EvidenceInput(field_name="source_of_funds_quant", subject_key="document", locator_kind="section_window", source_span="Cash", raw_value="Cash", normalized_value="Cash"),
            EvidenceInput(field_name="beneficially_owned_shares", subject_key="filer:1", locator_kind="obj", source_span="xml.filer[0].shares", raw_value="1000", normalized_value="1000.0"),
            EvidenceInput(field_name="beneficial_ownership_pct", subject_key="filer:1", locator_kind="obj", source_span="xml.filer[0].pct", raw_value="5", normalized_value="5.0"),
            EvidenceInput(field_name="proposed_sale_shares", subject_key="sale_notice:1", locator_kind="obj", source_span="notice[0].shares", raw_value="100", normalized_value="100.0"),
            EvidenceInput(field_name="market_value_sold_past_3m", subject_key="sold_past_3m:1", locator_kind="obj", source_span="sold[0].value", raw_value="2500", normalized_value="2500.0"),
            EvidenceInput(field_name="rule144_sale_plan_quant", subject_key="document", locator_kind="section_window", source_span="diversification", raw_value="diversification", normalized_value="diversification"),
        ],
    )

    summary_13dg = session.query(Owner13DGSummary).one()
    rp = session.query(Owner13DGReportingPerson).one()
    summary_144 = session.query(Owner144Summary).one()
    notices = session.query(Owner144Notice).order_by(Owner144Notice.notice_kind.asc()).all()
    assert summary_13dg.beneficial_ownership_intent_quant_text == "activist"
    assert rp.subject_key == "filer:1"
    assert rp.beneficially_owned_shares == 1000.0
    assert summary_144.rule144_sale_plan_quant_json == '{"sale_reason":"diversification"}'
    assert [notice.notice_kind for notice in notices] == ["sale_notice", "sold_past_3m"]


def test_persist_filing_bundle_populates_issuer_specialized_tables() -> None:
    session = _session()
    service = PersistenceService(session)

    service.persist_filing_bundle(
        filing=_issuer_filing("S-1"),
        route="issuer",
        facts=[
            FactInput(field_name="total_revenue", subject_key="document", value_numeric=1000.0),
            FactInput(field_name="mdna_outlook_quant", subject_key="document", value_text="up", value_json='{"direction":"up"}'),
            FactInput(field_name="gross_proceeds", subject_key="document", value_numeric=5000.0),
            FactInput(field_name="use_of_proceeds_quant", subject_key="document", value_text="working capital", value_json='{"working_capital_pct":100}'),
            FactInput(field_name="deal_value", subject_key="document", value_numeric=7000.0),
            FactInput(field_name="current_event_quant", subject_key="document", value_text="agreement", value_json='{"event_type":"agreement"}'),
            FactInput(field_name="offering_price_per_share", subject_key="security:1", value_numeric=25.0),
            FactInput(field_name="proposal_votes_for", subject_key="proposal:1", value_numeric=10.0),
            FactInput(field_name="exec_total_comp", subject_key="exec:1", value_numeric=123.0),
            FactInput(field_name="holder_beneficial_ownership_shares", subject_key="holder:1", value_numeric=456.0),
            FactInput(field_name="proxy_proposal_quant", subject_key="document", value_text="election", value_json='{"proposal_type":"election"}'),
            FactInput(field_name="comp_policy_quant", subject_key="document", value_text="pay for performance", value_json='{"pay_for_performance":true}'),
        ],
        evidences=[
            EvidenceInput(field_name="total_revenue", subject_key="document", locator_kind="obj", source_span="rev", raw_value="1000", normalized_value="1000.0"),
            EvidenceInput(field_name="mdna_outlook_quant", subject_key="document", locator_kind="section_window", source_span="up", raw_value="up", normalized_value="up"),
            EvidenceInput(field_name="gross_proceeds", subject_key="document", locator_kind="obj", source_span="gross", raw_value="5000", normalized_value="5000.0"),
            EvidenceInput(field_name="use_of_proceeds_quant", subject_key="document", locator_kind="section_window", source_span="working capital", raw_value="working capital", normalized_value="working capital"),
            EvidenceInput(field_name="deal_value", subject_key="document", locator_kind="obj", source_span="deal", raw_value="7000", normalized_value="7000.0"),
            EvidenceInput(field_name="current_event_quant", subject_key="document", locator_kind="section_window", source_span="agreement", raw_value="agreement", normalized_value="agreement"),
            EvidenceInput(field_name="offering_price_per_share", subject_key="security:1", locator_kind="obj", source_span="security[0].price", raw_value="25", normalized_value="25.0"),
            EvidenceInput(field_name="proposal_votes_for", subject_key="proposal:1", locator_kind="obj", source_span="proposal[0].for", raw_value="10", normalized_value="10.0"),
            EvidenceInput(field_name="exec_total_comp", subject_key="exec:1", locator_kind="parse_text", source_span="exec[0].total", raw_value="123", normalized_value="123.0"),
            EvidenceInput(field_name="holder_beneficial_ownership_shares", subject_key="holder:1", locator_kind="parse_text", source_span="holder[0].shares", raw_value="456", normalized_value="456.0"),
            EvidenceInput(field_name="proxy_proposal_quant", subject_key="document", locator_kind="section_window", source_span="election", raw_value="election", normalized_value="election"),
            EvidenceInput(field_name="comp_policy_quant", subject_key="document", locator_kind="section_window", source_span="pay for performance", raw_value="pay for performance", normalized_value="pay for performance"),
        ],
    )

    periodic = session.query(IssuerPeriodicSummary).one()
    event = session.query(IssuerEventSummary).one()
    offering = session.query(IssuerOfferingSummary).one()
    proxy = session.query(IssuerProxySummary).one()
    assert periodic.total_revenue == 1000.0
    assert periodic.mdna_outlook_quant_json == '{"direction":"up"}'
    assert event.deal_value == 7000.0
    assert event.current_event_quant_text == "agreement"
    assert offering.gross_proceeds == 5000.0
    assert offering.use_of_proceeds_quant_text == "working capital"
    assert proxy.proxy_proposal_quant_text == "election"
    assert session.query(IssuerSecurityLine).one().offering_price_per_share == 25.0
    assert session.query(IssuerProposalVote).one().proposal_votes_for == 10.0
    assert session.query(IssuerExecComp).one().exec_total_comp == 123.0
    assert session.query(IssuerHolderOwnership).one().holder_beneficial_ownership_shares == 456.0


def test_persist_filing_bundle_creates_row_level_review_tasks_with_primary_evidence_link() -> None:
    session = _session()
    service = PersistenceService(session)

    service.persist_filing_bundle(
        filing=_filing(),
        route="owner",
        facts=[
            FactInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                value_numeric=100.0,
                confidence=0.49,
                review_reason="first_seen_template",
            ),
            FactInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:2",
                value_numeric=200.0,
                confidence=0.49,
                review_reason="first_seen_template",
            ),
        ],
        evidences=[
            EvidenceInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                locator_kind="obj",
                source_span="transactions[0].shares",
                raw_value="100",
                normalized_value="100.0",
            ),
            EvidenceInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:2",
                locator_kind="obj",
                source_span="transactions[1].shares",
                raw_value="200",
                normalized_value="200.0",
            ),
        ],
    )

    review_tasks = session.query(ReviewTask).order_by(ReviewTask.subject_key).all()
    assert len(review_tasks) == 2
    assert [task.subject_key for task in review_tasks] == ["txn:1", "txn:2"]
    assert all(task.primary_evidence_id is None for task in review_tasks)


def test_persist_filing_bundle_deduplicates_open_review_tasks_by_subject_key() -> None:
    session = _session()
    service = PersistenceService(session)
    filing = _filing()

    for numeric_value in (100.0, 101.0):
        service.persist_filing_bundle(
            filing=filing,
            route="owner",
            facts=[
                FactInput(
                    field_name="shares_acquired_or_disposed",
                    subject_key="txn:1",
                    value_numeric=numeric_value,
                    confidence=0.49,
                    review_reason="first_seen_template",
                )
            ],
            evidences=[
                EvidenceInput(
                    field_name="shares_acquired_or_disposed",
                    subject_key="txn:1",
                    locator_kind="obj",
                    source_span="transactions[0].shares",
                    raw_value=str(int(numeric_value)),
                    normalized_value=str(numeric_value),
                )
            ],
        )

    review_tasks = session.query(ReviewTask).all()
    assert len(review_tasks) == 1
    assert review_tasks[0].subject_key == "txn:1"


def test_persist_filing_bundle_persists_filing_metadata_fields() -> None:
    session = _session()
    service = PersistenceService(session)
    filing = FilingRecord(
        accession_no="0000000000-24-000011",
        cik="0000789019",
        ticker="MSFT",
        form_type="10-Q/A",
        filed_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
        accepted_at=datetime(2024, 5, 2, tzinfo=timezone.utc),
        period_end=datetime(2024, 3, 31, tzinfo=timezone.utc),
        is_amendment=True,
        amendment_no=2,
    )

    service.persist_filing_bundle(
        filing=filing,
        route="issuer",
        facts=[FactInput(field_name="total_revenue", subject_key="document", value_numeric=123.0)],
        evidences=[
            EvidenceInput(
                field_name="total_revenue",
                subject_key="document",
                locator_kind="xbrl_xml",
                source_span="xbrl-fact",
                raw_value="123",
                normalized_value="123.0",
            )
        ],
    )

    document = session.query(FilingDocument).one()
    assert _normalize_to_utc(document.filed_at) == filing.filed_at
    assert _normalize_to_utc(document.accepted_at) == filing.accepted_at
    assert _normalize_to_utc(document.period_end) == filing.period_end
    assert document.is_amendment is True
    assert document.amendment_no == 2
