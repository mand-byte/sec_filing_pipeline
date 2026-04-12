from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from src.db.repositories import PipelineRepository
from src.pipeline.edgar_provider import classify_form_family, fetch_filings_for_security
from src.pipeline.extraction.bundles import (
    build_holding_13f_bundle,
    build_issuer_8k_vote_bundle,
    build_owner_form144_bundle,
    build_owner_ownership_bundle,
    build_owner_schedule_13dg_bundle,
    coerce_numeric_value,
)
from src.pipeline.extraction.engine import NumericExtractionEngine
from src.pipeline.extraction.registry import all_numeric_field_specs
from src.pipeline.extraction.subject_keys import subject_key_has_type, subject_key_matches_granularity
from src.pipeline.extraction.text_engine import TextExtractionEngine
from src.pipeline.extraction.text_normalization import SpanNormalizer
from src.pipeline.extraction.text_registry import all_text_field_specs
from src.pipeline.route_runtime import FilingBundle, _normalize_to_utc, _safe_write_log
from src.pipeline.services import EvidenceInput, FactInput
from src.pipeline.types import FilingRecord, RouteName


_ISSUER_VOTE_FIELDS = {
    "proposal_votes_for",
    "proposal_votes_against",
    "proposal_votes_abstain",
    "proposal_broker_non_votes",
}
_SPECIALIZED_NUMERIC_CONTRACT_ERROR = "SPECIALIZED_SUBJECT_CONTRACT_VIOLATION"


def _specialized_numeric_bundle_contract_error(
    *,
    route: RouteName,
    bundle: FilingBundle,
    numeric_specs_by_field: dict[str, Any],
) -> str | None:
    violations: set[str] = set()
    for record_type, entries in (("fact", bundle.facts), ("evidence", bundle.evidences)):
        for entry in entries:
            field_name = getattr(entry, "field_name", "").strip()
            subject_key = getattr(entry, "subject_key", "").strip()
            spec = numeric_specs_by_field.get(field_name)
            if spec is None:
                violations.add(f"{record_type}:{field_name}:unregistered")
                continue
            if not subject_key_matches_granularity(
                route=route,
                granularity=spec.granularity,
                subject_key=subject_key,
            ):
                violations.add(
                    f"{record_type}:{field_name}:{subject_key or '<blank>'}:expected_granularity={spec.granularity}"
                )
                continue
            if not subject_key_has_type(
                route=route,
                subject_key=subject_key,
                subject_type=spec.subject_type,
            ):
                violations.add(
                    f"{record_type}:{field_name}:{subject_key or '<blank>'}:expected={spec.subject_type}"
                )

    if not violations:
        return None
    return "; ".join(sorted(violations))


def _extend_specialized_numeric_bundle_if_valid(
    *,
    route: RouteName,
    bundle: FilingBundle,
    facts: list[FactInput],
    evidences: list[EvidenceInput],
    numeric_specs_by_field: dict[str, Any],
    repo: PipelineRepository,
    run_id: str,
    cik: str | None,
    accession_no: str | None,
    violation_message: str,
) -> bool:
    contract_error_detail = _specialized_numeric_bundle_contract_error(
        route=route,
        bundle=bundle,
        numeric_specs_by_field=numeric_specs_by_field,
    )
    if contract_error_detail is not None:
        _safe_write_log(
            repo,
            run_id=run_id,
            route=route,
            stage="extract",
            level="ERROR",
            message=violation_message,
            cik=cik,
            accession_no=accession_no,
            error_type=_SPECIALIZED_NUMERIC_CONTRACT_ERROR,
            error_detail=contract_error_detail,
        )
        return False

    facts.extend(bundle.facts)
    evidences.extend(bundle.evidences)
    return True


def _append_partial_bundle_if_any(
    *,
    filing: FilingRecord,
    facts: list[FactInput],
    evidences: list[EvidenceInput],
    bundles: list[FilingBundle],
) -> bool:
    if not facts:
        return False

    bundles.append(
        FilingBundle(
            filing=filing,
            facts=list(facts),
            evidences=list(evidences),
        )
    )
    return True


def _supports_text_extraction_surface(filing: object) -> bool:
    for attr_name in ("sections", "parse", "text", "items"):
        attr = getattr(filing, attr_name, None)
        if callable(attr):
            try:
                value = attr()
            except Exception:
                continue
            if value:
                return True
            continue
        if attr:
            return True
    return False


