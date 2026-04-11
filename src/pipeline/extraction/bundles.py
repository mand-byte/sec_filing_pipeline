from __future__ import annotations

from decimal import Decimal
import math
import re
from typing import Any
import xml.etree.ElementTree as ET

import pandas as pd

from src.pipeline.route_runtime import BundleBuildOutcome, FilingBundle, _format_exception_detail
from src.pipeline.services import EvidenceInput, FactInput
from src.pipeline.types import FilingRecord


def coerce_numeric_value(value: object) -> float | None:
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


def build_owner_ownership_bundle(*, envelope: Any, filing: FilingRecord) -> BundleBuildOutcome:
    obj_method = getattr(envelope.filing, "obj", None)
    if not callable(obj_method):
        return BundleBuildOutcome(bundle=None)

    try:
        ownership_form = obj_method()
    except Exception as exc:
        return BundleBuildOutcome(bundle=None, error_detail=_format_exception_detail(exc))

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
                numeric_value = coerce_numeric_value(raw_value)
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
                numeric_value = coerce_numeric_value(raw_value)
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
            numeric_value = coerce_numeric_value(getattr(row, "Shares", None))
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
                    raw_value=str(getattr(row, "Shares", "")),
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
                numeric_value = coerce_numeric_value(raw_value)
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

    return BundleBuildOutcome(bundle=FilingBundle(filing=filing, facts=facts, evidences=evidences))


def build_holding_13f_bundle(*, envelope: Any, filing: FilingRecord) -> BundleBuildOutcome:
    obj_method = getattr(envelope.filing, "obj", None)
    if not callable(obj_method):
        return BundleBuildOutcome(bundle=None)

    try:
        holding_report = obj_method()
    except Exception as exc:
        return BundleBuildOutcome(bundle=None, error_detail=_format_exception_detail(exc))

    infotable = getattr(holding_report, "infotable", None)
    if not isinstance(infotable, pd.DataFrame):
        return BundleBuildOutcome(bundle=None)

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
                numeric_value = coerce_numeric_value(raw_value)
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
    other_included_managers_count = coerce_numeric_value(other_included_managers_raw)
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
    total_holdings = coerce_numeric_value(total_holdings_raw)
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
    total_value = coerce_numeric_value(total_value_raw)
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

    return BundleBuildOutcome(bundle=FilingBundle(filing=filing, facts=facts, evidences=evidences))


def build_issuer_8k_vote_bundle(*, envelope: Any, filing: FilingRecord) -> BundleBuildOutcome:
    obj_method = getattr(envelope.filing, "obj", None)
    if not callable(obj_method):
        return BundleBuildOutcome(bundle=None)

    try:
        report = obj_method()
    except Exception as exc:
        return BundleBuildOutcome(bundle=None, error_detail=_format_exception_detail(exc))

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
        return BundleBuildOutcome(
            bundle=FilingBundle(filing=filing, facts=[], evidences=[]),
            item_present=False,
        )

    try:
        item_text = report[item_key]
    except Exception as exc:
        return BundleBuildOutcome(
            bundle=FilingBundle(filing=filing, facts=[], evidences=[]),
            error_detail=_format_exception_detail(exc),
            item_present=True,
        )

    if not isinstance(item_text, str) or not item_text.strip():
        return BundleBuildOutcome(
            bundle=FilingBundle(filing=filing, facts=[], evidences=[]),
            item_present=True,
        )

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
            numeric_value = coerce_numeric_value(token)
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

    return BundleBuildOutcome(
        bundle=FilingBundle(filing=filing, facts=facts, evidences=evidences),
        item_present=item_present,
    )


