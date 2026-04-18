from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from sqlalchemy import Text, cast, func, literal, select
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
)


@dataclass(frozen=True)
class SpecializedFieldSpec:
    model: type[Any]
    field_name: str
    subject_kind: str  # document or row
    numeric_attr: str | None = None
    text_attr: str | None = None
    json_attr: str | None = None
    subject_attr: str | None = "subject_key"
    evidence_attr: str = "evidence_map_json"


@dataclass(frozen=True)
class ParsedValue:
    route: str
    accession_no: str
    field_name: str
    subject_key: str
    value_numeric: float | None
    value_text: str | None
    value_json: str | None
    value_unit: str | None
    confidence: float | None
    evidence_payload: dict[str, Any] | None


def _spec(
    model: type[Any],
    field_name: str,
    *,
    subject_kind: str,
    numeric_attr: str | None = None,
    text_attr: str | None = None,
    json_attr: str | None = None,
) -> SpecializedFieldSpec:
    return SpecializedFieldSpec(
        model=model,
        field_name=field_name,
        subject_kind=subject_kind,
        numeric_attr=numeric_attr,
        text_attr=text_attr,
        json_attr=json_attr,
        subject_attr=None if subject_kind == "document" else "subject_key",
    )


_FIELD_SPECS: dict[str, list[SpecializedFieldSpec]] = {
    "info_table_entry_total": [_spec(Holding13FSummary, "info_table_entry_total", subject_kind="document", numeric_attr="info_table_entry_total")],
    "info_table_value_total_usd": [_spec(Holding13FSummary, "info_table_value_total_usd", subject_kind="document", numeric_attr="info_table_value_total_usd")],
    "other_included_managers_count": [_spec(Holding13FSummary, "other_included_managers_count", subject_kind="document", numeric_attr="other_included_managers_count")],
    "manager_structure_quant": [_spec(Holding13FSummary, "manager_structure_quant", subject_kind="document", text_attr="manager_structure_quant_text", json_attr="manager_structure_quant_json")],
    "amendment_scope_quant": [_spec(Holding13FSummary, "amendment_scope_quant", subject_kind="document", text_attr="amendment_scope_quant_text", json_attr="amendment_scope_quant_json")],
    "position_value_usd": [_spec(Holding13FPosition, "position_value_usd", subject_kind="row", numeric_attr="position_value_usd")],
    "shares_or_principal_amount": [_spec(Holding13FPosition, "shares_or_principal_amount", subject_kind="row", numeric_attr="shares_or_principal_amount")],
    "sole_voting_auth_shares": [_spec(Holding13FPosition, "sole_voting_auth_shares", subject_kind="row", numeric_attr="sole_voting_auth_shares")],
    "shared_voting_auth_shares": [_spec(Holding13FPosition, "shared_voting_auth_shares", subject_kind="row", numeric_attr="shared_voting_auth_shares")],
    "none_voting_auth_shares": [_spec(Holding13FPosition, "none_voting_auth_shares", subject_kind="row", numeric_attr="none_voting_auth_shares")],
    "insider_transaction_quant": [_spec(Owner345Summary, "insider_transaction_quant", subject_kind="document", text_attr="insider_transaction_quant_text", json_attr="insider_transaction_quant_json")],
    "insider_role_ownership_structure_quant": [_spec(Owner345Summary, "insider_role_ownership_structure_quant", subject_kind="document", text_attr="insider_role_ownership_structure_quant_text", json_attr="insider_role_ownership_structure_quant_json")],
    "shares_acquired_or_disposed": [_spec(Owner345Transaction, "shares_acquired_or_disposed", subject_kind="row", numeric_attr="shares_acquired_or_disposed")],
    "transaction_price_per_share": [_spec(Owner345Transaction, "transaction_price_per_share", subject_kind="row", numeric_attr="transaction_price_per_share")],
    "shares_owned_following_txn": [_spec(Owner345Transaction, "shares_owned_following_txn", subject_kind="row", numeric_attr="shares_owned_following_txn")],
    "non_derivative_shares_owned": [_spec(Owner345Position, "non_derivative_shares_owned", subject_kind="row", numeric_attr="non_derivative_shares_owned")],
    "derivative_underlying_shares": [_spec(Owner345Position, "derivative_underlying_shares", subject_kind="row", numeric_attr="derivative_underlying_shares")],
    "exercise_or_conversion_price": [_spec(Owner345Position, "exercise_or_conversion_price", subject_kind="row", numeric_attr="exercise_or_conversion_price")],
    "beneficial_ownership_intent_quant": [_spec(Owner13DGSummary, "beneficial_ownership_intent_quant", subject_kind="document", text_attr="beneficial_ownership_intent_quant_text", json_attr="beneficial_ownership_intent_quant_json")],
    "source_of_funds_quant": [_spec(Owner13DGSummary, "source_of_funds_quant", subject_kind="document", text_attr="source_of_funds_quant_text", json_attr="source_of_funds_quant_json")],
    "beneficially_owned_shares": [_spec(Owner13DGReportingPerson, "beneficially_owned_shares", subject_kind="row", numeric_attr="beneficially_owned_shares")],
    "beneficial_ownership_pct": [_spec(Owner13DGReportingPerson, "beneficial_ownership_pct", subject_kind="row", numeric_attr="beneficial_ownership_pct")],
    "sole_voting_power": [_spec(Owner13DGReportingPerson, "sole_voting_power", subject_kind="row", numeric_attr="sole_voting_power")],
    "shared_voting_power": [_spec(Owner13DGReportingPerson, "shared_voting_power", subject_kind="row", numeric_attr="shared_voting_power")],
    "sole_dispositive_power": [_spec(Owner13DGReportingPerson, "sole_dispositive_power", subject_kind="row", numeric_attr="sole_dispositive_power")],
    "shared_dispositive_power": [_spec(Owner13DGReportingPerson, "shared_dispositive_power", subject_kind="row", numeric_attr="shared_dispositive_power")],
    "aggregate_purchase_price": [_spec(Owner13DGReportingPerson, "aggregate_purchase_price", subject_kind="row", numeric_attr="aggregate_purchase_price")],
    "source_of_funds_amount": [_spec(Owner13DGReportingPerson, "source_of_funds_amount", subject_kind="row", numeric_attr="source_of_funds_amount")],
    "rule144_sale_plan_quant": [_spec(Owner144Summary, "rule144_sale_plan_quant", subject_kind="document", text_attr="rule144_sale_plan_quant_text", json_attr="rule144_sale_plan_quant_json")],
    "proposed_sale_shares": [_spec(Owner144Notice, "proposed_sale_shares", subject_kind="row", numeric_attr="proposed_sale_shares")],
    "proposed_sale_market_value": [_spec(Owner144Notice, "proposed_sale_market_value", subject_kind="row", numeric_attr="proposed_sale_market_value")],
    "shares_sold_past_3m": [_spec(Owner144Notice, "shares_sold_past_3m", subject_kind="row", numeric_attr="shares_sold_past_3m")],
    "market_value_sold_past_3m": [_spec(Owner144Notice, "market_value_sold_past_3m", subject_kind="row", numeric_attr="market_value_sold_past_3m")],
    "total_revenue": [_spec(IssuerPeriodicSummary, "total_revenue", subject_kind="document", numeric_attr="total_revenue")],
    "operating_income": [_spec(IssuerPeriodicSummary, "operating_income", subject_kind="document", numeric_attr="operating_income")],
    "net_income": [_spec(IssuerPeriodicSummary, "net_income", subject_kind="document", numeric_attr="net_income")],
    "diluted_eps": [_spec(IssuerPeriodicSummary, "diluted_eps", subject_kind="document", numeric_attr="diluted_eps")],
    "cash_and_equivalents": [_spec(IssuerPeriodicSummary, "cash_and_equivalents", subject_kind="document", numeric_attr="cash_and_equivalents")],
    "total_debt": [_spec(IssuerPeriodicSummary, "total_debt", subject_kind="document", numeric_attr="total_debt")],
    "operating_cash_flow": [_spec(IssuerPeriodicSummary, "operating_cash_flow", subject_kind="document", numeric_attr="operating_cash_flow")],
    "capex": [_spec(IssuerPeriodicSummary, "capex", subject_kind="document", numeric_attr="capex")],
    "shares_outstanding": [
        _spec(IssuerPeriodicSummary, "shares_outstanding", subject_kind="document", numeric_attr="shares_outstanding"),
        _spec(IssuerProxySummary, "shares_outstanding", subject_kind="document", numeric_attr="shares_outstanding"),
    ],
    "filing_delay_days": [_spec(IssuerPeriodicSummary, "filing_delay_days", subject_kind="document", numeric_attr="filing_delay_days")],
    "mdna_outlook_quant": [_spec(IssuerPeriodicSummary, "mdna_outlook_quant", subject_kind="document", text_attr="mdna_outlook_quant_text", json_attr="mdna_outlook_quant_json")],
    "risk_factor_quant": [
        _spec(IssuerPeriodicSummary, "risk_factor_quant", subject_kind="document", text_attr="risk_factor_quant_text", json_attr="risk_factor_quant_json"),
        _spec(IssuerOfferingSummary, "risk_factor_quant", subject_kind="document", text_attr="risk_factor_quant_text", json_attr="risk_factor_quant_json"),
    ],
    "delay_reason_quant": [_spec(IssuerPeriodicSummary, "delay_reason_quant", subject_kind="document", text_attr="delay_reason_quant_text", json_attr="delay_reason_quant_json")],
    "deal_value": [_spec(IssuerEventSummary, "deal_value", subject_kind="document", numeric_attr="deal_value")],
    "financing_commitment_amount": [
        _spec(IssuerEventSummary, "financing_commitment_amount", subject_kind="document", numeric_attr="financing_commitment_amount"),
        _spec(IssuerOfferingSummary, "financing_commitment_amount", subject_kind="document", numeric_attr="financing_commitment_amount"),
    ],
    "termination_fee": [_spec(IssuerEventSummary, "termination_fee", subject_kind="document", numeric_attr="termination_fee")],
    "current_event_quant": [_spec(IssuerEventSummary, "current_event_quant", subject_kind="document", text_attr="current_event_quant_text", json_attr="current_event_quant_json")],
    "tender_going_private_quant": [_spec(IssuerEventSummary, "tender_going_private_quant", subject_kind="document", text_attr="tender_going_private_quant_text", json_attr="tender_going_private_quant_json")],
    "gross_proceeds": [_spec(IssuerOfferingSummary, "gross_proceeds", subject_kind="document", numeric_attr="gross_proceeds")],
    "net_proceeds": [_spec(IssuerOfferingSummary, "net_proceeds", subject_kind="document", numeric_attr="net_proceeds")],
    "underwriter_discount_total": [_spec(IssuerOfferingSummary, "underwriter_discount_total", subject_kind="document", numeric_attr="underwriter_discount_total")],
    "use_of_proceeds_quant": [_spec(IssuerOfferingSummary, "use_of_proceeds_quant", subject_kind="document", text_attr="use_of_proceeds_quant_text", json_attr="use_of_proceeds_quant_json")],
    "offering_price_per_share": [_spec(IssuerSecurityLine, "offering_price_per_share", subject_kind="row", numeric_attr="offering_price_per_share")],
    "securities_offered_qty": [_spec(IssuerSecurityLine, "securities_offered_qty", subject_kind="row", numeric_attr="securities_offered_qty")],
    "offer_price_per_share": [_spec(IssuerSecurityLine, "offer_price_per_share", subject_kind="row", numeric_attr="offer_price_per_share")],
    "tender_shares_sought": [_spec(IssuerSecurityLine, "tender_shares_sought", subject_kind="row", numeric_attr="tender_shares_sought")],
    "proposal_votes_for": [_spec(IssuerProposalVote, "proposal_votes_for", subject_kind="row", numeric_attr="proposal_votes_for")],
    "proposal_votes_against": [_spec(IssuerProposalVote, "proposal_votes_against", subject_kind="row", numeric_attr="proposal_votes_against")],
    "proposal_votes_abstain": [_spec(IssuerProposalVote, "proposal_votes_abstain", subject_kind="row", numeric_attr="proposal_votes_abstain")],
    "proposal_broker_non_votes": [_spec(IssuerProposalVote, "proposal_broker_non_votes", subject_kind="row", numeric_attr="proposal_broker_non_votes")],
    "exec_total_comp": [_spec(IssuerExecComp, "exec_total_comp", subject_kind="row", numeric_attr="exec_total_comp")],
    "holder_beneficial_ownership_shares": [_spec(IssuerHolderOwnership, "holder_beneficial_ownership_shares", subject_kind="row", numeric_attr="holder_beneficial_ownership_shares")],
    "holder_beneficial_ownership_pct": [_spec(IssuerHolderOwnership, "holder_beneficial_ownership_pct", subject_kind="row", numeric_attr="holder_beneficial_ownership_pct")],
    "proxy_proposal_quant": [_spec(IssuerProxySummary, "proxy_proposal_quant", subject_kind="document", text_attr="proxy_proposal_quant_text", json_attr="proxy_proposal_quant_json")],
    "comp_policy_quant": [_spec(IssuerProxySummary, "comp_policy_quant", subject_kind="document", text_attr="comp_policy_quant_text", json_attr="comp_policy_quant_json")],
}