def _extract_delay_days_from_text(filing: object) -> float | None:
    text_sources: list[str] = []
    for attr_name in ("parse", "text", "sections"):
        attr = getattr(filing, attr_name, None)
        if callable(attr):
            try:
                value = attr()
            except Exception:
                continue
        else:
            value = attr

        if isinstance(value, str) and value.strip():
            text_sources.append(value)
        elif isinstance(value, list):
            text_sources.extend(str(item) for item in value if str(item).strip())
        elif isinstance(value, dict):
            text_sources.extend(str(item) for item in value.values() if str(item).strip())

    pattern = re.compile(r"(?i)\b(\d+)\s+calendar\s+days?\b")
    for source in text_sources:
        match = pattern.search(source)
        if match is not None:
            return float(match.group(1))
    return None


def _extract_text_sources(filing: object) -> list[str]:
    text_sources: list[str] = []
    for attr_name in ("parse", "text", "sections"):
        attr = getattr(filing, attr_name, None)
        if callable(attr):
            try:
                value = attr()
            except Exception:
                continue
        else:
            value = attr

        if isinstance(value, str) and value.strip():
            text_sources.append(value)
        elif isinstance(value, list):
            text_sources.extend(str(item) for item in value if str(item).strip())
        elif isinstance(value, dict):
            text_sources.extend(str(item) for item in value.values() if str(item).strip())
    return text_sources


def _extract_text_sections(filing: object) -> list[tuple[str | None, str]]:
    sections: list[tuple[str | None, str]] = []

    raw_sections = getattr(filing, "sections", None)
    if callable(raw_sections):
        try:
            raw_sections = raw_sections()
        except Exception:
            raw_sections = None

    if isinstance(raw_sections, dict):
        for section_name, section_text in raw_sections.items():
            text = str(section_text).strip()
            if text:
                sections.append((str(section_name), text))
    elif isinstance(raw_sections, list):
        for section in raw_sections:
            text = str(section).strip()
            if not text:
                continue
            heading = text.splitlines()[0].strip() if text.splitlines() else None
            sections.append((heading, text))

    if sections:
        return sections

    for attr_name in ("parse", "text"):
        attr = getattr(filing, attr_name, None)
        if callable(attr):
            try:
                value = attr()
            except Exception:
                continue
        else:
            value = attr
        if isinstance(value, str) and value.strip():
            sections.append((None, value))
    return sections


def _extract_first_currency(patterns: tuple[str, ...], text_sources: list[str]) -> float | None:
    for source in text_sources:
        normalized = " ".join(source.split())
        for pattern in patterns:
            match = re.search(pattern, normalized)
            if match is None:
                continue
            candidate = coerce_numeric_value(match.group(1))
            if candidate is not None:
                return float(candidate)
    return None


def _extract_first_currency_with_section(
    patterns: tuple[str, ...], text_sections: list[tuple[str | None, str]]
) -> tuple[float | None, str | None]:
    for section_name, source in text_sections:
        normalized = " ".join(source.split())
        for pattern in patterns:
            match = re.search(pattern, normalized)
            if match is None:
                continue
            candidate = coerce_numeric_value(match.group(1))
            if candidate is not None:
                return float(candidate), section_name
    return None, None


def _extract_first_count(patterns: tuple[str, ...], text_sources: list[str]) -> float | None:
    for source in text_sources:
        normalized = " ".join(source.split())
        for pattern in patterns:
            match = re.search(pattern, normalized)
            if match is None:
                continue
            candidate = coerce_numeric_value(match.group(1))
            if candidate is not None:
                return float(candidate)
    return None


def _extract_first_count_with_section(
    patterns: tuple[str, ...], text_sections: list[tuple[str | None, str]]
) -> tuple[float | None, str | None]:
    for section_name, source in text_sections:
        normalized = " ".join(source.split())
        for pattern in patterns:
            match = re.search(pattern, normalized)
            if match is None:
                continue
            candidate = coerce_numeric_value(match.group(1))
            if candidate is not None:
                return float(candidate), section_name
    return None, None