def strip_namespace(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def xml_root(xml_text: str) -> ET.Element | None:
    try:
        return ET.fromstring(xml_text)
    except ET.ParseError:
        return None


def xml_findall(element: ET.Element, tag_name: str) -> list[ET.Element]:
    return [child for child in element.iter() if strip_namespace(child.tag) == tag_name]


def xml_child_text(element: ET.Element, tag_name: str) -> str | None:
    for child in element.iter():
        if strip_namespace(child.tag) != tag_name:
            continue
        if child.text is None:
            continue
        text = child.text.strip()
        if text:
            return text
    return None


def xml_direct_child_text(element: ET.Element, tag_name: str) -> str | None:
    for child in list(element):
        if strip_namespace(child.tag) != tag_name:
            continue
        if child.text is None:
            continue
        text = child.text.strip()
        if text:
            return text
    return None


def extract_monetary_amount(text: str | None) -> float | None:
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
        numeric_value = coerce_numeric_value(match.group(1))
        if numeric_value is not None:
            return float(numeric_value)

    currency_matches = [
        coerce_numeric_value(match.group(1))
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
        numeric_value = coerce_numeric_value(match.group(1))
        if numeric_value is not None:
            return float(numeric_value)

    return None


def build_owner_schedule_13dg_bundle(*, envelope: Any, filing: FilingRecord, form_family: str) -> BundleBuildOutcome:
    xml_method = getattr(envelope.filing, "xml", None)
    if not callable(xml_method):
        return BundleBuildOutcome(bundle=None)

    try:
        xml_text = xml_method()
    except Exception as exc:
        return BundleBuildOutcome(bundle=None, error_detail=_format_exception_detail(exc))

    if not isinstance(xml_text, str) or not xml_text.strip():
        return BundleBuildOutcome(bundle=None)

    root = xml_root(xml_text)
    if root is None:
        return BundleBuildOutcome(bundle=None)

    if form_family == "13G":
        person_blocks = xml_findall(root, "coverPageHeaderReportingPersonDetails")
        field_map = (
            ("beneficially_owned_shares", "reportingPersonBeneficiallyOwnedAggregateNumberOfShares"),
            ("beneficial_ownership_pct", "classPercent"),
            ("sole_voting_power", "soleVotingPower"),
            ("shared_voting_power", "sharedVotingPower"),
            ("sole_dispositive_power", "soleDispositivePower"),
            ("shared_dispositive_power", "sharedDispositivePower"),
        )
    else:
        person_blocks = xml_findall(root, "reportingPerson")
        if not person_blocks:
            person_blocks = xml_findall(root, "coverPageReportingPerson")
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
    emitted_source_of_funds_subjects: set[str] = set()
    emitted_aggregate_purchase_subjects: set[str] = set()

    def append_13d_funds_amount_fact(
        *,
        field_name: str,
        subject_key: str,
        source_span: str,
        raw_value: str | None,
        numeric_value: float,
    ) -> None:
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
                source_span=source_span,
                raw_value=str(raw_value),
                normalized_value=str(float(numeric_value)),
            )
        )

    for index, block in enumerate(person_blocks, start=1):
        subject_key = f"filer:{index}"
        for field_name, tag_name in field_map:
            raw_value = xml_child_text(block, tag_name)
            numeric_value = coerce_numeric_value(raw_value)
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
                    source_span=f"xml.{strip_namespace(block.tag)}[{index - 1}].{tag_name}",
                    raw_value=str(raw_value),
                    normalized_value=str(float(numeric_value)),
                )
            )

        if form_family != "13D":
            continue

        funds_source_text = xml_child_text(block, "fundsSource")
        funds_amount = extract_monetary_amount(funds_source_text)
        if funds_amount is not None:
            source_span = f"xml.{strip_namespace(block.tag)}[{index - 1}].fundsSource"
            append_13d_funds_amount_fact(
                field_name="source_of_funds_amount",
                subject_key=subject_key,
                source_span=source_span,
                raw_value=funds_source_text,
                numeric_value=float(funds_amount),
            )
            emitted_source_of_funds_subjects.add(subject_key)
            append_13d_funds_amount_fact(
                field_name="aggregate_purchase_price",
                subject_key=subject_key,
                source_span=source_span,
                raw_value=funds_source_text,
                numeric_value=float(funds_amount),
            )
            emitted_aggregate_purchase_subjects.add(subject_key)

    if form_family == "13D" and len(person_blocks) == 1:
        subject_key = "filer:1"
        funds_source_text = xml_direct_child_text(root, "fundsSource")
        funds_amount = extract_monetary_amount(funds_source_text)
        if funds_amount is not None:
            if subject_key not in emitted_source_of_funds_subjects:
                append_13d_funds_amount_fact(
                    field_name="source_of_funds_amount",
                    subject_key=subject_key,
                    source_span="xml.fundsSource",
                    raw_value=funds_source_text,
                    numeric_value=float(funds_amount),
                )
            if subject_key not in emitted_aggregate_purchase_subjects:
                append_13d_funds_amount_fact(
                    field_name="aggregate_purchase_price",
                    subject_key=subject_key,
                    source_span="xml.fundsSource",
                    raw_value=funds_source_text,
                    numeric_value=float(funds_amount),
                )

    return BundleBuildOutcome(bundle=FilingBundle(filing=filing, facts=facts, evidences=evidences))


def build_owner_form144_bundle(*, envelope: Any, filing: FilingRecord) -> BundleBuildOutcome:
    obj_method = getattr(envelope.filing, "obj", None)
    if not callable(obj_method):
        return BundleBuildOutcome(bundle=None)

    try:
        form144 = obj_method()
    except Exception as exc:
        return BundleBuildOutcome(bundle=None, error_detail=_format_exception_detail(exc))

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
                numeric_value = coerce_numeric_value(raw_value)
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
                numeric_value = coerce_numeric_value(raw_value)
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

    return BundleBuildOutcome(bundle=FilingBundle(filing=filing, facts=facts, evidences=evidences))
