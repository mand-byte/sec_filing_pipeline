from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
import json
import math
from pathlib import Path
from typing import Any

import yaml

from src.pipeline.strict_v2_gates import evaluate_phase_gates

_FIELD_CONCEPTS: dict[str, tuple[str, ...]] = {
    "total_revenue": (
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:Revenues",
        "us-gaap:SalesRevenueNet",
    ),
    "operating_income": ("us-gaap:OperatingIncomeLoss",),
    "net_income": ("us-gaap:NetIncomeLoss", "us-gaap:ProfitLoss"),
}


def _normalize_concept(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    cleaned = value.strip()
    if not cleaned:
        return None

    if ":" in cleaned:
        cleaned = cleaned.split(":", 1)[1]
    return cleaned.casefold()


def _record_concept(candidate: dict[str, Any]) -> str | None:
    value = _record_get(candidate, "concept", "Concept", "qname", "name")
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _candidate_key(candidate: dict[str, Any]) -> str:
    for key in ("fact_key", "id", "key"):
        value = candidate.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    concept = _record_concept(candidate) or "unknown"
    period_start = _record_get(candidate, "period_start", "periodStart", "start_date", "startDate")
    period_end = _record_get(candidate, "period_end", "periodEnd", "end_date", "endDate")
    dimensions = _record_get(candidate, "dimensions", "Dimensions", "dimension")
    return f"{concept}|{period_start}|{period_end}|{dimensions}"


@dataclass(frozen=True)
class NumericBatchField:
    field_name: str
    adjudication: dict[str, Any]


@dataclass(frozen=True)
class NumericBatchCase:
    case_id: str
    ticker: str
    sic: int | None
    industry: str | None
    form_type: str
    accession_no: str
    filing_year: int
    filing_period: str
    fields: tuple[NumericBatchField, ...]


@dataclass(frozen=True)
class NumericBatchEvalResult:
    summary: dict[str, Any]
    by_field: dict[str, Any]
    failures: list[dict[str, Any]]
    phase_gates: list[dict[str, Any]]
    review_packets: list[dict[str, Any]]


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, Mapping):
        raise ValueError(f"numeric batch yaml root must be a mapping: {path}")
    return dict(payload)


def load_10q_numeric_batch_cases(golden_path: Path) -> list[NumericBatchCase]:
    payload = _load_yaml_mapping(golden_path)
    cases_raw = payload.get("cases", [])
    cases: list[NumericBatchCase] = []
    for case in cases_raw:
        fields = tuple(
            NumericBatchField(
                field_name=str(field["field_name"]),
                adjudication=dict(field["adjudication"]),
            )
            for field in case.get("fields", [])
        )
        cases.append(
            NumericBatchCase(
                case_id=str(case["case_id"]),
                ticker=str(case["ticker"]),
                sic=case.get("sic"),
                industry=case.get("industry"),
                form_type=str(case["form_type"]),
                accession_no=str(case["accession_no"]),
                filing_year=int(case["filing_year"]),
                filing_period=str(case["filing_period"]),
                fields=fields,
            )
        )
    return cases


def apply_adjudication_update(
    *,
    golden_path: Path,
    case_id: str,
    field_name: str,
    selected_candidate_key: str,
    actual_value: float | int,
    confidence: float,
    reason: str,
    confidence_threshold: float,
) -> bool:
    payload = yaml.safe_load(golden_path.read_text(encoding="utf-8")) or {}
    if not math.isfinite(confidence) or confidence < confidence_threshold:
        return False

    for case in payload.get("cases", []):
        if str(case.get("case_id")) != case_id:
            continue
        for field in case.get("fields", []):
            if str(field.get("field_name")) != field_name:
                continue
            adjudication = field.setdefault("adjudication", {})
            adjudication["selected_candidate_key"] = selected_candidate_key
            adjudication["value_numeric"] = actual_value
            adjudication["selection_reason"] = reason
            adjudication["adjudicated_by"] = "snippet_financial_analyst"
            adjudication["adjudication_confidence"] = confidence
            golden_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
            return True
    return False