def _build_issuer_offering_text_facts(*, filing: FilingRecord, text_sections: list[tuple[str | None, str]]) -> FilingBundle | None:
    field_extractors = {
        "gross_proceeds": _extract_first_currency_with_section(
            (
                r"(?i)gross proceeds(?: of)?\s+\$([\d,]+(?:\.\d+)?)",
                r"(?i)aggregate offering price(?: of)?\s+\$([\d,]+(?:\.\d+)?)",
            ),
            text_sections,
        ),
        "net_proceeds": _extract_first_currency_with_section(
            (
                r"(?i)net proceeds(?: of)?\s+\$([\d,]+(?:\.\d+)?)",
                r"(?i)estimated net proceeds(?: of)?\s+\$([\d,]+(?:\.\d+)?)",
            ),
            text_sections,
        ),
        "offering_price_per_share": _extract_first_currency_with_section(
            (
                r"(?i)offering price per share(?: was| is)?\s+\$([\d,]+(?:\.\d+)?)",
                r"(?i)\$([\d,]+(?:\.\d+)?)\s+per share",
            ),
            text_sections,
        ),
        "underwriter_discount_total": _extract_first_currency_with_section(
            (
                r"(?i)underwriting discounts and commissions(?: of)?\s+\$([\d,]+(?:\.\d+)?)",
            ),
            text_sections,
        ),
        "financing_commitment_amount": _extract_first_currency_with_section(
            (
                r"(?i)financing commitment(?: of)?\s+\$([\d,]+(?:\.\d+)?)",
                r"(?i)backstop amount(?: of)?\s+\$([\d,]+(?:\.\d+)?)",
            ),
            text_sections,
        ),
        "securities_offered_qty": _extract_first_count_with_section(
            (
                r"(?i)([\d,]+)\s+shares?\s+of common stock",
                r"(?i)offering of\s+([\d,]+)\s+shares?",
            ),
            text_sections,
        ),
    }

    facts: list[FactInput] = []
    evidences: list[EvidenceInput] = []
    for field_name, extraction in field_extractors.items():
        value, source_section = extraction
        if value is None:
            continue
        subject_key = "security:1" if field_name in {"offering_price_per_share", "securities_offered_qty"} else "document"
        facts.append(
            FactInput(
                field_name=field_name,
                subject_key=subject_key,
                value_numeric=value,
                confidence=0.99,
            )
        )
        evidences.append(
            EvidenceInput(
                field_name=field_name,
                subject_key=subject_key,
                locator_kind="parse_text",
                source_span="offering_text",
                source_section=source_section,
                raw_value=str(value),
                normalized_value=str(value),
            )
        )

    if not facts:
        return None
    return FilingBundle(filing=filing, facts=facts, evidences=evidences)


def _build_issuer_deal_text_facts(*, filing: FilingRecord, text_sections: list[tuple[str | None, str]]) -> FilingBundle | None:
    field_extractors = {
        "deal_value": _extract_first_currency_with_section(
            (
                r"(?i)deal value(?: of)?\s+\$([\d,]+(?:\.\d+)?)",
                r"(?i)transaction value(?: of)?\s+\$([\d,]+(?:\.\d+)?)",
            ),
            text_sections,
        ),
        "offer_price_per_share": _extract_first_currency_with_section(
            (
                r"(?i)offer price per share(?: was| is)?\s+\$([\d,]+(?:\.\d+)?)",
                r"(?i)cash consideration per share(?: was| is)?\s+\$([\d,]+(?:\.\d+)?)",
            ),
            text_sections,
        ),
        "tender_shares_sought": _extract_first_count_with_section(
            (
                r"(?i)([\d,]+)\s+shares?\s+sought",
                r"(?i)maximum number of shares(?: is| are)?\s+([\d,]+)",
            ),
            text_sections,
        ),
        "financing_commitment_amount": _extract_first_currency_with_section(
            (
                r"(?i)financing commitment(?: of)?\s+\$([\d,]+(?:\.\d+)?)",
                r"(?i)backstop amount(?: of)?\s+\$([\d,]+(?:\.\d+)?)",
            ),
            text_sections,
        ),
        "termination_fee": _extract_first_currency_with_section(
            (
                r"(?i)termination fee(?: of)?\s+\$([\d,]+(?:\.\d+)?)",
                r"(?i)break-up fee(?: of)?\s+\$([\d,]+(?:\.\d+)?)",
            ),
            text_sections,
        ),
    }

    facts: list[FactInput] = []
    evidences: list[EvidenceInput] = []
    for field_name, extraction in field_extractors.items():
        value, source_section = extraction
        if value is None:
            continue
        subject_key = "security:1" if field_name in {"offer_price_per_share", "tender_shares_sought"} else "document"
        facts.append(
            FactInput(
                field_name=field_name,
                subject_key=subject_key,
                value_numeric=value,
                confidence=0.99,
            )
        )
        evidences.append(
            EvidenceInput(
                field_name=field_name,
                subject_key=subject_key,
                locator_kind="parse_text",
                source_span="deal_text",
                source_section=source_section,
                raw_value=str(value),
                normalized_value=str(value),
            )
        )

    if not facts:
        return None
    return FilingBundle(filing=filing, facts=facts, evidences=evidences)


