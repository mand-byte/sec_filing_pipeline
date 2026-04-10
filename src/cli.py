from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from decimal import Decimal
import math
from pathlib import Path
import re
from typing import Any, cast
import xml.etree.ElementTree as ET

import pandas as pd

import typer
from sqlalchemy import func, select

from src.config import Settings
from src.db.models import PipelineLog, SecurityMaster
from src.db.repositories import PipelineRepository
from src.db.session import get_session_factory
from src.pipeline.edgar_provider import classify_form_family, fetch_filings_for_security
from src.pipeline.extraction.engine import NumericExtractionEngine
from src.pipeline.extraction.registry import all_numeric_field_specs
from src.pipeline.extraction.text_engine import TextExtractionEngine
from src.pipeline.extraction.text_registry import all_text_field_specs
from src.pipeline.review.review_gate import ReviewGateInput, evaluate_review_gate
from src.pipeline.review.stats import SqlAlchemyReviewStats
from src.pipeline.offline_artifacts import write_run_artifacts
from src.pipeline.offline_evaluator import OfflineEvalSelectors, run_offline_tier2_evaluation
from src.pipeline.golden_10q_numeric_batch import evaluate_10q_numeric_batch
from src.pipeline.routers.holding import HoldingRouter
from src.pipeline.routers.issuer import IssuerRouter
from src.pipeline.routers.owner import OwnerRouter
from src.pipeline.rules import is_filing_eligible, should_skip_delisted_route
from src.pipeline.scheduler import (
    ROUTE_ORDER,
    build_blocking_scheduler,
    make_run_id,
    ordered_routers,
    run_single_tick,
)
from src.pipeline.services import EvidenceInput, FactInput, PersistenceService
from src.pipeline.types import FilingRecord, RouteName


app = typer.Typer(help="SEC filing pipeline CLI for running phase 1 tasks.")


_ISSUER_VOTE_FIELDS = {
    "proposal_votes_for",
    "proposal_votes_against",
    "proposal_votes_abstain",
    "proposal_broker_non_votes",
}


@dataclass(frozen=True)
class FilingBundle:
    filing: FilingRecord
    facts: list[FactInput] = field(default_factory=list)
    evidences: list[EvidenceInput] = field(default_factory=list)


def _normalize_to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _as_utc_start_of_day(start_date: date) -> datetime:
    return datetime.combine(start_date, time.min, tzinfo=timezone.utc)


def _bundle_sort_key(bundle: FilingBundle) -> tuple[datetime, str]:
    return (_normalize_to_utc(bundle.filing.accepted_at), bundle.filing.accession_no)