_FIELD_VALUE_UNITS: dict[str, str] = {
    "shares_acquired_or_disposed": "shares",
    "shares_owned_following_txn": "shares",
    "non_derivative_shares_owned": "shares",
    "derivative_underlying_shares": "shares",
    "beneficially_owned_shares": "shares",
    "beneficial_ownership_pct": "percent",
    "sole_voting_power": "shares",
    "shared_voting_power": "shares",
    "sole_dispositive_power": "shares",
    "shared_dispositive_power": "shares",
    "proposed_sale_shares": "shares",
    "shares_sold_past_3m": "shares",
    "position_value_usd": "USD",
    "info_table_value_total_usd": "USD",
    "transaction_price_per_share": "currency_per_share",
    "offering_price_per_share": "currency_per_share",
    "offer_price_per_share": "currency_per_share",
}


def _evidence_for_field(row: Any, spec: SpecializedFieldSpec, field_name: str) -> dict[str, Any] | None:
    evidence_json = getattr(row, spec.evidence_attr, None)
    if not isinstance(evidence_json, str) or not evidence_json:
        return None
    try:
        payload = json.loads(evidence_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    field_payload = payload.get(field_name)
    if isinstance(field_payload, list) and field_payload:
        return field_payload[0] if isinstance(field_payload[0], dict) else None
    if isinstance(field_payload, dict):
        return field_payload
    return None


def _specialized_row(
    session: Session,
    *,
    accession_no: str,
    field_name: str,
    subject_key: str,
) -> tuple[SpecializedFieldSpec, Any] | None:
    for spec in _FIELD_SPECS.get(field_name, ()):
        stmt = select(spec.model).where(spec.model.accession_no == accession_no)
        if spec.subject_attr is not None:
            stmt = stmt.where(getattr(spec.model, spec.subject_attr) == subject_key)
        row = session.scalar(stmt)
        if row is None:
            continue
        numeric_value = getattr(row, spec.numeric_attr) if spec.numeric_attr is not None else None
        text_value = getattr(row, spec.text_attr) if spec.text_attr is not None else None
        json_value = getattr(row, spec.json_attr) if spec.json_attr is not None else None
        if numeric_value is None and text_value is None and json_value is None:
            continue
        return spec, row
    return None


def load_parsed_value(
    *,
    session: Session,
    accession_no: str,
    route: str,
    field_name: str,
    subject_key: str = "document",
) -> ParsedValue | None:
    specialized = _specialized_row(
        session,
        accession_no=accession_no,
        field_name=field_name,
        subject_key=subject_key,
    )
    if specialized is not None:
        spec, row = specialized
        return ParsedValue(
            route=route,
            accession_no=accession_no,
            field_name=field_name,
            subject_key=subject_key,
            value_numeric=float(getattr(row, spec.numeric_attr)) if spec.numeric_attr is not None and getattr(row, spec.numeric_attr) is not None else None,
            value_text=getattr(row, spec.text_attr) if spec.text_attr is not None else None,
            value_json=getattr(row, spec.json_attr) if spec.json_attr is not None else None,
            value_unit=_FIELD_VALUE_UNITS.get(field_name),
            confidence=None,
            evidence_payload=_evidence_for_field(row, spec, field_name),
        )
    return None


def update_parsed_value(
    *,
    session: Session,
    accession_no: str,
    route: str,
    field_name: str,
    subject_key: str,
    corrected_payload: dict[str, Any],
) -> bool:
    specialized = _specialized_row(
        session,
        accession_no=accession_no,
        field_name=field_name,
        subject_key=subject_key,
    )
    if specialized is not None:
        spec, row = specialized
        if spec.numeric_attr is not None and "value_numeric" in corrected_payload:
            setattr(row, spec.numeric_attr, corrected_payload.get("value_numeric"))
        if spec.text_attr is not None and "value_text" in corrected_payload:
            setattr(row, spec.text_attr, corrected_payload.get("value_text"))
        if spec.json_attr is not None and "value_json" in corrected_payload:
            value_json = corrected_payload.get("value_json")
            setattr(row, spec.json_attr, value_json if isinstance(value_json, str) or value_json is None else json.dumps(value_json, ensure_ascii=False))
        return True

    return False


def clear_parsed_value(
    *,
    session: Session,
    accession_no: str,
    route: str,
    field_name: str,
    subject_key: str,
) -> bool:
    specialized = _specialized_row(
        session,
        accession_no=accession_no,
        field_name=field_name,
        subject_key=subject_key,
    )
    if specialized is not None:
        spec, row = specialized
        if spec.numeric_attr is not None:
            setattr(row, spec.numeric_attr, None)
        if spec.text_attr is not None:
            setattr(row, spec.text_attr, None)
        if spec.json_attr is not None:
            setattr(row, spec.json_attr, None)
        return True

    return False


def issuer_field_count(
    *,
    session: Session,
    cik: str,
    route: str,
    field_name: str,
) -> int:
    total = 0
    for spec in _FIELD_SPECS.get(field_name, ()):
        value_attr = spec.numeric_attr or spec.text_attr or spec.json_attr
        if value_attr is None:
            continue
        stmt = (
            select(func.count())
            .select_from(spec.model)
            .join(FilingDocument, FilingDocument.accession_no == spec.model.accession_no)
            .where(
                FilingDocument.cik == cik,
                getattr(spec.model, value_attr).is_not(None),
            )
        )
        total += int(session.scalar(stmt) or 0)
    if total > 0:
        return total
    return 0


def template_field_count(
    *,
    session: Session,
    template_hash: str,
    route: str,
    field_name: str,
) -> int:
    total = 0
    for spec in _FIELD_SPECS.get(field_name, ()):
        evidence_attr = getattr(spec.model, spec.evidence_attr)
        stmt = select(func.count()).select_from(spec.model).where(
            cast(evidence_attr, Text).contains(template_hash)
        )
        total += int(session.scalar(stmt) or 0)
    if total > 0:
        return total
    return 0


def numeric_history_values(
    *,
    session: Session,
    route: str,
    field_name: str,
) -> list[tuple[float | None, str | None]]:
    rows: list[tuple[float | None, str | None]] = []
    for spec in _FIELD_SPECS.get(field_name, ()):
        numeric_attr = getattr(spec.model, spec.numeric_attr) if spec.numeric_attr is not None else None
        text_attr = getattr(spec.model, spec.text_attr) if spec.text_attr is not None else None
        if numeric_attr is None and text_attr is None:
            continue
        stmt = select(
            numeric_attr if numeric_attr is not None else literal(None),
            text_attr if text_attr is not None else literal(None),
        )
        rows.extend(session.execute(stmt).all())
    if rows:
        return rows
    return []