def _build_issuer_row_numeric_text_facts(*, filing: FilingRecord, text_sections: list[tuple[str | None, str]]) -> FilingBundle | None:
    facts: list[FactInput] = []
    evidences: list[EvidenceInput] = []
    executive_index = 0
    holder_index = 0

    exec_pattern = re.compile(r"(?i)^(?P<label>.+?)\s+total\s+\$?(?P<amount>[\d,]+(?:\.\d+)?)$")
    holder_pattern = re.compile(r"(?i)^(?P<label>.+?)\s+(?P<shares>[\d,]+)\s+shares?\s+(?P<pct>[\d.]+)%$")

    for source_section, source in text_sections:
        for raw_line in source.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            exec_match = exec_pattern.match(line)
            if exec_match is not None:
                amount = coerce_numeric_value(exec_match.group("amount"))
                if amount is not None:
                    executive_index += 1
                    subject_key = f"exec:{executive_index}"
                    facts.append(
                        FactInput(
                            field_name="exec_total_comp",
                            subject_key=subject_key,
                            value_numeric=float(amount),
                            confidence=0.99,
                        )
                    )
                    evidences.append(
                        EvidenceInput(
                            field_name="exec_total_comp",
                            subject_key=subject_key,
                            locator_kind="parse_text",
                            source_span=line,
                            source_section=source_section,
                            raw_value=exec_match.group("amount"),
                            normalized_value=str(float(amount)),
                        )
                    )
                continue

            holder_match = holder_pattern.match(line)
            if holder_match is not None:
                shares = coerce_numeric_value(holder_match.group("shares"))
                pct = coerce_numeric_value(holder_match.group("pct"))
                if shares is not None and pct is not None:
                    holder_index += 1
                    subject_key = f"holder:{holder_index}"
                    facts.append(
                        FactInput(
                            field_name="holder_beneficial_ownership_shares",
                            subject_key=subject_key,
                            value_numeric=float(shares),
                            confidence=0.99,
                        )
                    )
                    facts.append(
                        FactInput(
                            field_name="holder_beneficial_ownership_pct",
                            subject_key=subject_key,
                            value_numeric=float(pct),
                            confidence=0.99,
                        )
                    )
                    evidences.append(
                        EvidenceInput(
                            field_name="holder_beneficial_ownership_shares",
                            subject_key=subject_key,
                            locator_kind="parse_text",
                            source_span=line,
                            source_section=source_section,
                            raw_value=holder_match.group("shares"),
                            normalized_value=str(float(shares)),
                        )
                    )
                    evidences.append(
                        EvidenceInput(
                            field_name="holder_beneficial_ownership_pct",
                            subject_key=subject_key,
                            locator_kind="parse_text",
                            source_span=line,
                            source_section=source_section,
                            raw_value=holder_match.group("pct"),
                            normalized_value=str(float(pct)),
                        )
                    )

    if not facts:
        return None
    return FilingBundle(filing=filing, facts=facts, evidences=evidences)