def _record_get(candidate: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in candidate:
            return candidate[key]
    return None


def _coerce_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            return date.fromisoformat(cleaned[:10])
        except ValueError:
            return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        try:
            return _coerce_date(isoformat())
        except Exception:
            return None
    return None


def _duration_days(candidate: dict[str, Any]) -> int | None:
    period_start = _coerce_date(
        _record_get(candidate, "period_start", "periodStart", "start_date", "startDate")
    )
    period_end = _coerce_date(
        _record_get(candidate, "period_end", "periodEnd", "end_date", "endDate")
    )
    if period_start is None or period_end is None:
        return None
    return (period_end - period_start).days + 1


def _record_statement_type(candidate: dict[str, Any]) -> str | None:
    value = _record_get(candidate, "statement_type", "statementType", "statement")
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _record_dimensioned(candidate: dict[str, Any]) -> bool:
    explicit = _record_get(candidate, "dimensioned", "is_dimensioned")
    if isinstance(explicit, bool):
        return explicit

    dimensions = _record_get(candidate, "dimensions", "Dimensions", "dimension")
    if isinstance(dimensions, Mapping):
        return bool(dimensions)
    if isinstance(dimensions, Sequence) and not isinstance(dimensions, (str, bytes)):
        return len(dimensions) > 0
    return False


def _record_value(candidate: dict[str, Any]) -> Any:
    value = _record_get(candidate, "value", "numeric_value", "amount")
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return value


def _passes_runtime_filters(*, field_name: str, candidate: dict[str, Any]) -> bool:
    desired_concepts = {
        _normalize_concept(concept)
        for concept in _FIELD_CONCEPTS.get(field_name, ())
        if _normalize_concept(concept) is not None
    }
    concept_key = _normalize_concept(_record_concept(candidate))
    if concept_key is None or concept_key not in desired_concepts:
        return False

    statement_type = _record_statement_type(candidate)
    if statement_type not in {None, "IncomeStatement"}:
        return False

    if _record_dimensioned(candidate):
        return False

    duration = _duration_days(candidate)
    if duration is not None and not (70 <= duration <= 110):
        return False

    return _record_value(candidate) is not None


def _candidate_score(*, field_name: str, candidate: dict[str, Any]) -> int:
    score = 0

    desired_concepts = {
        _normalize_concept(concept): index
        for index, concept in enumerate(_FIELD_CONCEPTS.get(field_name, ()))
        if _normalize_concept(concept) is not None
    }
    concept_key = _normalize_concept(_record_concept(candidate))
    if concept_key in desired_concepts:
        score += 100 - desired_concepts[concept_key] * 10

    if _record_statement_type(candidate) == "IncomeStatement":
        score += 30
    if not _record_dimensioned(candidate):
        score += 20

    duration = _duration_days(candidate)
    if duration is not None and 70 <= duration <= 110:
        target_days = 90
        score += max(0, 20 - abs(duration - target_days))
    elif duration is not None and duration >= 150:
        score -= 10

    return score


def _update_by_field(*, by_field: dict[str, dict[str, int]], field_name: str, recall_hit: bool, top1_hit: bool) -> None:
    stats = by_field.setdefault(
        field_name,
        {"total": 0, "candidate_recall_hits": 0, "top1_hits": 0},
    )
    stats["total"] += 1
    if recall_hit:
        stats["candidate_recall_hits"] += 1
    if top1_hit:
        stats["top1_hits"] += 1


def _finalize_by_field(by_field: dict[str, dict[str, int]]) -> dict[str, dict[str, float | int]]:
    finalized: dict[str, dict[str, float | int]] = {}
    for field_name, stats in by_field.items():
        total = stats["total"]
        finalized[field_name] = {
            "total": total,
            "candidate_recall": stats["candidate_recall_hits"] / total if total else 0.0,
            "top1_accuracy": stats["top1_hits"] / total if total else 0.0,
        }
    return finalized


def evaluate_10q_numeric_batch(*, golden_path: Path, snapshot_dir: Path) -> NumericBatchEvalResult:
    golden_payload = _load_yaml_mapping(golden_path)
    cases = load_10q_numeric_batch_cases(golden_path)
    total_batches = len(cases)
    total_field_checks = 0
    candidate_recall_hits = 0
    top1_hits = 0
    batch_all_match_hits = 0
    failures: list[dict[str, Any]] = []
    by_field: dict[str, dict[str, int]] = {}
    review_packets: list[dict[str, Any]] = []
    seen_fields: set[str] = set()
    seen_form_types: set[str] = set()
    seen_tickers: set[str] = set()
    seen_filing_years: set[str] = set()

    for case in cases:
        seen_tickers.add(case.ticker)
        seen_form_types.add(case.form_type)
        seen_filing_years.add(str(case.filing_year))
        snapshot_path = snapshot_dir / f"{case.case_id}.json"
        snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        snapshot_fields = {
            str(field["field_name"]): list(field.get("candidate_pool", []))
            for field in snapshot_payload.get("fields", [])
        }

        batch_all_match = True
        for field in case.fields:
            seen_fields.add(field.field_name)
            total_field_checks += 1
            candidates = snapshot_fields.get(field.field_name, [])
            selected_key = field.adjudication.get("selected_candidate_key")
            available_keys = {_candidate_key(candidate) for candidate in candidates}
            recall_hit = selected_key in available_keys
            if recall_hit:
                candidate_recall_hits += 1

            ranked = sorted(
                [
                    candidate
                    for candidate in candidates
                    if _passes_runtime_filters(
                        field_name=field.field_name,
                        candidate=candidate,
                    )
                ],
                key=lambda candidate: (
                    -_candidate_score(
                        field_name=field.field_name,
                        candidate=candidate,
                    ),
                    _candidate_key(candidate),
                ),
            )
            top_key = _candidate_key(ranked[0]) if ranked else None
            top1_hit = top_key == selected_key
            if top1_hit:
                top1_hits += 1
            else:
                batch_all_match = False
                failure = {
                    "case_id": case.case_id,
                    "field_name": field.field_name,
                    "expected": selected_key,
                    "actual": top_key,
                }
                failures.append(failure)
                review_packets.append(
                    {
                        "case_id": case.case_id,
                        "subject_key": "document",
                        "field_name": field.field_name,
                        "expected": {
                            "selected_candidate_key": selected_key,
                        },
                        "actual": {
                            "selected_candidate_key": top_key,
                            "candidate_keys": sorted(available_keys),
                        },
                    }
                )

            _update_by_field(
                by_field=by_field,
                field_name=field.field_name,
                recall_hit=recall_hit,
                top1_hit=top1_hit,
            )

        if batch_all_match:
            batch_all_match_hits += 1

    coverage = {
        "total_cases": total_batches,
        "total_candidates": total_field_checks,
        "gold_applicable_rows": total_field_checks,
        "silver_applicable_rows": 0,
        "invariant_rows": 0,
        "distinct_tickers": len(seen_tickers),
        "distinct_filing_years": len(seen_filing_years),
    }
    metrics = {
        "total_batches": total_batches,
        "total_field_checks": total_field_checks,
        "passed": top1_hits,
        "failed": total_field_checks - top1_hits,
        "candidate_recall": candidate_recall_hits / total_field_checks if total_field_checks else 0.0,
        "top1_accuracy": top1_hits / total_field_checks if total_field_checks else 0.0,
        "batch_all_match_rate": batch_all_match_hits / total_batches if total_batches else 0.0,
        "gold_strict_accuracy": top1_hits / total_field_checks if total_field_checks else 0.0,
        "gold_coverage": candidate_recall_hits / total_field_checks if total_field_checks else 0.0,
        "row_selection_accuracy": top1_hits / total_field_checks if total_field_checks else 0.0,
        "not_applicable_precision": 1.0,
        "silver_alignment": 0.0,
        "invariant_pass_rate": 0.0,
    }
    phase_gates = evaluate_phase_gates(
        gates_raw=golden_payload.get("phase_gates", []),
        coverage=coverage,
        metrics=metrics,
        set_values={
            "required_fields": seen_fields,
            "required_form_types": seen_form_types,
            "required_tickers": seen_tickers,
            "required_filing_years": seen_filing_years,
        },
    )
    summary = {
        "coverage": coverage,
        "metrics": metrics,
        "phase_gates": {
            "total": len(phase_gates),
            "passed": len([gate for gate in phase_gates if gate.get("status") == "passed"]),
            "failed": len([gate for gate in phase_gates if gate.get("status") == "failed"]),
            "skipped": 0,
        },
    }
    return NumericBatchEvalResult(
        summary=summary,
        by_field=_finalize_by_field(by_field),
        failures=failures,
        phase_gates=phase_gates,
        review_packets=review_packets,
    )
