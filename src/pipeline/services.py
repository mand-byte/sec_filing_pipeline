from dataclasses import dataclass
from datetime import datetime, timezone
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import (
    FilingDocument,
    Holding13FPosition,
    Holding13FSummary,
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
    ReviewTask,
)
from src.pipeline.types import FilingRecord, RouteName


@dataclass(frozen=True)
class FactInput:
    field_name: str
    subject_key: str = "document"
    value_numeric: float | None = None
    value_text: str | None = None
    value_json: str | None = None
    value_unit: str | None = None
    confidence: float | None = None
    review_priority: str | None = None
    review_reason: str | None = None


@dataclass(frozen=True)
class EvidenceInput:
    field_name: str
    locator_kind: str
    source_span: str
    subject_key: str = "document"
    source_section: str | None = None
    source_item_no: str | None = None
    source_xpath: str | None = None
    xbrl_concept: str | None = None
    source_locator_json: str | None = None
    source_heading_path_json: str | None = None
    source_block_offsets_json: str | None = None
    adequacy_signals_json: str | None = None
    retry_history_json: str | None = None
    selection_trace_json: str | None = None
    raw_value: str | None = None
    normalized_value: str | None = None


_OWNER_345_SUMMARY_FIELDS = {
    "insider_transaction_quant",
    "insider_role_ownership_structure_quant",
}
_OWNER_13DG_SUMMARY_FIELDS = {
    "beneficial_ownership_intent_quant",
    "source_of_funds_quant",
}
_OWNER_144_SUMMARY_FIELDS = {"rule144_sale_plan_quant"}
_ISSUER_PERIODIC_NUMERIC_FIELDS = {
    "total_revenue",
    "operating_income",
    "net_income",
    "diluted_eps",
    "cash_and_equivalents",
    "total_debt",
    "operating_cash_flow",
    "capex",
    "shares_outstanding",
    "filing_delay_days",
}
_ISSUER_PERIODIC_TEXT_FIELDS = {
    "mdna_outlook_quant",
    "risk_factor_quant",
    "delay_reason_quant",
}
_ISSUER_EVENT_NUMERIC_FIELDS = {
    "deal_value",
    "financing_commitment_amount",
    "termination_fee",
}
_ISSUER_EVENT_TEXT_FIELDS = {
    "current_event_quant",
    "tender_going_private_quant",
}
_ISSUER_OFFERING_NUMERIC_FIELDS = {
    "gross_proceeds",
    "net_proceeds",
    "underwriter_discount_total",
    "financing_commitment_amount",
}
_ISSUER_OFFERING_TEXT_FIELDS = {
    "use_of_proceeds_quant",
    "risk_factor_quant",
}
_ISSUER_PROXY_TEXT_FIELDS = {
    "proxy_proposal_quant",
    "comp_policy_quant",
}