def build_bundles_from_provider(
    *,
    security: Any,
    route: RouteName,
    start_accepted_at: datetime,
    repo: PipelineRepository,
    run_id: str,
    fetch_filings=fetch_filings_for_security,
    text_normalizer: SpanNormalizer | None = None,
) -> list[FilingBundle]:
    envelopes = fetch_filings(
        security=security,
        route=route,
        start_accepted_at=start_accepted_at,
    )
    if not envelopes:
        return []

    numeric_engine = NumericExtractionEngine()
    text_engine = TextExtractionEngine(normalizer=text_normalizer)
    route_numeric_specs = tuple(
        sorted(
            (spec for spec in all_numeric_field_specs() if spec.route == route),
            key=lambda spec: spec.field_name,
        )
    )
    route_numeric_specs_by_field = {
        spec.field_name: spec
        for spec in route_numeric_specs
    }
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
            filed_at=envelope.filed_at,
            accepted_at=envelope.accepted_at,
            period_end=envelope.period_end,
            is_amendment=envelope.form_type.endswith("/A"),
            amendment_no=envelope.amendment_no,
        )

        facts: list[FactInput] = []
        evidences: list[EvidenceInput] = []
        form_family = classify_form_family(envelope.form_type)
        if route == "owner" and form_family in {"3", "4", "5"}:
            if _supports_text_extraction_surface(envelope.filing):
                owner_text_specs = tuple(
                    spec
                    for spec in route_text_specs
                    if form_family in spec.form_families
                )
                for spec in owner_text_specs:
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
                            source_section=outcome["source_section"],
                            source_item_no=outcome["source_item_no"],
                            source_xpath=outcome["locator_path"],
                            source_locator_json=outcome["source_locator_json"],
                            source_heading_path_json=outcome["source_heading_path_json"],
                            source_block_offsets_json=outcome["source_block_offsets_json"],
                            adequacy_signals_json=outcome["adequacy_signals_json"],
                            retry_history_json=outcome["retry_history_json"],
                            selection_trace_json=outcome["selection_trace_json"],
                            raw_value=outcome["value_text"],
                            normalized_value=outcome["value_text"],
                        )
                    )

            owner_outcome = build_owner_ownership_bundle(envelope=envelope, filing=filing)
            owner_bundle = owner_outcome.bundle
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
                    error_detail=owner_outcome.error_detail,
                )
                _append_partial_bundle_if_any(
                    filing=filing,
                    facts=facts,
                    evidences=evidences,
                    bundles=bundles,
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
                _append_partial_bundle_if_any(
                    filing=filing,
                    facts=facts,
                    evidences=evidences,
                    bundles=bundles,
                )
                continue
            owner_facts: list[FactInput] = []
            owner_evidences: list[EvidenceInput] = []
            if not _extend_specialized_numeric_bundle_if_valid(
                route=route,
                bundle=owner_bundle,
                facts=owner_facts,
                evidences=owner_evidences,
                numeric_specs_by_field=route_numeric_specs_by_field,
                repo=repo,
                run_id=run_id,
                cik=envelope.cik,
                accession_no=envelope.accession_no,
                violation_message="owner ownership bundle violated numeric subject contract",
            ):
                _append_partial_bundle_if_any(
                    filing=filing,
                    facts=facts,
                    evidences=evidences,
                    bundles=bundles,
                )
                continue
            merged_bundle = FilingBundle(
                filing=owner_bundle.filing,
                facts=[*owner_facts, *facts],
                evidences=[*owner_evidences, *evidences],
            )
            bundles.append(merged_bundle)
            continue

        if route == "owner" and form_family in {"13D", "13G"}:
            if _supports_text_extraction_surface(envelope.filing):
                schedule_text_specs = tuple(
                    spec
                    for spec in route_text_specs
                    if form_family in spec.form_families
                )
                for spec in schedule_text_specs:
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
                            source_section=outcome["source_section"],
                            source_item_no=outcome["source_item_no"],
                            source_xpath=outcome["locator_path"],
                            source_locator_json=outcome["source_locator_json"],
                            source_heading_path_json=outcome["source_heading_path_json"],
                            source_block_offsets_json=outcome["source_block_offsets_json"],
                            adequacy_signals_json=outcome["adequacy_signals_json"],
                            retry_history_json=outcome["retry_history_json"],
                            selection_trace_json=outcome["selection_trace_json"],
                            raw_value=outcome["value_text"],
                            normalized_value=outcome["value_text"],
                        )
                    )

            schedule_outcome = build_owner_schedule_13dg_bundle(
                envelope=envelope,
                filing=filing,
                form_family=form_family,
            )
            schedule_bundle = schedule_outcome.bundle
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
                    error_detail=schedule_outcome.error_detail,
                )
                _append_partial_bundle_if_any(
                    filing=filing,
                    facts=facts,
                    evidences=evidences,
                    bundles=bundles,
                )
                continue
            has_owner_rows = any(
                subject_key_has_type(
                    route=route,
                    subject_key=fact.subject_key,
                    subject_type="reporting_person",
                )
                for fact in schedule_bundle.facts
            )
            if not _extend_specialized_numeric_bundle_if_valid(
                route=route,
                bundle=schedule_bundle,
                facts=facts,
                evidences=evidences,
                numeric_specs_by_field=route_numeric_specs_by_field,
                repo=repo,
                run_id=run_id,
                cik=envelope.cik,
                accession_no=envelope.accession_no,
                violation_message="owner schedule bundle violated numeric subject contract",
            ):
                _append_partial_bundle_if_any(
                    filing=filing,
                    facts=facts,
                    evidences=evidences,
                    bundles=bundles,
                )
                continue
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
                _append_partial_bundle_if_any(
                    filing=filing,
                    facts=facts,
                    evidences=evidences,
                    bundles=bundles,
                )
                continue
            merged_bundle = FilingBundle(
                filing=schedule_bundle.filing,
                facts=list(facts),
                evidences=list(evidences),
            )
            bundles.append(merged_bundle)
            continue
        if route == "owner" and form_family == "144":
            if _supports_text_extraction_surface(envelope.filing):
                form144_text_specs = tuple(
                    spec
                    for spec in route_text_specs
                    if form_family in spec.form_families
                )
                for spec in form144_text_specs:
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
                            source_section=outcome["source_section"],
                            source_item_no=outcome["source_item_no"],
                            source_xpath=outcome["locator_path"],
                            source_locator_json=outcome["source_locator_json"],
                            source_heading_path_json=outcome["source_heading_path_json"],
                            source_block_offsets_json=outcome["source_block_offsets_json"],
                            adequacy_signals_json=outcome["adequacy_signals_json"],
                            retry_history_json=outcome["retry_history_json"],
                            selection_trace_json=outcome["selection_trace_json"],
                            raw_value=outcome["value_text"],
                            normalized_value=outcome["value_text"],
                        )
                    )

            form144_outcome = build_owner_form144_bundle(envelope=envelope, filing=filing)
            form144_bundle = form144_outcome.bundle
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
                    error_detail=form144_outcome.error_detail,
                )
                _append_partial_bundle_if_any(
                    filing=filing,
                    facts=facts,
                    evidences=evidences,
                    bundles=bundles,
                )
                continue
            has_sale_rows = any(
                subject_key_has_type(
                    route=route,
                    subject_key=fact.subject_key,
                    subject_type="form144_notice",
                )
                for fact in form144_bundle.facts
            )
            form144_facts: list[FactInput] = []
            form144_evidences: list[EvidenceInput] = []
            if not _extend_specialized_numeric_bundle_if_valid(
                route=route,
                bundle=form144_bundle,
                facts=form144_facts,
                evidences=form144_evidences,
                numeric_specs_by_field=route_numeric_specs_by_field,
                repo=repo,
                run_id=run_id,
                cik=envelope.cik,
                accession_no=envelope.accession_no,
                violation_message="owner form144 bundle violated numeric subject contract",
            ):
                _append_partial_bundle_if_any(
                    filing=filing,
                    facts=facts,
                    evidences=evidences,
                    bundles=bundles,
                )
                continue
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
                _append_partial_bundle_if_any(
                    filing=filing,
                    facts=facts,
                    evidences=evidences,
                    bundles=bundles,
                )
                continue
            merged_bundle = FilingBundle(
                filing=form144_bundle.filing,
                facts=[*form144_facts, *facts],
                evidences=[*form144_evidences, *evidences],
            )
            bundles.append(merged_bundle)
            continue

        if route == "issuer" and form_family == "8-K":
            vote_outcome = build_issuer_8k_vote_bundle(
                envelope=envelope,
                filing=filing,
            )
            vote_bundle = vote_outcome.bundle
            vote_item_present = vote_outcome.item_present
            if vote_bundle is not None:
                vote_facts: list[FactInput] = []
                vote_evidences: list[EvidenceInput] = []
                vote_bundle_valid = _extend_specialized_numeric_bundle_if_valid(
                    route=route,
                    bundle=vote_bundle,
                    facts=vote_facts,
                    evidences=vote_evidences,
                    numeric_specs_by_field=route_numeric_specs_by_field,
                    repo=repo,
                    run_id=run_id,
                    cik=envelope.cik,
                    accession_no=envelope.accession_no,
                    violation_message="issuer 8-K vote bundle violated numeric subject contract",
                )
                if vote_bundle_valid:
                    has_vote_rows = any(
                        subject_key_has_type(
                            route=route,
                            subject_key=fact.subject_key,
                            subject_type="proposal",
                        )
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
                            error_detail=vote_outcome.error_detail,
                        )
                    if has_vote_rows:
                        facts.extend(vote_facts)
                        evidences.extend(vote_evidences)

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
                        source_section=outcome["source_section"],
                        source_item_no=outcome["source_item_no"],
                        source_xpath=outcome["locator_path"],
                        source_locator_json=outcome["source_locator_json"],
                        source_heading_path_json=outcome["source_heading_path_json"],
                        source_block_offsets_json=outcome["source_block_offsets_json"],
                        adequacy_signals_json=outcome["adequacy_signals_json"],
                        retry_history_json=outcome["retry_history_json"],
                        selection_trace_json=outcome["selection_trace_json"],
                        raw_value=outcome["value_text"],
                        normalized_value=outcome["value_text"],
                    )
                )

            holding_outcome = build_holding_13f_bundle(envelope=envelope, filing=filing)
            holding_bundle = holding_outcome.bundle
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
                    error_detail=holding_outcome.error_detail,
                )
                _append_partial_bundle_if_any(
                    filing=filing,
                    facts=facts,
                    evidences=evidences,
                    bundles=bundles,
                )
                continue
            has_position_rows = any(
                subject_key_has_type(
                    route=route,
                    subject_key=fact.subject_key,
                    subject_type="holding_position",
                )
                for fact in holding_bundle.facts
            )
            holding_facts: list[FactInput] = []
            holding_evidences: list[EvidenceInput] = []
            if not _extend_specialized_numeric_bundle_if_valid(
                route=route,
                bundle=holding_bundle,
                facts=holding_facts,
                evidences=holding_evidences,
                numeric_specs_by_field=route_numeric_specs_by_field,
                repo=repo,
                run_id=run_id,
                cik=envelope.cik,
                accession_no=envelope.accession_no,
                violation_message="holding 13F amendment bundle violated numeric subject contract",
            ):
                _append_partial_bundle_if_any(
                    filing=filing,
                    facts=facts,
                    evidences=evidences,
                    bundles=bundles,
                )
                continue
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
                _append_partial_bundle_if_any(
                    filing=filing,
                    facts=facts,
                    evidences=evidences,
                    bundles=bundles,
                )
                continue
            merged_bundle = FilingBundle(
                filing=holding_bundle.filing,
                facts=[*holding_facts, *facts],
                evidences=[*holding_evidences, *evidences],
            )
            bundles.append(merged_bundle)
            continue

        if route == "holding" and form_family == "13F-HR":
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
                        source_section=outcome["source_section"],
                        source_item_no=outcome["source_item_no"],
                        source_xpath=outcome["locator_path"],
                        source_locator_json=outcome["source_locator_json"],
                        source_heading_path_json=outcome["source_heading_path_json"],
                        source_block_offsets_json=outcome["source_block_offsets_json"],
                        adequacy_signals_json=outcome["adequacy_signals_json"],
                        retry_history_json=outcome["retry_history_json"],
                        selection_trace_json=outcome["selection_trace_json"],
                        raw_value=outcome["value_text"],
                        normalized_value=outcome["value_text"],
                    )
                )

            holding_outcome = build_holding_13f_bundle(envelope=envelope, filing=filing)
            holding_bundle = holding_outcome.bundle
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
                    error_detail=holding_outcome.error_detail,
                )
                _append_partial_bundle_if_any(
                    filing=filing,
                    facts=facts,
                    evidences=evidences,
                    bundles=bundles,
                )
                continue
            has_position_rows = any(
                subject_key_has_type(
                    route=route,
                    subject_key=fact.subject_key,
                    subject_type="holding_position",
                )
                for fact in holding_bundle.facts
            )
            holding_facts: list[FactInput] = []
            holding_evidences: list[EvidenceInput] = []
            if not _extend_specialized_numeric_bundle_if_valid(
                route=route,
                bundle=holding_bundle,
                facts=holding_facts,
                evidences=holding_evidences,
                numeric_specs_by_field=route_numeric_specs_by_field,
                repo=repo,
                run_id=run_id,
                cik=envelope.cik,
                accession_no=envelope.accession_no,
                violation_message="holding 13F bundle violated numeric subject contract",
            ):
                _append_partial_bundle_if_any(
                    filing=filing,
                    facts=facts,
                    evidences=evidences,
                    bundles=bundles,
                )
                continue
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
                _append_partial_bundle_if_any(
                    filing=filing,
                    facts=facts,
                    evidences=evidences,
                    bundles=bundles,
                )
                continue
            merged_bundle = FilingBundle(
                filing=holding_bundle.filing,
                facts=[*holding_facts, *facts],
                evidences=[*holding_evidences, *evidences],
            )
            bundles.append(merged_bundle)
            continue

        filing_numeric_specs = route_numeric_specs
        filing_text_specs = route_text_specs
        if route == "issuer" and form_family == "10-Q":
            filing_numeric_specs = tuple(
                spec
                for spec in route_numeric_specs
                if spec.xbrl_enabled_form_families and form_family in spec.xbrl_enabled_form_families
            )
            filing_text_specs = (
                tuple(
                    spec
                    for spec in route_text_specs
                    if form_family in spec.form_families
                )
                if _supports_text_extraction_surface(envelope.filing)
                else ()
            )
        elif route == "issuer" and form_family == "8-K":
            filing_numeric_specs = tuple(
                spec
                for spec in route_numeric_specs
                if spec.field_name not in _ISSUER_VOTE_FIELDS
            )
            text_sections = _extract_text_sections(envelope.filing)
            deal_bundle = _build_issuer_deal_text_facts(
                filing=filing,
                text_sections=text_sections,
            )
            if deal_bundle is not None:
                _extend_specialized_numeric_bundle_if_valid(
                    route=route,
                    bundle=deal_bundle,
                    facts=facts,
                    evidences=evidences,
                    numeric_specs_by_field=route_numeric_specs_by_field,
                    repo=repo,
                    run_id=run_id,
                    cik=envelope.cik,
                    accession_no=envelope.accession_no,
                    violation_message="issuer deal bundle violated numeric subject contract",
                )
        elif route == "issuer" and form_family in {"S-1", "424B4"}:
            text_sections = _extract_text_sections(envelope.filing)
            offering_bundle = _build_issuer_offering_text_facts(
                filing=filing,
                text_sections=text_sections,
            )
            if offering_bundle is not None:
                _extend_specialized_numeric_bundle_if_valid(
                    route=route,
                    bundle=offering_bundle,
                    facts=facts,
                    evidences=evidences,
                    numeric_specs_by_field=route_numeric_specs_by_field,
                    repo=repo,
                    run_id=run_id,
                    cik=envelope.cik,
                    accession_no=envelope.accession_no,
                    violation_message="issuer offering bundle violated numeric subject contract",
                )
            row_numeric_bundle = _build_issuer_row_numeric_text_facts(
                filing=filing,
                text_sections=text_sections,
            )
            if row_numeric_bundle is not None:
                _extend_specialized_numeric_bundle_if_valid(
                    route=route,
                    bundle=row_numeric_bundle,
                    facts=facts,
                    evidences=evidences,
                    numeric_specs_by_field=route_numeric_specs_by_field,
                    repo=repo,
                    run_id=run_id,
                    cik=envelope.cik,
                    accession_no=envelope.accession_no,
                    violation_message="issuer row-numeric bundle violated numeric subject contract",
                )
        elif route == "issuer" and form_family == "DEF 14A":
            text_sections = _extract_text_sections(envelope.filing)
            row_numeric_bundle = _build_issuer_row_numeric_text_facts(
                filing=filing,
                text_sections=text_sections,
            )
            if row_numeric_bundle is not None:
                _extend_specialized_numeric_bundle_if_valid(
                    route=route,
                    bundle=row_numeric_bundle,
                    facts=facts,
                    evidences=evidences,
                    numeric_specs_by_field=route_numeric_specs_by_field,
                    repo=repo,
                    run_id=run_id,
                    cik=envelope.cik,
                    accession_no=envelope.accession_no,
                    violation_message="issuer row-numeric bundle violated numeric subject contract",
                )
        elif route == "issuer" and form_family in {"SC TO-I", "SC 13E3"}:
            text_sections = _extract_text_sections(envelope.filing)
            deal_bundle = _build_issuer_deal_text_facts(
                filing=filing,
                text_sections=text_sections,
            )
            if deal_bundle is not None:
                _extend_specialized_numeric_bundle_if_valid(
                    route=route,
                    bundle=deal_bundle,
                    facts=facts,
                    evidences=evidences,
                    numeric_specs_by_field=route_numeric_specs_by_field,
                    repo=repo,
                    run_id=run_id,
                    cik=envelope.cik,
                    accession_no=envelope.accession_no,
                    violation_message="issuer deal bundle violated numeric subject contract",
                )
        elif route == "issuer" and form_family in {"NT 10-Q", "NT 10-K"}:
            delay_days = _extract_delay_days_from_text(envelope.filing)
            if delay_days is not None:
                facts.append(
                    FactInput(
                        field_name="filing_delay_days",
                        subject_key="document",
                        value_numeric=delay_days,
                        confidence=0.99,
                    )
                )
                evidences.append(
                    EvidenceInput(
                        field_name="filing_delay_days",
                        subject_key="document",
                        locator_kind="parse_text",
                        source_span="calendar_days",
                        raw_value=str(int(delay_days)),
                        normalized_value=str(delay_days),
                    )
                )

        if route == "issuer" and form_family in {"DEF 14A", "S-1", "424B4"}:
            filing_numeric_specs = tuple(
                spec
                for spec in filing_numeric_specs
                if spec.field_name
                not in {
                    "exec_total_comp",
                    "holder_beneficial_ownership_shares",
                    "holder_beneficial_ownership_pct",
                }
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
                    selection_trace_json=outcome.get("selection_trace_json"),
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
                    source_section=outcome["source_section"],
                    source_item_no=outcome["source_item_no"],
                    source_xpath=outcome["locator_path"],
                    source_locator_json=outcome["source_locator_json"],
                    source_heading_path_json=outcome["source_heading_path_json"],
                    source_block_offsets_json=outcome["source_block_offsets_json"],
                    adequacy_signals_json=outcome["adequacy_signals_json"],
                    retry_history_json=outcome["retry_history_json"],
                    selection_trace_json=outcome["selection_trace_json"],
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