def _coerce_numeric_value(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not cleaned:
            return None
        try:
            numeric = float(cleaned)
        except (ValueError, OverflowError):
            return None
        return numeric if math.isfinite(numeric) else None
    return None


def _owner_ownership_bundle(*, envelope: Any, filing: FilingRecord) -> FilingBundle | None:
    obj_method = getattr(envelope.filing, "obj", None)
    if not callable(obj_method):
        return None

    try:
        ownership_form = obj_method()
    except Exception:
        return None

    facts: list[FactInput] = []
    evidences: list[EvidenceInput] = []

    transactions = getattr(ownership_form, "transactions", None)
    if transactions is not None:
        if not isinstance(transactions, list):
            try:
                transactions = list(transactions)
            except Exception:
                transactions = []

        field_specs = (
            ("shares_acquired_or_disposed", ("shares", "shares_numeric"), "shares"),
            ("transaction_price_per_share", ("price_per_share", "price_numeric"), "price_per_share"),
            (
                "shares_owned_following_txn",
                ("shares_owned_following_transaction", "shares_owned_following_txn"),
                "shares_owned_following_transaction",
            ),
        )

        for index, transaction in enumerate(transactions, start=1):
            subject_key = f"txn:{index}"
            for field_name, attr_names, path_name in field_specs:
                raw_value = None
                for attr_name in attr_names:
                    raw_value = getattr(transaction, attr_name, None)
                    if raw_value is not None:
                        break
                numeric_value = _coerce_numeric_value(raw_value)
                if numeric_value is None:
                    continue
                facts.append(
                    FactInput(
                        field_name=field_name,
                        subject_key=subject_key,
                        value_numeric=numeric_value,
                        confidence=0.99,
                    )
                )
                evidences.append(
                    EvidenceInput(
                        field_name=field_name,
                        subject_key=subject_key,
                        locator_kind="obj",
                        source_span=f"transactions[{index - 1}].{path_name}",
                        raw_value=str(raw_value),
                        normalized_value=str(numeric_value),
                    )
                )

    derivative_table = getattr(ownership_form, "derivative_table", None)
    derivative_transactions = getattr(getattr(derivative_table, "transactions", None), "data", None)
    if isinstance(derivative_transactions, pd.DataFrame) and not derivative_transactions.empty:
        for index, row in enumerate(derivative_transactions.itertuples(index=False), start=1):
            subject_key = f"dtxn:{index}"
            derivative_specs = (
                ("derivative_underlying_shares", getattr(row, "UnderlyingShares", None), "UnderlyingShares"),
                ("exercise_or_conversion_price", getattr(row, "ExercisePrice", None), "ExercisePrice"),
            )
            for field_name, raw_value, path_name in derivative_specs:
                numeric_value = _coerce_numeric_value(raw_value)
                if numeric_value is None:
                    continue
                facts.append(
                    FactInput(
                        field_name=field_name,
                        subject_key=subject_key,
                        value_numeric=numeric_value,
                        confidence=0.99,
                    )
                )
                evidences.append(
                    EvidenceInput(
                        field_name=field_name,
                        subject_key=subject_key,
                        locator_kind="obj",
                        source_span=f"derivative_table.transactions[{index - 1}].{path_name}",
                        raw_value=str(raw_value),
                        normalized_value=str(numeric_value),
                    )
                )

    non_derivative_holdings = getattr(getattr(getattr(ownership_form, "non_derivative_table", None), "holdings", None), "data", None)
    if isinstance(non_derivative_holdings, pd.DataFrame) and not non_derivative_holdings.empty:
        for index, row in enumerate(non_derivative_holdings.itertuples(index=False), start=1):
            numeric_value = _coerce_numeric_value(getattr(row, "Shares", None))
            if numeric_value is None:
                continue
            subject_key = f"nhold:{index}"
            facts.append(
                FactInput(
                    field_name="non_derivative_shares_owned",
                    subject_key=subject_key,
                    value_numeric=numeric_value,
                    confidence=0.99,
                )
            )
            evidences.append(
                EvidenceInput(
                    field_name="non_derivative_shares_owned",
                    subject_key=subject_key,
                    locator_kind="obj",
                    source_span=f"non_derivative_table.holdings[{index - 1}].Shares",
                    raw_value=str(getattr(row, 'Shares', '')),
                    normalized_value=str(numeric_value),
                )
            )

    derivative_holdings = getattr(getattr(getattr(ownership_form, "derivative_table", None), "holdings", None), "data", None)
    if isinstance(derivative_holdings, pd.DataFrame) and not derivative_holdings.empty:
        for index, row in enumerate(derivative_holdings.itertuples(index=False), start=1):
            subject_key = f"dhold:{index}"
            holding_specs = (
                ("derivative_underlying_shares", getattr(row, "UnderlyingShares", None), "UnderlyingShares"),
                ("exercise_or_conversion_price", getattr(row, "ExercisePrice", None), "ExercisePrice"),
            )
            for field_name, raw_value, path_name in holding_specs:
                numeric_value = _coerce_numeric_value(raw_value)
                if numeric_value is None:
                    continue
                facts.append(
                    FactInput(
                        field_name=field_name,
                        subject_key=subject_key,
                        value_numeric=numeric_value,
                        confidence=0.99,
                    )
                )
                evidences.append(
                    EvidenceInput(
                        field_name=field_name,
                        subject_key=subject_key,
                        locator_kind="obj",
                        source_span=f"derivative_table.holdings[{index - 1}].{path_name}",
                        raw_value=str(raw_value),
                        normalized_value=str(numeric_value),
                    )
                )

    return FilingBundle(filing=filing, facts=facts, evidences=evidences)


def _holding_13f_bundle(*, envelope: Any, filing: FilingRecord) -> FilingBundle | None:
    obj_method = getattr(envelope.filing, "obj", None)
    if not callable(obj_method):
        return None

    try:
        holding_report = obj_method()
    except Exception:
        return None

    infotable = getattr(holding_report, "infotable", None)
    if not isinstance(infotable, pd.DataFrame):
        return None

    facts: list[FactInput] = []
    evidences: list[EvidenceInput] = []
    row_value_total_usd = 0.0

    if not infotable.empty:
        for index, row in enumerate(infotable.itertuples(index=False), start=1):
            subject_key = f"position:{index}"
            position_specs = (
                ("position_value_usd", getattr(row, "Value", None), "Value", 1000.0),
                ("shares_or_principal_amount", getattr(row, "SharesPrnAmount", None), "SharesPrnAmount", 1.0),
                ("sole_voting_auth_shares", getattr(row, "SoleVoting", None), "SoleVoting", 1.0),
                ("shared_voting_auth_shares", getattr(row, "SharedVoting", None), "SharedVoting", 1.0),
                ("none_voting_auth_shares", getattr(row, "NonVoting", None), "NonVoting", 1.0),
            )
            for field_name, raw_value, path_name, scale in position_specs:
                numeric_value = _coerce_numeric_value(raw_value)
                if numeric_value is None:
                    continue
                normalized_value = float(numeric_value * scale)
                if field_name == "position_value_usd":
                    row_value_total_usd += normalized_value
                facts.append(
                    FactInput(
                        field_name=field_name,
                        subject_key=subject_key,
                        value_numeric=normalized_value,
                        confidence=0.99,
                    )
                )
                evidences.append(
                    EvidenceInput(
                        field_name=field_name,
                        subject_key=subject_key,
                        locator_kind="obj",
                        source_span=f"infotable[{index - 1}].{path_name}",
                        raw_value=str(raw_value),
                        normalized_value=str(normalized_value),
                    )
                )

    summary_page = getattr(getattr(holding_report, "primary_form_information", None), "summary_page", None)
    other_included_managers_raw = getattr(summary_page, "other_included_managers_count", None)
    other_included_managers_count = _coerce_numeric_value(other_included_managers_raw)
    if other_included_managers_count is not None:
        facts.append(
            FactInput(
                field_name="other_included_managers_count",
                subject_key="document",
                value_numeric=float(other_included_managers_count),
                confidence=0.99,
            )
        )
        evidences.append(
            EvidenceInput(
                field_name="other_included_managers_count",
                subject_key="document",
                locator_kind="obj",
                source_span="summary_page.otherIncludedManagersCount",
                raw_value=str(other_included_managers_raw),
                normalized_value=str(float(other_included_managers_count)),
            )
        )

    total_holdings_raw = getattr(holding_report, "total_holdings", None)
    total_holdings = _coerce_numeric_value(total_holdings_raw)
    if total_holdings is None:
        total_holdings = float(len(infotable.index))
        total_holdings_raw = len(infotable.index)
        total_holdings_span = "infotable.row_count"
    else:
        total_holdings = float(total_holdings)
        total_holdings_span = "summary_page.tableEntryTotal"
    facts.append(
        FactInput(
            field_name="info_table_entry_total",
            subject_key="document",
            value_numeric=total_holdings,
            confidence=0.99,
        )
    )
    evidences.append(
        EvidenceInput(
            field_name="info_table_entry_total",
            subject_key="document",
            locator_kind="obj",
            source_span=total_holdings_span,
            raw_value=str(total_holdings_raw),
            normalized_value=str(total_holdings),
        )
    )

    total_value_raw = getattr(holding_report, "total_value", None)
    total_value = _coerce_numeric_value(total_value_raw)
    if total_value is None:
        total_value_usd = row_value_total_usd
        total_value_raw = row_value_total_usd / 1000.0
        total_value_span = "infotable.Value"
    else:
        total_value_usd = float(total_value * 1000.0)
        total_value_span = "summary_page.tableValueTotal"
    facts.append(
        FactInput(
            field_name="info_table_value_total_usd",
            subject_key="document",
            value_numeric=total_value_usd,
            confidence=0.99,
        )
    )
    evidences.append(
        EvidenceInput(
            field_name="info_table_value_total_usd",
            subject_key="document",
            locator_kind="obj",
            source_span=total_value_span,
            raw_value=str(total_value_raw),
            normalized_value=str(total_value_usd),
        )
    )

    return FilingBundle(filing=filing, facts=facts, evidences=evidences)


def _strip_namespace(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _xml_root(xml_text: str) -> ET.Element | None:
    try:
        return ET.fromstring(xml_text)
    except ET.ParseError:
        return None


def _xml_findall(element: ET.Element, tag_name: str) -> list[ET.Element]:
    return [child for child in element.iter() if _strip_namespace(child.tag) == tag_name]


def _xml_child_text(element: ET.Element, tag_name: str) -> str | None:
    for child in element.iter():
        if _strip_namespace(child.tag) != tag_name:
            continue
        if child.text is None:
            continue
        text = child.text.strip()
        if text:
            return text
    return None


def _xml_direct_child_text(element: ET.Element, tag_name: str) -> str | None:
    for child in list(element):
        if _strip_namespace(child.tag) != tag_name:
            continue
        if child.text is None:
            continue
        text = child.text.strip()
        if text:
            return text
    return None


def _extract_monetary_amount(text: str | None) -> float | None:
    if not isinstance(text, str):
        return None

    normalized_text = " ".join(text.split())
    anchored_currency_patterns = (
        r"(?i)(?:total\s+funds\s+used|aggregate\s+purchase\s+price|purchase\s+price|source\s+and\s+amount\s+of\s+funds|reporting\s+person\s+used)\D{0,32}\$\s*([-+]?\d[\d,]*(?:\.\d+)?)",
        r"(?i)\$\s*([-+]?\d[\d,]*(?:\.\d+)?)\D{0,32}(?:in\s+cash|of\s+working\s+capital|from\s+working\s+capital|aggregate\s+purchase\s+price|purchase\s+price)",
    )
    for pattern in anchored_currency_patterns:
        match = re.search(pattern, normalized_text)
        if match is None:
            continue
        numeric_value = _coerce_numeric_value(match.group(1))
        if numeric_value is not None:
            return float(numeric_value)

    currency_matches = [
        _coerce_numeric_value(match.group(1))
        for match in re.finditer(r"\$\s*([-+]?\d[\d,]*(?:\.\d+)?)", normalized_text)
    ]
    currency_candidates = [value for value in currency_matches if value is not None]
    if len(currency_candidates) == 1:
        return float(currency_candidates[0])
    if len(currency_candidates) > 1:
        return None

    anchored_plain_patterns = (
        r"(?i)(?:total\s+funds\s+used|aggregate\s+purchase\s+price|purchase\s+price|reporting\s+person\s+used)\D{0,16}([-+]?\d{1,3}(?:,\d{3})+|[-+]?\d{5,}(?:\.\d+)?)",
    )
    for pattern in anchored_plain_patterns:
        match = re.search(pattern, normalized_text)
        if match is None:
            continue
        numeric_value = _coerce_numeric_value(match.group(1))
        if numeric_value is not None:
            return float(numeric_value)

    return None


def _owner_schedule_13dg_bundle(*, envelope: Any, filing: FilingRecord, form_family: str) -> FilingBundle | None:
    xml_method = getattr(envelope.filing, "xml", None)
    if not callable(xml_method):
        return None

    try:
        xml_text = xml_method()
    except Exception:
        return None

    if not isinstance(xml_text, str) or not xml_text.strip():
        return None

    root = _xml_root(xml_text)
    if root is None:
        return None

    if form_family == "13G":
        person_blocks = _xml_findall(root, "coverPageHeaderReportingPersonDetails")
        field_map = (
            ("beneficially_owned_shares", "reportingPersonBeneficiallyOwnedAggregateNumberOfShares"),
            ("beneficial_ownership_pct", "classPercent"),
            ("sole_voting_power", "soleVotingPower"),
            ("shared_voting_power", "sharedVotingPower"),
            ("sole_dispositive_power", "soleDispositivePower"),
            ("shared_dispositive_power", "sharedDispositivePower"),
        )
    else:
        person_blocks = _xml_findall(root, "reportingPerson")
        if not person_blocks:
            person_blocks = _xml_findall(root, "coverPageReportingPerson")
        field_map = (
            ("beneficially_owned_shares", "aggregateAmountOwned"),
            ("beneficial_ownership_pct", "percentOfClass"),
            ("sole_voting_power", "soleVotingPower"),
            ("shared_voting_power", "sharedVotingPower"),
            ("sole_dispositive_power", "soleDispositivePower"),
            ("shared_dispositive_power", "sharedDispositivePower"),
        )

    facts: list[FactInput] = []
    evidences: list[EvidenceInput] = []

    for index, block in enumerate(person_blocks, start=1):
        subject_key = f"filer:{index}"
        for field_name, tag_name in field_map:
            raw_value = _xml_child_text(block, tag_name)
            numeric_value = _coerce_numeric_value(raw_value)
            if numeric_value is None:
                continue
            facts.append(
                FactInput(
                    field_name=field_name,
                    subject_key=subject_key,
                    value_numeric=float(numeric_value),
                    confidence=0.99,
                )
            )
            evidences.append(
                EvidenceInput(
                    field_name=field_name,
                    subject_key=subject_key,
                    locator_kind="obj",
                    source_span=f"xml.{_strip_namespace(block.tag)}[{index - 1}].{tag_name}",
                    raw_value=str(raw_value),
                    normalized_value=str(float(numeric_value)),
                )
            )

        if form_family != "13D":
            continue

        funds_source_text = _xml_child_text(block, "fundsSource")
        funds_amount = _extract_monetary_amount(funds_source_text)
        if funds_amount is not None:
            facts.append(
                FactInput(
                    field_name="source_of_funds_amount",
                    subject_key=subject_key,
                    value_numeric=float(funds_amount),
                    confidence=0.99,
                )
            )
            evidences.append(
                EvidenceInput(
                    field_name="source_of_funds_amount",
                    subject_key=subject_key,
                    locator_kind="obj",
                    source_span=f"xml.{_strip_namespace(block.tag)}[{index - 1}].fundsSource",
                    raw_value=str(funds_source_text),
                    normalized_value=str(float(funds_amount)),
                )
            )

    if form_family == "13D":
        funds_source_text = _xml_direct_child_text(root, "fundsSource")
        aggregate_purchase_price = _extract_monetary_amount(funds_source_text)
        if aggregate_purchase_price is not None:
            facts.append(
                FactInput(
                    field_name="aggregate_purchase_price",
                    subject_key="document",
                    value_numeric=float(aggregate_purchase_price),
                    confidence=0.99,
                )
            )
            evidences.append(
                EvidenceInput(
                    field_name="aggregate_purchase_price",
                    subject_key="document",
                    locator_kind="obj",
                    source_span="xml.fundsSource",
                    raw_value=str(funds_source_text),
                    normalized_value=str(float(aggregate_purchase_price)),
                )
            )

    return FilingBundle(filing=filing, facts=facts, evidences=evidences)


def _owner_form144_bundle(*, envelope: Any, filing: FilingRecord) -> FilingBundle | None:
    obj_method = getattr(envelope.filing, "obj", None)
    if not callable(obj_method):
        return None

    try:
        form144 = obj_method()
    except Exception:
        return None

    facts: list[FactInput] = []
    evidences: list[EvidenceInput] = []

    securities_information = getattr(form144, "securities_information", None)
    if isinstance(securities_information, pd.DataFrame) and not securities_information.empty:
        for index, row in enumerate(securities_information.itertuples(index=False), start=1):
            subject_key = f"sale_notice:{index}"
            sale_specs = (
                ("proposed_sale_shares", getattr(row, "units_to_be_sold", None), "securities_information.units_to_be_sold"),
                ("proposed_sale_market_value", getattr(row, "market_value", None), "securities_information.market_value"),
            )
            for field_name, raw_value, path_name in sale_specs:
                numeric_value = _coerce_numeric_value(raw_value)
                if numeric_value is None:
                    continue
                facts.append(
                    FactInput(
                        field_name=field_name,
                        subject_key=subject_key,
                        value_numeric=float(numeric_value),
                        confidence=0.99,
                    )
                )
                evidences.append(
                    EvidenceInput(
                        field_name=field_name,
                        subject_key=subject_key,
                        locator_kind="obj",
                        source_span=f"{path_name}[{index - 1}]",
                        raw_value=str(raw_value),
                        normalized_value=str(float(numeric_value)),
                    )
                )

    securities_sold = getattr(form144, "securities_sold_past_3_months", None)
    if isinstance(securities_sold, pd.DataFrame) and not securities_sold.empty:
        for index, row in enumerate(securities_sold.itertuples(index=False), start=1):
            subject_key = f"sold_past_3m:{index}"
            sold_specs = (
                ("shares_sold_past_3m", getattr(row, "amount_sold", None), "securities_sold_past_3_months.amount_sold"),
                ("market_value_sold_past_3m", getattr(row, "gross_proceeds", None), "securities_sold_past_3_months.gross_proceeds"),
            )
            for field_name, raw_value, path_name in sold_specs:
                numeric_value = _coerce_numeric_value(raw_value)
                if numeric_value is None:
                    continue
                facts.append(
                    FactInput(
                        field_name=field_name,
                        subject_key=subject_key,
                        value_numeric=float(numeric_value),
                        confidence=0.99,
                    )
                )
                evidences.append(
                    EvidenceInput(
                        field_name=field_name,
                        subject_key=subject_key,
                        locator_kind="obj",
                        source_span=f"{path_name}[{index - 1}]",
                        raw_value=str(raw_value),
                        normalized_value=str(float(numeric_value)),
                    )
                )

    return FilingBundle(filing=filing, facts=facts, evidences=evidences)


def _issuer_8k_vote_bundle(*, envelope: Any, filing: FilingRecord) -> tuple[FilingBundle | None, bool]:
    obj_method = getattr(envelope.filing, "obj", None)
    if not callable(obj_method):
        return None, False

    try:
        report = obj_method()
    except Exception:
        return None, False

    items = getattr(report, "items", None)
    item_key: str | None = None
    if isinstance(items, list):
        for candidate in items:
            candidate_text = str(candidate)
            normalized_candidate = candidate_text.upper().replace(" ", "")
            if normalized_candidate in {"ITEM5.07", "5.07", "ITEM5.07."}:
                item_key = candidate_text
                break
            if "5.07" in normalized_candidate:
                item_key = candidate_text
                break

    item_present = item_key is not None
    if not item_present:
        return FilingBundle(filing=filing, facts=[], evidences=[]), False

    try:
        item_text = report[item_key]
    except Exception:
        return FilingBundle(filing=filing, facts=[], evidences=[]), True

    if not isinstance(item_text, str) or not item_text.strip():
        return FilingBundle(filing=filing, facts=[], evidences=[]), True

    facts: list[FactInput] = []
    evidences: list[EvidenceInput] = []
    lines = [line.strip() for line in item_text.splitlines() if line.strip()]
    proposal_index = 0

    for line_number, line in enumerate(lines, start=1):
        all_numeric_tokens = [
            match.group(0)
            for match in re.finditer(r"\d[\d,]*", line)
        ]
        if len(all_numeric_tokens) < 3:
            continue

        selected_token_values: list[str] | None = None
        for count in (4, 3):
            if len(all_numeric_tokens) < count:
                continue
            candidate_tokens = all_numeric_tokens[-count:]
            token_pattern = r"\s+".join(re.escape(token) for token in candidate_tokens)
            trailing_vote_match = re.match(
                rf"^(?P<label>.+?)\s+(?P<tail>{token_pattern})\s*$",
                line,
            )
            if trailing_vote_match is None:
                continue
            label = trailing_vote_match.group("label").strip()
            if not label or not re.search(r"[A-Za-z]", label):
                continue
            selected_token_values = candidate_tokens
            break

        if selected_token_values is None:
            continue

        selected_numeric_values: list[float] = []
        for token in selected_token_values:
            numeric_value = _coerce_numeric_value(token)
            if numeric_value is None:
                selected_numeric_values = []
                break
            selected_numeric_values.append(float(numeric_value))

        if len(selected_numeric_values) < 3:
            continue

        proposal_index += 1
        subject_key = f"proposal:{proposal_index}"
        field_values = [
            ("proposal_votes_for", selected_numeric_values[0]),
            ("proposal_votes_against", selected_numeric_values[1]),
            ("proposal_votes_abstain", selected_numeric_values[2]),
        ]
        if len(selected_numeric_values) >= 4:
            field_values.append(("proposal_broker_non_votes", selected_numeric_values[3]))

        for field_name, numeric_value in field_values:
            facts.append(
                FactInput(
                    field_name=field_name,
                    subject_key=subject_key,
                    value_numeric=numeric_value,
                    confidence=0.99,
                )
            )
            evidences.append(
                EvidenceInput(
                    field_name=field_name,
                    subject_key=subject_key,
                    locator_kind="obj",
                    source_span=f"items[{item_key}].line[{line_number}]",
                    source_item_no="5.07",
                    raw_value=line,
                    normalized_value=str(numeric_value),
                )
            )

    return FilingBundle(filing=filing, facts=facts, evidences=evidences), item_present


def _load_run_once_securities(session: Any) -> list[SecurityMaster]:
    return list(
        session.scalars(
            select(SecurityMaster).order_by(
                SecurityMaster.cik.asc(),
                SecurityMaster.composite_figi.asc(),
            )
        ).all()
    )


def _load_route_filing_bundles(
    *,
    security: Any,
    route: RouteName,
    start_accepted_at: datetime,
) -> list[FilingBundle]:
    del start_accepted_at
    bundles_by_route = getattr(security, "filing_bundles_by_route", None)
    if not isinstance(bundles_by_route, dict):
        return []

    bundles = bundles_by_route.get(route, [])
    if not isinstance(bundles, list):
        return []

    return sorted(
        [bundle for bundle in bundles if isinstance(bundle, FilingBundle)],
        key=_bundle_sort_key,
    )


def _build_bundles_from_provider(
    *,
    security: Any,
    route: RouteName,
    start_accepted_at: datetime,
    repo: PipelineRepository,
    run_id: str,
) -> list[FilingBundle]:
    envelopes = fetch_filings_for_security(
        security=security,
        route=route,
        start_accepted_at=start_accepted_at,
    )
    if not envelopes:
        return []

    numeric_engine = NumericExtractionEngine()
    text_engine = TextExtractionEngine()
    route_numeric_specs = tuple(
        sorted(
            (spec for spec in all_numeric_field_specs() if spec.route == route),
            key=lambda spec: spec.field_name,
        )
    )
    route_text_specs = tuple(
        sorted(
            (spec for spec in all_text_field_specs() if spec.route == route),
            key=lambda spec: spec.field_name,
        )
    )

    bundles: list[FilingBundle] = []
    for envelope in sorted(
        envelopes,
        key=lambda env: (_normalize_to_utc(env.accepted_at), env.accession_no),
    ):
        filing = FilingRecord(
            accession_no=envelope.accession_no,
            cik=envelope.cik,
            ticker=getattr(security, "ticker", None),
            form_type=envelope.form_type,
            filed_at=None,
            accepted_at=envelope.accepted_at,
            period_end=None,
            is_amendment=envelope.form_type.endswith("/A"),
            amendment_no=None,
        )

        facts: list[FactInput] = []
        evidences: list[EvidenceInput] = []
        form_family = classify_form_family(envelope.form_type)
        if route == "owner" and form_family in {"3", "4", "5"}:
            owner_bundle = _owner_ownership_bundle(envelope=envelope, filing=filing)
            if owner_bundle is None:
                _safe_write_log(
                    repo,
                    run_id=run_id,
                    route=route,
                    stage="extract",
                    level="ERROR",
                    message="owner ownership extraction failed",
                    cik=envelope.cik,
                    accession_no=envelope.accession_no,
                    error_type="OWNERSHIP_OBJ_UNAVAILABLE",
                )
                continue
            if not owner_bundle.facts:
                _safe_write_log(
                    repo,
                    run_id=run_id,
                    route=route,
                    stage="extract",
                    level="ERROR",
                    message="owner ownership extracted no rows",
                    cik=envelope.cik,
                    accession_no=envelope.accession_no,
                    error_type="NO_OWNER_ROWS_EXTRACTED",
                )
                continue
            bundles.append(owner_bundle)
            continue

        if route == "owner" and form_family in {"13D", "13G"}:
            schedule_bundle = _owner_schedule_13dg_bundle(
                envelope=envelope,
                filing=filing,
                form_family=form_family,
            )
            if schedule_bundle is None:
                _safe_write_log(
                    repo,
                    run_id=run_id,
                    route=route,
                    stage="extract",
                    level="ERROR",
                    message="owner schedule extraction failed",
                    cik=envelope.cik,
                    accession_no=envelope.accession_no,
                    error_type="OWNER_XML_UNAVAILABLE",
                )
                continue
            has_owner_rows = any(
                fact.subject_key.startswith("filer:")
                for fact in schedule_bundle.facts
            )
            if not has_owner_rows:
                _safe_write_log(
                    repo,
                    run_id=run_id,
                    route=route,
                    stage="extract",
                    level="ERROR",
                    message="owner schedule extracted no rows",
                    cik=envelope.cik,
                    accession_no=envelope.accession_no,
                    error_type="NO_OWNER_ROWS_EXTRACTED",
                )
                continue
            facts.extend(schedule_bundle.facts)
            evidences.extend(schedule_bundle.evidences)

        if route == "owner" and form_family == "144":
            form144_bundle = _owner_form144_bundle(envelope=envelope, filing=filing)
            if form144_bundle is None:
                _safe_write_log(
                    repo,
                    run_id=run_id,
                    route=route,
                    stage="extract",
                    level="ERROR",
                    message="owner form144 extraction failed",
                    cik=envelope.cik,
                    accession_no=envelope.accession_no,
                    error_type="OWNER_OBJ_UNAVAILABLE",
                )
                continue
            has_sale_rows = any(
                fact.subject_key.startswith("sale_notice:") or fact.subject_key.startswith("sold_past_3m:")
                for fact in form144_bundle.facts
            )
            if not has_sale_rows:
                _safe_write_log(
                    repo,
                    run_id=run_id,
                    route=route,
                    stage="extract",
                    level="ERROR",
                    message="owner form144 extracted no rows",
                    cik=envelope.cik,
                    accession_no=envelope.accession_no,
                    error_type="NO_OWNER_ROWS_EXTRACTED",
                )
                continue
            bundles.append(form144_bundle)
            continue

        if route == "issuer" and form_family == "8-K":
            vote_bundle, vote_item_present = _issuer_8k_vote_bundle(
                envelope=envelope,
                filing=filing,
            )
            if vote_bundle is not None:
                has_vote_rows = any(
                    fact.subject_key.startswith("proposal:")
                    for fact in vote_bundle.facts
                )
                if vote_item_present and not has_vote_rows:
                    _safe_write_log(
                        repo,
                        run_id=run_id,
                        route=route,
                        stage="extract",
                        level="ERROR",
                        message="issuer 8-K vote extraction failed",
                        cik=envelope.cik,
                        accession_no=envelope.accession_no,
                        error_type="NO_VOTE_ROWS_EXTRACTED",
                    )
                if has_vote_rows:
                    facts.extend(vote_bundle.facts)
                    evidences.extend(vote_bundle.evidences)

        if route == "holding" and form_family == "13F-HR/A":
            holding_text_specs = tuple(
                spec
                for spec in route_text_specs
                if form_family in spec.form_families
            )
            for spec in holding_text_specs:
                outcome = text_engine.extract_field(filing=envelope.filing, field_spec=spec)
                if outcome["status"] != "ok":
                    _safe_write_log(
                        repo,
                        run_id=run_id,
                        route=route,
                        stage="extract",
                        level="ERROR",
                        message="text field extraction failed",
                        cik=envelope.cik,
                        accession_no=envelope.accession_no,
                        error_type=outcome["error_code"],
                    )
                    continue
                facts.append(
                    FactInput(
                        field_name=spec.field_name,
                        subject_key="document",
                        value_text=outcome["value_text"],
                        value_json=outcome["value_json"],
                        confidence=0.99,
                    )
                )
                evidences.append(
                    EvidenceInput(
                        field_name=spec.field_name,
                        subject_key="document",
                        locator_kind=outcome["locator_kind"],
                        source_span=outcome["source_span"],
                        source_xpath=outcome["locator_path"],
                        raw_value=outcome["value_text"],
                        normalized_value=outcome["value_text"],
                    )
                )

            holding_bundle = _holding_13f_bundle(envelope=envelope, filing=filing)
            if holding_bundle is None:
                _safe_write_log(
                    repo,
                    run_id=run_id,
                    route=route,
                    stage="extract",
                    level="ERROR",
                    message="holding 13F extraction failed",
                    cik=envelope.cik,
                    accession_no=envelope.accession_no,
                    error_type="HOLDING_OBJ_UNAVAILABLE",
                )
                continue
            has_position_rows = any(
                fact.subject_key.startswith("position:")
                for fact in holding_bundle.facts
            )
            if not has_position_rows:
                _safe_write_log(
                    repo,
                    run_id=run_id,
                    route=route,
                    stage="extract",
                    level="ERROR",
                    message="holding 13F amendment extracted no position rows",
                    cik=envelope.cik,
                    accession_no=envelope.accession_no,
                    error_type="NO_HOLDING_ROWS_EXTRACTED",
                )
                continue
            merged_bundle = FilingBundle(
                filing=holding_bundle.filing,
                facts=[*holding_bundle.facts, *facts],
                evidences=[*holding_bundle.evidences, *evidences],
            )
            bundles.append(merged_bundle)
            continue

        if route == "holding" and form_family == "13F-HR":
            holding_bundle = _holding_13f_bundle(envelope=envelope, filing=filing)
            if holding_bundle is None:
                _safe_write_log(
                    repo,
                    run_id=run_id,
                    route=route,
                    stage="extract",
                    level="ERROR",
                    message="holding 13F extraction failed",
                    cik=envelope.cik,
                    accession_no=envelope.accession_no,
                    error_type="HOLDING_OBJ_UNAVAILABLE",
                )
                continue
            has_position_rows = any(
                fact.subject_key.startswith("position:")
                for fact in holding_bundle.facts
            )
            if not has_position_rows:
                _safe_write_log(
                    repo,
                    run_id=run_id,
                    route=route,
                    stage="extract",
                    level="ERROR",
                    message="holding 13F extracted no rows",
                    cik=envelope.cik,
                    accession_no=envelope.accession_no,
                    error_type="NO_HOLDING_ROWS_EXTRACTED",
                )
                continue
            bundles.append(holding_bundle)
            continue

        filing_numeric_specs = route_numeric_specs
        filing_text_specs = route_text_specs
        if route == "issuer" and form_family == "10-Q":
            filing_numeric_specs = tuple(
                spec
                for spec in route_numeric_specs
                if spec.xbrl_enabled_form_families and form_family in spec.xbrl_enabled_form_families
            )
            filing_text_specs = ()
        elif route == "issuer" and form_family == "8-K":
            filing_numeric_specs = tuple(
                spec
                for spec in route_numeric_specs
                if spec.field_name not in _ISSUER_VOTE_FIELDS
            )

        for spec in filing_numeric_specs:
            if form_family not in spec.form_families:
                continue

            outcome = numeric_engine.extract_field(filing=envelope.filing, field_spec=spec)
            if outcome["status"] != "ok":
                if outcome["error_code"] != "FIELD_NOT_FOUND":
                    _safe_write_log(
                        repo,
                        run_id=run_id,
                        route=route,
                        stage="extract",
                        level="ERROR",
                        message="numeric field extraction failed",
                        cik=envelope.cik,
                        accession_no=envelope.accession_no,
                        error_type=outcome["error_code"],
                    )
                continue

            facts.append(
                FactInput(
                    field_name=spec.field_name,
                    subject_key="document",
                    value_numeric=float(outcome["value_normalized"]),
                    confidence=0.99,
                )
            )
            evidences.append(
                EvidenceInput(
                    field_name=spec.field_name,
                    subject_key="document",
                    locator_kind=outcome["locator_kind"],
                    source_span=outcome.get("source_span", outcome["locator_path"]),
                    source_xpath=outcome.get("source_xpath"),
                    xbrl_concept=outcome.get("xbrl_concept"),
                    raw_value=str(outcome["value_raw"]),
                    normalized_value=str(outcome["value_normalized"]),
                )
            )

        for spec in filing_text_specs:
            if form_family not in spec.form_families:
                continue

            outcome = text_engine.extract_field(filing=envelope.filing, field_spec=spec)
            if outcome["status"] != "ok":
                _safe_write_log(
                    repo,
                    run_id=run_id,
                    route=route,
                    stage="extract",
                    level="ERROR",
                    message="text field extraction failed",
                    cik=envelope.cik,
                    accession_no=envelope.accession_no,
                    error_type=outcome["error_code"],
                )
                continue

            facts.append(
                FactInput(
                    field_name=spec.field_name,
                    subject_key="document",
                    value_text=outcome["value_text"],
                    value_json=outcome["value_json"],
                    confidence=0.99,
                )
            )
            evidences.append(
                EvidenceInput(
                    field_name=spec.field_name,
                    subject_key="document",
                    locator_kind=outcome["locator_kind"],
                    source_span=outcome["source_span"],
                    source_xpath=outcome["locator_path"],
                    raw_value=outcome["value_text"],
                    normalized_value=outcome["value_text"],
                )
            )

        if not facts:
            if route == "issuer" and form_family == "10-Q":
                _safe_write_log(
                    repo,
                    run_id=run_id,
                    route=route,
                    stage="extract",
                    level="ERROR",
                    message="issuer 10-Q slice extracted no target fields",
                    cik=envelope.cik,
                    accession_no=envelope.accession_no,
                    error_type="NO_TARGET_FIELDS_EXTRACTED",
                )
                continue

            bundles.append(
                FilingBundle(
                    filing=filing,
                    facts=[],
                    evidences=[],
                )
            )
            continue

        bundles.append(
            FilingBundle(
                filing=filing,
                facts=facts,
                evidences=evidences,
            )
        )

    return bundles


def _safe_write_log(
    repo: PipelineRepository,
    *,
    run_id: str,
    route: RouteName,
    stage: str,
    level: str,
    message: str,
    cik: str | None = None,
    accession_no: str | None = None,
    error_type: str | None = None,
) -> None:
    try:
        repo.write_log(
            run_id=run_id,
            route=route,
            stage=stage,
            level=level,
            message=message,
            cik=cik,
            accession_no=accession_no,
            error_type=error_type,
        )
    except Exception:
        pass


def _review_metric_for_gate(fact: FactInput) -> float | None:
    if isinstance(fact.value_numeric, (int, float)) and not isinstance(fact.value_numeric, bool):
        return float(fact.value_numeric)

    if isinstance(fact.value_text, str):
        text_length = len(fact.value_text.strip())
        if text_length > 0:
            return float(text_length)

    return None


def _apply_review_gate_to_bundle(*, bundle: FilingBundle, route: RouteName, stats: SqlAlchemyReviewStats) -> None:
    form_family = classify_form_family(bundle.filing.form_type)
    text_field_names = {
        spec.field_name
        for spec in all_text_field_specs()
        if spec.route == route and form_family in spec.form_families
    }
    if not text_field_names:
        return

    evidence_by_field: dict[str, EvidenceInput] = {}
    for evidence in bundle.evidences:
        if evidence.field_name not in evidence_by_field:
            evidence_by_field[evidence.field_name] = evidence

    for index, fact in enumerate(bundle.facts):
        if fact.field_name not in text_field_names:
            continue

        evidence = evidence_by_field.get(fact.field_name)
        metric = _review_metric_for_gate(fact)
        review_decision = evaluate_review_gate(
            candidate=ReviewGateInput(
                cik=bundle.filing.cik,
                route=route,
                field_name=fact.field_name,
                template_hash=evidence.source_xpath if evidence else None,
                value_numeric=metric,
            ),
            stats=stats,
        )

        bundle.facts[index] = FactInput(
            field_name=fact.field_name,
            subject_key=fact.subject_key,
            value_numeric=fact.value_numeric,
            value_text=fact.value_text,
            value_json=fact.value_json,
            value_unit=fact.value_unit,
            confidence=0.49 if review_decision["decision"] == "needs_review" else 0.99,
            review_priority=review_decision["priority"],
            review_reason=review_decision["reason"],
        )


def _process_security_route(
    *,
    security: Any,
    route: RouteName,
    repo: PipelineRepository,
    persistence_service: PersistenceService,
    start_date: date,
    run_id: str,
) -> None:
    cik = getattr(security, "cik", None)
    if cik is None:
        return

    active_attr = getattr(security, "active", None)
    if not isinstance(active_attr, bool):
        return
    active = active_attr
    composite_figi = getattr(security, "composite_figi", None)
    delisted_utc = getattr(security, "delisted_utc", None)

    completion = None
    if composite_figi is not None:
        completion = repo.get_delisted_route_completion(
            composite_figi=composite_figi,
            cik=cik,
            route=route,
        )

    if active and completion is not None and bool(getattr(completion, "is_completed", False)):
        try:
            repo.invalidate_delisted_route_completion(
                composite_figi=composite_figi,
                cik=cik,
                route=route,
            )
        except Exception as exc:
            _safe_write_log(
                repo,
                run_id=run_id,
                route=route,
                cik=cik,
                stage="persist",
                level="ERROR",
                message="delisted completion invalidation failed",
                error_type=exc.__class__.__name__,
            )
        completion = None

    if should_skip_delisted_route(
        active=active,
        is_completed=bool(getattr(completion, "is_completed", False)),
        snapshot=getattr(completion, "delisted_utc_snapshot", None),
        current_delisted_utc=delisted_utc,
    ):
        return

    watermark = repo.get_route_watermark(cik, route)
    start_accepted_at = watermark or _as_utc_start_of_day(start_date)

    bundles = _load_route_filing_bundles(
        security=security,
        route=route,
        start_accepted_at=start_accepted_at,
    )
    if not bundles:
        bundles = _build_bundles_from_provider(
            security=security,
            route=route,
            start_accepted_at=start_accepted_at,
            repo=repo,
            run_id=run_id,
        )

    eligible_bundles: list[FilingBundle] = []
    normalized_start = _normalize_to_utc(start_accepted_at)
    for bundle in bundles:
        accepted_at = _normalize_to_utc(bundle.filing.accepted_at)
        if accepted_at <= normalized_start:
            continue
        if not is_filing_eligible(active=active, delisted_utc=delisted_utc, accepted_at=accepted_at):
            continue
        eligible_bundles.append(bundle)

    eligible_bundles.sort(key=_bundle_sort_key)

    last_seen_accepted_at = watermark
    if eligible_bundles:
        review_stats = SqlAlchemyReviewStats(repo.session)
        processed_bundles: list[FilingBundle] = []
        for bundle in eligible_bundles:
            try:
                _apply_review_gate_to_bundle(bundle=bundle, route=route, stats=review_stats)
                persistence_service.persist_filing_bundle(
                    filing=bundle.filing,
                    route=route,
                    facts=bundle.facts,
                    evidences=bundle.evidences,
                )
                processed_bundles.append(bundle)
                _safe_write_log(
                    repo,
                    run_id=run_id,
                    route=route,
                    cik=cik,
                    accession_no=bundle.filing.accession_no,
                    stage="persist",
                    level="INFO",
                    message="filing persisted",
                )
            except Exception as exc:
                try:
                    repo.session.rollback()
                except Exception:
                    pass
                _safe_write_log(
                    repo,
                    run_id=run_id,
                    route=route,
                    cik=cik,
                    accession_no=bundle.filing.accession_no,
                    stage="persist",
                    level="ERROR",
                    message="filing persistence failed",
                    error_type=exc.__class__.__name__,
                )

        if processed_bundles:
            max_accepted_at = max(
                (_normalize_to_utc(bundle.filing.accepted_at) for bundle in processed_bundles),
                key=lambda value: value,
            )
            try:
                repo.upsert_route_watermark(cik=cik, route=route, accepted_at=max_accepted_at)
                last_seen_accepted_at = max_accepted_at
            except Exception as exc:
                _safe_write_log(
                    repo,
                    run_id=run_id,
                    route=route,
                    cik=cik,
                    stage="persist",
                    level="ERROR",
                    message="watermark update failed",
                    error_type=exc.__class__.__name__,
                )

    if (not active) and composite_figi is not None:
        try:
            repo.mark_delisted_route_completed(
                composite_figi=composite_figi,
                cik=cik,
                route=route,
                delisted_utc_snapshot=delisted_utc,
                last_seen_accepted_at=last_seen_accepted_at,
            )
        except Exception as exc:
            _safe_write_log(
                repo,
                run_id=run_id,
                route=route,
                cik=cik,
                stage="persist",
                level="ERROR",
                message="delisted completion update failed",
                error_type=exc.__class__.__name__,
            )


def _build_run_artifact_payloads(*, session: Any, run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    route_rows = session.execute(
        select(PipelineLog.route, func.count())
        .where(PipelineLog.run_id == run_id, PipelineLog.stage == "persist", PipelineLog.level == "INFO")
        .group_by(PipelineLog.route)
    ).all()
    route_coverage = {route: int(count) for route, count in route_rows}

    error_rows = session.execute(
        select(PipelineLog.error_type, func.count())
        .where(PipelineLog.run_id == run_id, PipelineLog.level == "ERROR")
        .group_by(PipelineLog.error_type)
    ).all()
    error_distribution = {
        (error_type or "UNKNOWN"): int(count)
        for error_type, count in error_rows
    }

    sample_logs = session.scalars(
        select(PipelineLog)
        .where(PipelineLog.run_id == run_id)
        .order_by(PipelineLog.id.asc())
    ).all()
    samples = [
        {
            "route": row.route,
            "stage": row.stage,
            "level": row.level,
            "message": row.message,
            "cik": row.cik,
            "accession_no": row.accession_no,
            "error_type": row.error_type,
        }
        for row in sample_logs
    ]

    summary = {
        "run_id": run_id,
        "coverage": {
            "routes": route_coverage,
        },
        "errors": {
            "distribution": error_distribution,
        },
        "metrics": {
            "total_logs": len(sample_logs),
        },
    }

    diff_markdown = "# Diff\n- baseline comparison unavailable for this run"
    return summary, samples, diff_markdown


def _run_once_pipeline() -> None:
    settings = Settings()
    session_factory = get_session_factory(settings)

    router_map = {
        "issuer": IssuerRouter(),
        "owner": OwnerRouter(),
        "holding": HoldingRouter(),
    }
    routers = ordered_routers(router_map)
    typer.echo("route order: " + " -> ".join(router.name for router in routers))

    run_id = make_run_id()

    with session_factory() as session:
        repo = PipelineRepository(session)
        persistence_service = PersistenceService(session)
        securities = _load_run_once_securities(session)

        run_single_tick(
            run_id=run_id,
            securities=securities,
            routers=routers,
            repo=repo,
        )

        for security in securities:
            for route_name in ROUTE_ORDER:
                _process_security_route(
                    security=security,
                    route=cast(RouteName, route_name),
                    repo=repo,
                    persistence_service=persistence_service,
                    start_date=settings.start_date,
                    run_id=run_id,
                )

        if settings.write_offline_artifacts:
            summary_payload, sample_payload, diff_markdown = _build_run_artifact_payloads(
                session=session,
                run_id=run_id,
            )
            write_run_artifacts(
                base_dir=settings.offline_artifacts_dir,
                run_id=run_id,
                summary=summary_payload,
                by_field={},
                failures=[sample for sample in sample_payload if sample.get("level") == "ERROR"],
                candidates=sample_payload,
                diff_markdown=diff_markdown,
            )


@app.command("run-once")
def run_once() -> None:
    """Run the phase-1 pipeline once."""
    _run_once_pipeline()


def _run_strict_v2_eval(
    *,
    regex_config: str,
    golden_set: str,
    fixtures_dir: str,
    artifacts_dir: str,
    route: str | None,
    form_family: str | None,
    field_name: str | None,
    case_id: str | None,
    baseline: str | None,
    min_pass_rate: float,
) -> None:
    if not 0.0 <= min_pass_rate <= 1.0:
        raise typer.BadParameter("min_pass_rate must be between 0.0 and 1.0")

    result = run_offline_tier2_evaluation(
        regex_config_path=Path(regex_config),
        golden_set_path=Path(golden_set),
        fixtures_dir=Path(fixtures_dir),
        artifacts_dir=Path(artifacts_dir),
        selectors=OfflineEvalSelectors(
            route=route,
            form_family=form_family,
            field_name=field_name,
            case_id=case_id,
        ),
        baseline_path=Path(baseline) if baseline else None,
        min_pass_rate=min_pass_rate,
    )
    typer.echo(f"strict-v2 run_id: {result.run_id}")
    typer.echo(
        "strict-v2 metrics: "
        + f"passed={result.summary['metrics']['passed']} "
        + f"failed={result.summary['metrics']['failed']} "
        + f"gold_strict_accuracy={result.summary['metrics']['gold_strict_accuracy']:.4f} "
        + f"silver_alignment={result.summary['metrics']['silver_alignment']:.4f}"
    )


@app.command("offline-eval")
def offline_eval(
    regex_config: str = typer.Option(
        "configs/tier2/regex/default.yaml",
        "--regex-config",
        help="Path to Tier2 regex config yaml",
    ),
    golden_set: str = typer.Option(
        "configs/tier2/golden_set/default.yaml",
        "--golden-set",
        help="Path to Tier2 golden set yaml",
    ),
    fixtures_dir: str = typer.Option(
        "configs/tier2/fixtures",
        "--fixtures-dir",
        help="Directory of local fixture snapshots",
    ),
    artifacts_dir: str = typer.Option(
        "artifacts/offline",
        "--artifacts-dir",
        help="Directory for offline evaluator artifacts",
    ),
    route: str | None = typer.Option(None, "--route", help="Optional route filter"),
    form_family: str | None = typer.Option(None, "--form-family", help="Optional form family filter"),
    field_name: str | None = typer.Option(None, "--field", help="Optional field filter"),
    case_id: str | None = typer.Option(None, "--case-id", help="Optional case id filter"),
    baseline: str | None = typer.Option(None, "--baseline", help="Optional baseline summary json"),
    min_pass_rate: float = typer.Option(0.95, "--min-pass-rate", min=0.0, max=1.0, help="Minimum pass rate threshold"),
) -> None:
    """Run Tier2 offline evaluator using local fixtures and golden set."""
    _run_strict_v2_eval(
        regex_config=regex_config,
        golden_set=golden_set,
        fixtures_dir=fixtures_dir,
        artifacts_dir=artifacts_dir,
        route=route,
        form_family=form_family,
        field_name=field_name,
        case_id=case_id,
        baseline=baseline,
        min_pass_rate=min_pass_rate,
    )


@app.command("strict-v2-eval")
def strict_v2_eval(
    regex_config: str = typer.Option(
        "configs/tier2/regex/default.yaml",
        "--regex-config",
        help="Path to strict-v2 regex config yaml",
    ),
    golden_set: str = typer.Option(
        "configs/tier2/golden_set/default.yaml",
        "--golden-set",
        help="Path to strict-v2 golden set yaml",
    ),
    fixtures_dir: str = typer.Option(
        "configs/tier2/fixtures",
        "--fixtures-dir",
        help="Directory of local strict-v2 fixture snapshots",
    ),
    artifacts_dir: str = typer.Option(
        "artifacts/golden",
        "--artifacts-dir",
        help="Directory for strict-v2 artifacts",
    ),
    route: str | None = typer.Option(None, "--route", help="Optional route filter"),
    form_family: str | None = typer.Option(None, "--form-family", help="Optional form family filter"),
    field_name: str | None = typer.Option(None, "--field", help="Optional field filter"),
    case_id: str | None = typer.Option(None, "--case-id", help="Optional case id filter"),
    baseline: str | None = typer.Option(None, "--baseline", help="Optional baseline summary json"),
    min_pass_rate: float = typer.Option(0.95, "--min-pass-rate", min=0.0, max=1.0, help="Minimum pass rate threshold"),
) -> None:
    """Run strict-v2 evaluation and emit the golden artifact contract."""
    _run_strict_v2_eval(
        regex_config=regex_config,
        golden_set=golden_set,
        fixtures_dir=fixtures_dir,
        artifacts_dir=artifacts_dir,
        route=route,
        form_family=form_family,
        field_name=field_name,
        case_id=case_id,
        baseline=baseline,
        min_pass_rate=min_pass_rate,
    )


@app.command("golden-10q-numeric-batch")
def golden_10q_numeric_batch(
    golden_path: str = typer.Option(
        ...,
        "--golden-path",
        help="Path to the adjudicated 10-Q numeric batch golden set",
    ),
    snapshot_dir: str = typer.Option(
        ...,
        "--snapshot-dir",
        help="Directory containing batch_001 candidate snapshots",
    ),
) -> None:
    result = evaluate_10q_numeric_batch(
        golden_path=Path(golden_path),
        snapshot_dir=Path(snapshot_dir),
    )
    metrics = result.summary["metrics"]
    typer.echo(
        "golden metrics: "
        + f"batches={metrics['total_batches']} "
        + f"field_checks={metrics['total_field_checks']} "
        + f"candidate_recall={metrics['candidate_recall']} "
        + f"top1_accuracy={metrics['top1_accuracy']} "
        + f"batch_all_match_rate={metrics['batch_all_match_rate']}"
    )
    for field_name, field_metrics in result.by_field.items():
        typer.echo(
            "field "
            + f"{field_name}: "
            + f"candidate_recall={field_metrics['candidate_recall']} "
            + f"top1_accuracy={field_metrics['top1_accuracy']}"
        )


@app.command("schedule")
def schedule() -> None:
    """Run the phase-1 scheduler loop."""
    settings = Settings()
    scheduler = build_blocking_scheduler(
        interval_minutes=settings.scheduler_interval_minutes,
        tick_callable=run_once,
    )
    scheduler.start()


if __name__ == "__main__":
    app()