class PersistenceService:
    def __init__(self, session: Session):
        """Persist extracted facts, evidences, and review tasks into the DB."""
        self.session = session

    def _upsert_filing_document(self, *, filing: FilingRecord, now: datetime) -> None:
        """Ensure the shared filing_document row exists before result persistence."""
        existing_doc = self.session.scalar(
            select(FilingDocument).where(FilingDocument.accession_no == filing.accession_no)
        )
        if existing_doc is not None:
            return
        self.session.add(
            FilingDocument(
                accession_no=filing.accession_no,
                cik=filing.cik,
                ticker=filing.ticker,
                form_type=filing.form_type,
                filed_at=filing.filed_at,
                accepted_at=filing.accepted_at,
                period_end=filing.period_end,
                is_amendment=filing.is_amendment,
                amendment_no=filing.amendment_no,
                created_at=now,
            )
        )
        self.session.flush()

    def _upsert_open_review_task(
        self,
        *,
        filing: FilingRecord,
        route: RouteName | str,
        fact: FactInput,
        now: datetime,
    ) -> None:
        """Create one open review task when low-confidence output requires human review."""
        existing_review_task = self.session.scalar(
            select(ReviewTask).where(
                ReviewTask.accession_no == filing.accession_no,
                ReviewTask.route == route,
                ReviewTask.field_name == fact.field_name,
                ReviewTask.subject_key == fact.subject_key,
                ReviewTask.status == "open",
            )
        )
        if existing_review_task is not None:
            return
        self.session.add(
            ReviewTask(
                accession_no=filing.accession_no,
                route=route,
                field_name=fact.field_name,
                subject_key=fact.subject_key,
                status="open",
                priority=fact.review_priority or "high",
                reason=fact.review_reason,
                assignee=None,
                created_at=now,
                resolved_at=None,
            )
        )

    @staticmethod
    def _is_holding_13f_bundle(*, route: RouteName | str, filing: FilingRecord) -> bool:
        """Return True when a filing should persist through the specialized 13F tables."""
        return str(route) == "holding" and filing.form_type.strip().upper().startswith("13F-HR")

    @staticmethod
    def _evidence_payload(evidence: EvidenceInput) -> dict[str, object | None]:
        """Convert one evidence input into the compact persisted JSON payload."""
        return {
            "locator_kind": evidence.locator_kind,
            "source_section": evidence.source_section,
            "source_item_no": evidence.source_item_no,
            "source_xpath": evidence.source_xpath,
            "xbrl_concept": evidence.xbrl_concept,
            "source_span": evidence.source_span,
            "source_locator_json": evidence.source_locator_json,
            "source_heading_path_json": evidence.source_heading_path_json,
            "source_block_offsets_json": evidence.source_block_offsets_json,
            "adequacy_signals_json": evidence.adequacy_signals_json,
            "retry_history_json": evidence.retry_history_json,
            "selection_trace_json": evidence.selection_trace_json,
            "raw_value": evidence.raw_value,
            "normalized_value": evidence.normalized_value,
        }

    @staticmethod
    def _fact_payload(fact: FactInput) -> object | None:
        """Project one fact into its most specific stored payload."""
        if fact.value_numeric is not None:
            return fact.value_numeric
        if fact.value_text is not None:
            return fact.value_text
        return fact.value_json

    @staticmethod
    def _document_fact_map(facts: list[FactInput]) -> dict[str, FactInput]:
        """Index document-level facts by field name."""
        return {
            fact.field_name: fact
            for fact in facts
            if fact.subject_key == "document"
        }

    def _evidence_map_by_subject(
        self,
        evidences: list[EvidenceInput],
    ) -> dict[str, dict[str, list[dict[str, object | None]]]]:
        """Group evidence payloads by subject key then field name."""
        evidence_map_by_subject: dict[str, dict[str, list[dict[str, object | None]]]] = {}
        for evidence in evidences:
            subject_map = evidence_map_by_subject.setdefault(evidence.subject_key, {})
            field_payloads = subject_map.setdefault(evidence.field_name, [])
            field_payloads.append(self._evidence_payload(evidence))
        return evidence_map_by_subject

    @staticmethod
    def _summary_numeric(summary_facts: dict[str, FactInput], field_name: str) -> float | None:
        fact = summary_facts.get(field_name)
        return float(fact.value_numeric) if fact is not None and fact.value_numeric is not None else None

    @staticmethod
    def _summary_text(summary_facts: dict[str, FactInput], field_name: str) -> str | None:
        fact = summary_facts.get(field_name)
        return fact.value_text if fact is not None else None

    @staticmethod
    def _summary_json(summary_facts: dict[str, FactInput], field_name: str) -> str | None:
        fact = summary_facts.get(field_name)
        return fact.value_json if fact is not None else None

    @staticmethod
    def _subject_ordinal(subject_key: str) -> int:
        if ":" not in subject_key:
            return 0
        _, raw = subject_key.split(":", 1)
        return int(raw) if raw.isdigit() else 0

    def _persist_holding_13f_bundle(
        self,
        *,
        filing: FilingRecord,
        route: RouteName | str,
        facts: list[FactInput],
        evidences: list[EvidenceInput],
        now: datetime,
    ) -> None:
        """Persist 13F holding outputs into specialized summary + position tables."""
        del route
        self._upsert_filing_document(filing=filing, now=now)

        evidence_map_by_subject: dict[str, dict[str, list[dict[str, object | None]]]] = {}
        for evidence in evidences:
            subject_map = evidence_map_by_subject.setdefault(evidence.subject_key, {})
            field_payloads = subject_map.setdefault(evidence.field_name, [])
            field_payloads.append(self._evidence_payload(evidence))

        summary_values: dict[str, object | None] = {}
        summary_facts = {
            fact.field_name: fact
            for fact in facts
            if fact.subject_key == "document"
        }
        position_values: dict[str, dict[str, object | None]] = {}
        for fact in facts:
            if fact.subject_key == "document":
                summary_values[fact.field_name] = fact.value_numeric if fact.value_numeric is not None else (
                    fact.value_text if fact.value_text is not None else fact.value_json
                )
            elif fact.subject_key.startswith("position:"):
                position_map = position_values.setdefault(fact.subject_key, {})
                position_map[fact.field_name] = fact.value_numeric if fact.value_numeric is not None else (
                    fact.value_text if fact.value_text is not None else fact.value_json
                )

            if fact.confidence is not None and fact.confidence < 0.5:
                self._upsert_open_review_task(
                    filing=filing,
                    route="holding",
                    fact=fact,
                    now=now,
                )

        self.session.query(Holding13FPosition).filter(
            Holding13FPosition.accession_no == filing.accession_no
        ).delete(synchronize_session=False)
        self.session.query(Holding13FSummary).filter(
            Holding13FSummary.accession_no == filing.accession_no
        ).delete(synchronize_session=False)

        summary_evidence_map = evidence_map_by_subject.get("document", {})
        self.session.add(
            Holding13FSummary(
                accession_no=filing.accession_no,
                info_table_entry_total=(
                    float(summary_values["info_table_entry_total"])
                    if summary_values.get("info_table_entry_total") is not None
                    else None
                ),
                info_table_value_total_usd=(
                    float(summary_values["info_table_value_total_usd"])
                    if summary_values.get("info_table_value_total_usd") is not None
                    else None
                ),
                other_included_managers_count=(
                    float(summary_values["other_included_managers_count"])
                    if summary_values.get("other_included_managers_count") is not None
                    else None
                ),
                manager_structure_quant_text=summary_facts["manager_structure_quant"].value_text if "manager_structure_quant" in summary_facts else None,
                manager_structure_quant_json=summary_facts["manager_structure_quant"].value_json if "manager_structure_quant" in summary_facts else None,
                amendment_scope_quant_text=summary_facts["amendment_scope_quant"].value_text if "amendment_scope_quant" in summary_facts else None,
                amendment_scope_quant_json=summary_facts["amendment_scope_quant"].value_json if "amendment_scope_quant" in summary_facts else None,
                evidence_map_json=json.dumps(summary_evidence_map, ensure_ascii=False, sort_keys=True)
                if summary_evidence_map
                else None,
                extracted_at=now,
            )
        )

        for subject_key, values in sorted(
            position_values.items(),
            key=lambda item: int(item[0].split(":", 1)[1]) if ":" in item[0] and item[0].split(":", 1)[1].isdigit() else 0,
        ):
            position_index = int(subject_key.split(":", 1)[1]) if ":" in subject_key and subject_key.split(":", 1)[1].isdigit() else 0
            evidence_map = evidence_map_by_subject.get(subject_key, {})
            self.session.add(
                Holding13FPosition(
                    accession_no=filing.accession_no,
                    subject_key=subject_key,
                    position_index=position_index,
                    position_value_usd=float(values["position_value_usd"]) if values.get("position_value_usd") is not None else None,
                    shares_or_principal_amount=float(values["shares_or_principal_amount"]) if values.get("shares_or_principal_amount") is not None else None,
                    sole_voting_auth_shares=float(values["sole_voting_auth_shares"]) if values.get("sole_voting_auth_shares") is not None else None,
                    shared_voting_auth_shares=float(values["shared_voting_auth_shares"]) if values.get("shared_voting_auth_shares") is not None else None,
                    none_voting_auth_shares=float(values["none_voting_auth_shares"]) if values.get("none_voting_auth_shares") is not None else None,
                    evidence_map_json=json.dumps(evidence_map, ensure_ascii=False, sort_keys=True) if evidence_map else None,
                    extracted_at=now,
                )
            )

        self.session.commit()

    def _persist_owner_specialized_bundle(
        self,
        *,
        filing: FilingRecord,
        route: RouteName | str,
        facts: list[FactInput],
        evidences: list[EvidenceInput],
        now: datetime,
    ) -> None:
        """Persist owner-route outputs into specialized owner tables."""
        self._upsert_filing_document(filing=filing, now=now)
        summary_facts = self._document_fact_map(facts)
        evidence_map_by_subject = self._evidence_map_by_subject(evidences)

        self.session.query(Owner345Summary).filter(Owner345Summary.accession_no == filing.accession_no).delete(synchronize_session=False)
        self.session.query(Owner345Transaction).filter(Owner345Transaction.accession_no == filing.accession_no).delete(synchronize_session=False)
        self.session.query(Owner345Position).filter(Owner345Position.accession_no == filing.accession_no).delete(synchronize_session=False)
        self.session.query(Owner13DGSummary).filter(Owner13DGSummary.accession_no == filing.accession_no).delete(synchronize_session=False)
        self.session.query(Owner13DGReportingPerson).filter(Owner13DGReportingPerson.accession_no == filing.accession_no).delete(synchronize_session=False)
        self.session.query(Owner144Summary).filter(Owner144Summary.accession_no == filing.accession_no).delete(synchronize_session=False)
        self.session.query(Owner144Notice).filter(Owner144Notice.accession_no == filing.accession_no).delete(synchronize_session=False)

        for fact in facts:
            if fact.confidence is not None and fact.confidence < 0.5:
                self._upsert_open_review_task(
                    filing=filing,
                    route=route,
                    fact=fact,
                    now=now,
                )

        if any(field in summary_facts for field in _OWNER_345_SUMMARY_FIELDS):
            self.session.add(
                Owner345Summary(
                    accession_no=filing.accession_no,
                    insider_transaction_quant_text=self._summary_text(summary_facts, "insider_transaction_quant"),
                    insider_transaction_quant_json=self._summary_json(summary_facts, "insider_transaction_quant"),
                    insider_role_ownership_structure_quant_text=self._summary_text(summary_facts, "insider_role_ownership_structure_quant"),
                    insider_role_ownership_structure_quant_json=self._summary_json(summary_facts, "insider_role_ownership_structure_quant"),
                    evidence_map_json=json.dumps(evidence_map_by_subject.get("document", {}), ensure_ascii=False, sort_keys=True)
                    if evidence_map_by_subject.get("document")
                    else None,
                    extracted_at=now,
                )
            )

        owner_345_transactions: dict[str, dict[str, object | None]] = {}
        owner_345_positions: dict[str, dict[str, object | None]] = {}
        for fact in facts:
            if fact.subject_key.startswith(("txn:", "dtxn:")):
                values = owner_345_transactions.setdefault(fact.subject_key, {})
                values[fact.field_name] = self._fact_payload(fact)
            elif fact.subject_key.startswith(("nhold:", "dhold:")):
                values = owner_345_positions.setdefault(fact.subject_key, {})
                values[fact.field_name] = self._fact_payload(fact)

        for subject_key, values in sorted(owner_345_transactions.items(), key=lambda item: self._subject_ordinal(item[0])):
            self.session.add(
                Owner345Transaction(
                    accession_no=filing.accession_no,
                    subject_key=subject_key,
                    transaction_index=self._subject_ordinal(subject_key),
                    transaction_kind="derivative" if subject_key.startswith("dtxn:") else "non_derivative",
                    shares_acquired_or_disposed=float(values["shares_acquired_or_disposed"]) if values.get("shares_acquired_or_disposed") is not None else None,
                    transaction_price_per_share=float(values["transaction_price_per_share"]) if values.get("transaction_price_per_share") is not None else None,
                    shares_owned_following_txn=float(values["shares_owned_following_txn"]) if values.get("shares_owned_following_txn") is not None else None,
                    evidence_map_json=json.dumps(evidence_map_by_subject.get(subject_key, {}), ensure_ascii=False, sort_keys=True)
                    if evidence_map_by_subject.get(subject_key)
                    else None,
                    extracted_at=now,
                )
            )

        for subject_key, values in sorted(owner_345_positions.items(), key=lambda item: self._subject_ordinal(item[0])):
            self.session.add(
                Owner345Position(
                    accession_no=filing.accession_no,
                    subject_key=subject_key,
                    position_index=self._subject_ordinal(subject_key),
                    position_kind="derivative" if subject_key.startswith("dhold:") else "non_derivative",
                    non_derivative_shares_owned=float(values["non_derivative_shares_owned"]) if values.get("non_derivative_shares_owned") is not None else None,
                    derivative_underlying_shares=float(values["derivative_underlying_shares"]) if values.get("derivative_underlying_shares") is not None else None,
                    exercise_or_conversion_price=float(values["exercise_or_conversion_price"]) if values.get("exercise_or_conversion_price") is not None else None,
                    evidence_map_json=json.dumps(evidence_map_by_subject.get(subject_key, {}), ensure_ascii=False, sort_keys=True)
                    if evidence_map_by_subject.get(subject_key)
                    else None,
                    extracted_at=now,
                )
            )

        owner_13dg_people: dict[str, dict[str, object | None]] = {}
        owner_144_notices: dict[str, dict[str, object | None]] = {}
        for fact in facts:
            if fact.subject_key.startswith("filer:"):
                values = owner_13dg_people.setdefault(fact.subject_key, {})
                values[fact.field_name] = self._fact_payload(fact)
            elif fact.subject_key.startswith(("sale_notice:", "sold_past_3m:")):
                values = owner_144_notices.setdefault(fact.subject_key, {})
                values[fact.field_name] = self._fact_payload(fact)

        if any(field in summary_facts for field in _OWNER_13DG_SUMMARY_FIELDS):
            self.session.add(
                Owner13DGSummary(
                    accession_no=filing.accession_no,
                    beneficial_ownership_intent_quant_text=self._summary_text(summary_facts, "beneficial_ownership_intent_quant"),
                    beneficial_ownership_intent_quant_json=self._summary_json(summary_facts, "beneficial_ownership_intent_quant"),
                    source_of_funds_quant_text=self._summary_text(summary_facts, "source_of_funds_quant"),
                    source_of_funds_quant_json=self._summary_json(summary_facts, "source_of_funds_quant"),
                    evidence_map_json=json.dumps(evidence_map_by_subject.get("document", {}), ensure_ascii=False, sort_keys=True)
                    if evidence_map_by_subject.get("document")
                    else None,
                    extracted_at=now,
                )
            )

        for subject_key, values in sorted(owner_13dg_people.items(), key=lambda item: self._subject_ordinal(item[0])):
            self.session.add(
                Owner13DGReportingPerson(
                    accession_no=filing.accession_no,
                    subject_key=subject_key,
                    reporting_person_index=self._subject_ordinal(subject_key),
                    beneficially_owned_shares=float(values["beneficially_owned_shares"]) if values.get("beneficially_owned_shares") is not None else None,
                    beneficial_ownership_pct=float(values["beneficial_ownership_pct"]) if values.get("beneficial_ownership_pct") is not None else None,
                    sole_voting_power=float(values["sole_voting_power"]) if values.get("sole_voting_power") is not None else None,
                    shared_voting_power=float(values["shared_voting_power"]) if values.get("shared_voting_power") is not None else None,
                    sole_dispositive_power=float(values["sole_dispositive_power"]) if values.get("sole_dispositive_power") is not None else None,
                    shared_dispositive_power=float(values["shared_dispositive_power"]) if values.get("shared_dispositive_power") is not None else None,
                    aggregate_purchase_price=float(values["aggregate_purchase_price"]) if values.get("aggregate_purchase_price") is not None else None,
                    source_of_funds_amount=float(values["source_of_funds_amount"]) if values.get("source_of_funds_amount") is not None else None,
                    evidence_map_json=json.dumps(evidence_map_by_subject.get(subject_key, {}), ensure_ascii=False, sort_keys=True)
                    if evidence_map_by_subject.get(subject_key)
                    else None,
                    extracted_at=now,
                )
            )

        if any(field in summary_facts for field in _OWNER_144_SUMMARY_FIELDS):
            self.session.add(
                Owner144Summary(
                    accession_no=filing.accession_no,
                    rule144_sale_plan_quant_text=self._summary_text(summary_facts, "rule144_sale_plan_quant"),
                    rule144_sale_plan_quant_json=self._summary_json(summary_facts, "rule144_sale_plan_quant"),
                    evidence_map_json=json.dumps(evidence_map_by_subject.get("document", {}), ensure_ascii=False, sort_keys=True)
                    if evidence_map_by_subject.get("document")
                    else None,
                    extracted_at=now,
                )
            )

        for subject_key, values in sorted(owner_144_notices.items(), key=lambda item: self._subject_ordinal(item[0])):
            self.session.add(
                Owner144Notice(
                    accession_no=filing.accession_no,
                    subject_key=subject_key,
                    notice_index=self._subject_ordinal(subject_key),
                    notice_kind="sold_past_3m" if subject_key.startswith("sold_past_3m:") else "sale_notice",
                    proposed_sale_shares=float(values["proposed_sale_shares"]) if values.get("proposed_sale_shares") is not None else None,
                    proposed_sale_market_value=float(values["proposed_sale_market_value"]) if values.get("proposed_sale_market_value") is not None else None,
                    shares_sold_past_3m=float(values["shares_sold_past_3m"]) if values.get("shares_sold_past_3m") is not None else None,
                    market_value_sold_past_3m=float(values["market_value_sold_past_3m"]) if values.get("market_value_sold_past_3m") is not None else None,
                    evidence_map_json=json.dumps(evidence_map_by_subject.get(subject_key, {}), ensure_ascii=False, sort_keys=True)
                    if evidence_map_by_subject.get(subject_key)
                    else None,
                    extracted_at=now,
                )
            )
        self.session.commit()

    def _persist_issuer_specialized_bundle(
        self,
        *,
        filing: FilingRecord,
        route: RouteName | str,
        facts: list[FactInput],
        evidences: list[EvidenceInput],
        now: datetime,
    ) -> None:
        """Persist issuer-route outputs into specialized issuer tables."""
        self._upsert_filing_document(filing=filing, now=now)
        summary_facts = self._document_fact_map(facts)
        evidence_map_by_subject = self._evidence_map_by_subject(evidences)

        self.session.query(IssuerPeriodicSummary).filter(IssuerPeriodicSummary.accession_no == filing.accession_no).delete(synchronize_session=False)
        self.session.query(IssuerEventSummary).filter(IssuerEventSummary.accession_no == filing.accession_no).delete(synchronize_session=False)
        self.session.query(IssuerOfferingSummary).filter(IssuerOfferingSummary.accession_no == filing.accession_no).delete(synchronize_session=False)
        self.session.query(IssuerProxySummary).filter(IssuerProxySummary.accession_no == filing.accession_no).delete(synchronize_session=False)
        self.session.query(IssuerSecurityLine).filter(IssuerSecurityLine.accession_no == filing.accession_no).delete(synchronize_session=False)
        self.session.query(IssuerProposalVote).filter(IssuerProposalVote.accession_no == filing.accession_no).delete(synchronize_session=False)
        self.session.query(IssuerExecComp).filter(IssuerExecComp.accession_no == filing.accession_no).delete(synchronize_session=False)
        self.session.query(IssuerHolderOwnership).filter(IssuerHolderOwnership.accession_no == filing.accession_no).delete(synchronize_session=False)

        for fact in facts:
            if fact.confidence is not None and fact.confidence < 0.5:
                self._upsert_open_review_task(
                    filing=filing,
                    route=route,
                    fact=fact,
                    now=now,
                )

        if any(field in summary_facts for field in (_ISSUER_PERIODIC_NUMERIC_FIELDS | _ISSUER_PERIODIC_TEXT_FIELDS)):
            self.session.add(
                IssuerPeriodicSummary(
                    accession_no=filing.accession_no,
                    total_revenue=self._summary_numeric(summary_facts, "total_revenue"),
                    operating_income=self._summary_numeric(summary_facts, "operating_income"),
                    net_income=self._summary_numeric(summary_facts, "net_income"),
                    diluted_eps=self._summary_numeric(summary_facts, "diluted_eps"),
                    cash_and_equivalents=self._summary_numeric(summary_facts, "cash_and_equivalents"),
                    total_debt=self._summary_numeric(summary_facts, "total_debt"),
                    operating_cash_flow=self._summary_numeric(summary_facts, "operating_cash_flow"),
                    capex=self._summary_numeric(summary_facts, "capex"),
                    shares_outstanding=self._summary_numeric(summary_facts, "shares_outstanding"),
                    filing_delay_days=self._summary_numeric(summary_facts, "filing_delay_days"),
                    mdna_outlook_quant_text=self._summary_text(summary_facts, "mdna_outlook_quant"),
                    mdna_outlook_quant_json=self._summary_json(summary_facts, "mdna_outlook_quant"),
                    risk_factor_quant_text=self._summary_text(summary_facts, "risk_factor_quant"),
                    risk_factor_quant_json=self._summary_json(summary_facts, "risk_factor_quant"),
                    delay_reason_quant_text=self._summary_text(summary_facts, "delay_reason_quant"),
                    delay_reason_quant_json=self._summary_json(summary_facts, "delay_reason_quant"),
                    evidence_map_json=json.dumps(evidence_map_by_subject.get("document", {}), ensure_ascii=False, sort_keys=True)
                    if evidence_map_by_subject.get("document")
                    else None,
                    extracted_at=now,
                )
            )

        if any(field in summary_facts for field in (_ISSUER_EVENT_NUMERIC_FIELDS | _ISSUER_EVENT_TEXT_FIELDS)):
            self.session.add(
                IssuerEventSummary(
                    accession_no=filing.accession_no,
                    deal_value=self._summary_numeric(summary_facts, "deal_value"),
                    financing_commitment_amount=self._summary_numeric(summary_facts, "financing_commitment_amount"),
                    termination_fee=self._summary_numeric(summary_facts, "termination_fee"),
                    current_event_quant_text=self._summary_text(summary_facts, "current_event_quant"),
                    current_event_quant_json=self._summary_json(summary_facts, "current_event_quant"),
                    tender_going_private_quant_text=self._summary_text(summary_facts, "tender_going_private_quant"),
                    tender_going_private_quant_json=self._summary_json(summary_facts, "tender_going_private_quant"),
                    evidence_map_json=json.dumps(evidence_map_by_subject.get("document", {}), ensure_ascii=False, sort_keys=True)
                    if evidence_map_by_subject.get("document")
                    else None,
                    extracted_at=now,
                )
            )

        if any(field in summary_facts for field in (_ISSUER_OFFERING_NUMERIC_FIELDS | _ISSUER_OFFERING_TEXT_FIELDS)):
            self.session.add(
                IssuerOfferingSummary(
                    accession_no=filing.accession_no,
                    gross_proceeds=self._summary_numeric(summary_facts, "gross_proceeds"),
                    net_proceeds=self._summary_numeric(summary_facts, "net_proceeds"),
                    underwriter_discount_total=self._summary_numeric(summary_facts, "underwriter_discount_total"),
                    financing_commitment_amount=self._summary_numeric(summary_facts, "financing_commitment_amount"),
                    use_of_proceeds_quant_text=self._summary_text(summary_facts, "use_of_proceeds_quant"),
                    use_of_proceeds_quant_json=self._summary_json(summary_facts, "use_of_proceeds_quant"),
                    risk_factor_quant_text=self._summary_text(summary_facts, "risk_factor_quant"),
                    risk_factor_quant_json=self._summary_json(summary_facts, "risk_factor_quant"),
                    evidence_map_json=json.dumps(evidence_map_by_subject.get("document", {}), ensure_ascii=False, sort_keys=True)
                    if evidence_map_by_subject.get("document")
                    else None,
                    extracted_at=now,
                )
            )

        if any(field in summary_facts for field in _ISSUER_PROXY_TEXT_FIELDS):
            self.session.add(
                IssuerProxySummary(
                    accession_no=filing.accession_no,
                    shares_outstanding=self._summary_numeric(summary_facts, "shares_outstanding"),
                    proxy_proposal_quant_text=self._summary_text(summary_facts, "proxy_proposal_quant"),
                    proxy_proposal_quant_json=self._summary_json(summary_facts, "proxy_proposal_quant"),
                    comp_policy_quant_text=self._summary_text(summary_facts, "comp_policy_quant"),
                    comp_policy_quant_json=self._summary_json(summary_facts, "comp_policy_quant"),
                    evidence_map_json=json.dumps(evidence_map_by_subject.get("document", {}), ensure_ascii=False, sort_keys=True)
                    if evidence_map_by_subject.get("document")
                    else None,
                    extracted_at=now,
                )
            )

        issuer_security_rows: dict[str, dict[str, object | None]] = {}
        issuer_proposal_rows: dict[str, dict[str, object | None]] = {}
        issuer_exec_rows: dict[str, dict[str, object | None]] = {}
        issuer_holder_rows: dict[str, dict[str, object | None]] = {}
        for fact in facts:
            if fact.subject_key.startswith("security:"):
                values = issuer_security_rows.setdefault(fact.subject_key, {})
                values[fact.field_name] = self._fact_payload(fact)
            elif fact.subject_key.startswith("proposal:"):
                values = issuer_proposal_rows.setdefault(fact.subject_key, {})
                values[fact.field_name] = self._fact_payload(fact)
            elif fact.subject_key.startswith("exec:"):
                values = issuer_exec_rows.setdefault(fact.subject_key, {})
                values[fact.field_name] = self._fact_payload(fact)
            elif fact.subject_key.startswith("holder:"):
                values = issuer_holder_rows.setdefault(fact.subject_key, {})
                values[fact.field_name] = self._fact_payload(fact)

        for subject_key, values in sorted(issuer_security_rows.items(), key=lambda item: self._subject_ordinal(item[0])):
            self.session.add(
                IssuerSecurityLine(
                    accession_no=filing.accession_no,
                    subject_key=subject_key,
                    security_index=self._subject_ordinal(subject_key),
                    offering_price_per_share=float(values["offering_price_per_share"]) if values.get("offering_price_per_share") is not None else None,
                    securities_offered_qty=float(values["securities_offered_qty"]) if values.get("securities_offered_qty") is not None else None,
                    offer_price_per_share=float(values["offer_price_per_share"]) if values.get("offer_price_per_share") is not None else None,
                    tender_shares_sought=float(values["tender_shares_sought"]) if values.get("tender_shares_sought") is not None else None,
                    evidence_map_json=json.dumps(evidence_map_by_subject.get(subject_key, {}), ensure_ascii=False, sort_keys=True)
                    if evidence_map_by_subject.get(subject_key)
                    else None,
                    extracted_at=now,
                )
            )

        for subject_key, values in sorted(issuer_proposal_rows.items(), key=lambda item: self._subject_ordinal(item[0])):
            self.session.add(
                IssuerProposalVote(
                    accession_no=filing.accession_no,
                    subject_key=subject_key,
                    proposal_index=self._subject_ordinal(subject_key),
                    proposal_votes_for=float(values["proposal_votes_for"]) if values.get("proposal_votes_for") is not None else None,
                    proposal_votes_against=float(values["proposal_votes_against"]) if values.get("proposal_votes_against") is not None else None,
                    proposal_votes_abstain=float(values["proposal_votes_abstain"]) if values.get("proposal_votes_abstain") is not None else None,
                    proposal_broker_non_votes=float(values["proposal_broker_non_votes"]) if values.get("proposal_broker_non_votes") is not None else None,
                    evidence_map_json=json.dumps(evidence_map_by_subject.get(subject_key, {}), ensure_ascii=False, sort_keys=True)
                    if evidence_map_by_subject.get(subject_key)
                    else None,
                    extracted_at=now,
                )
            )

        for subject_key, values in sorted(issuer_exec_rows.items(), key=lambda item: self._subject_ordinal(item[0])):
            self.session.add(
                IssuerExecComp(
                    accession_no=filing.accession_no,
                    subject_key=subject_key,
                    exec_index=self._subject_ordinal(subject_key),
                    exec_total_comp=float(values["exec_total_comp"]) if values.get("exec_total_comp") is not None else None,
                    evidence_map_json=json.dumps(evidence_map_by_subject.get(subject_key, {}), ensure_ascii=False, sort_keys=True)
                    if evidence_map_by_subject.get(subject_key)
                    else None,
                    extracted_at=now,
                )
            )

        for subject_key, values in sorted(issuer_holder_rows.items(), key=lambda item: self._subject_ordinal(item[0])):
            self.session.add(
                IssuerHolderOwnership(
                    accession_no=filing.accession_no,
                    subject_key=subject_key,
                    holder_index=self._subject_ordinal(subject_key),
                    holder_beneficial_ownership_shares=float(values["holder_beneficial_ownership_shares"]) if values.get("holder_beneficial_ownership_shares") is not None else None,
                    holder_beneficial_ownership_pct=float(values["holder_beneficial_ownership_pct"]) if values.get("holder_beneficial_ownership_pct") is not None else None,
                    evidence_map_json=json.dumps(evidence_map_by_subject.get(subject_key, {}), ensure_ascii=False, sort_keys=True)
                    if evidence_map_by_subject.get(subject_key)
                    else None,
                    extracted_at=now,
                )
            )
        self.session.commit()

    def persist_filing_bundle(
        self,
        *,
        filing: FilingRecord,
        route: RouteName | str,
        facts: list[FactInput],
        evidences: list[EvidenceInput],
    ) -> None:
        """Upsert one filing's extracted facts and linked evidence rows."""
        if facts and not evidences:
            raise ValueError("at least one evidence")

        if facts:
            evidence_keys = {(evidence.field_name, evidence.subject_key) for evidence in evidences}
            missing_evidence = [
                (fact.field_name, fact.subject_key)
                for fact in facts
                if (fact.field_name, fact.subject_key) not in evidence_keys
            ]
            if missing_evidence:
                raise ValueError("at least one evidence")

        now = datetime.now(timezone.utc)
        if self._is_holding_13f_bundle(route=route, filing=filing):
            self._persist_holding_13f_bundle(
                filing=filing,
                route=route,
                facts=facts,
                evidences=evidences,
                now=now,
            )
            return

        if str(route) == "owner":
            self._persist_owner_specialized_bundle(
                filing=filing,
                route=route,
                facts=facts,
                evidences=evidences,
                now=now,
            )
            return
        elif str(route) == "issuer":
            self._persist_issuer_specialized_bundle(
                filing=filing,
                route=route,
                facts=facts,
                evidences=evidences,
                now=now,
            )
            return

        raise ValueError(f"unsupported route for specialized persistence: {route}")
