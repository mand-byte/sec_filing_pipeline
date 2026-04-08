from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import math
from pathlib import Path
from typing import Any

import yaml

_FIELD_CONCEPTS: dict[str, tuple[str, ...]] = {
    "total_revenue": (
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:Revenues",
        "us-gaap:SalesRevenueNet",
    ),
    "operating_income": ("us-gaap:OperatingIncomeLoss",),
    "net_income": ("us-gaap:NetIncomeLoss", "us-gaap:ProfitLoss"),
}


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


def load_10q_numeric_batch_cases(golden_path: Path) -> list[NumericBatchCase]:
    payload = yaml.safe_load(golden_path.read_text(encoding="utf-8")) or {}
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


def build_adjudication_packet(
    *,
    case_id: str,
    field_name: str,
    ticker: str,
    form_type: str,
    filing_period: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    sorted_candidates = sorted(candidates, key=lambda candidate: str(candidate.get("fact_key") or ""))
    return {
        "case_id": case_id,
        "field_name": field_name,
        "ticker": ticker,
        "form_type": form_type,
        "filing_period": filing_period,
        "candidates": [
            {
                "fact_key": candidate.get("fact_key"),
                "value": candidate.get("value"),
                "concept": candidate.get("concept"),
                "statement_type": candidate.get("statement_type"),
                "dimensioned": candidate.get("dimensioned"),
                "evidence_snippet_text": candidate.get("evidence", {}).get("snippet_text"),
            }
            for candidate in sorted_candidates
        ],
    }


def classify_disagreement(
    *,
    golden_candidate_key: str | None,
    rule_candidate_key: str | None,
    agent_candidate_key: str | None,
) -> dict[str, str]:
    if rule_candidate_key == golden_candidate_key and agent_candidate_key == golden_candidate_key:
        return {"disagreement_type": "NONE", "review_recommendation": "keep_golden"}
    if rule_candidate_key != golden_candidate_key and agent_candidate_key == golden_candidate_key:
        return {"disagreement_type": "A", "review_recommendation": "review_rule"}
    if rule_candidate_key == golden_candidate_key and agent_candidate_key != golden_candidate_key:
        return {"disagreement_type": "B", "review_recommendation": "keep_golden"}
    if (
        rule_candidate_key == agent_candidate_key
        and rule_candidate_key is not None
        and rule_candidate_key != golden_candidate_key
    ):
        return {"disagreement_type": "D", "review_recommendation": "re_adjudicate_golden"}
    if rule_candidate_key != golden_candidate_key and agent_candidate_key != golden_candidate_key:
        return {"disagreement_type": "C", "review_recommendation": "review_rule"}
    return {"disagreement_type": "NONE", "review_recommendation": "keep_golden"}


def build_adjudication_packet(
    *,
    case_id: str,
    field_name: str,
    ticker: str,
    form_type: str,
    filing_period: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    sorted_candidates = sorted(candidates, key=lambda candidate: str(candidate.get("fact_key") or ""))
    return {
        "case_id": case_id,
        "field_name": field_name,
        "ticker": ticker,
        "form_type": form_type,
        "filing_period": filing_period,
        "candidates": [
            {
                "fact_key": candidate.get("fact_key"),
                "value": candidate.get("value"),
                "concept": candidate.get("concept"),
                "statement_type": candidate.get("statement_type"),
                "dimensioned": candidate.get("dimensioned"),
                "evidence_snippet_text": candidate.get("evidence", {}).get("snippet_text"),
            }
            for candidate in sorted_candidates
        ],
    }


def classify_disagreement(
    *,
    golden_candidate_key: str | None,
    rule_candidate_key: str | None,
    agent_candidate_key: str | None,
) -> dict[str, str]:
    if rule_candidate_key == golden_candidate_key and agent_candidate_key == golden_candidate_key:
        return {"disagreement_type": "NONE", "review_recommendation": "keep_golden"}
    if rule_candidate_key != golden_candidate_key and agent_candidate_key == golden_candidate_key:
        return {"disagreement_type": "A", "review_recommendation": "review_rule"}
    if rule_candidate_key == golden_candidate_key and agent_candidate_key != golden_candidate_key:
        return {"disagreement_type": "B", "review_recommendation": "keep_golden"}
    if (
        rule_candidate_key == agent_candidate_key
        and rule_candidate_key is not None
        and rule_candidate_key != golden_candidate_key
    ):
        return {"disagreement_type": "D", "review_recommendation": "re_adjudicate_golden"}
    if rule_candidate_key != golden_candidate_key and agent_candidate_key != golden_candidate_key:
        return {"disagreement_type": "C", "review_recommendation": "review_rule"}
    return {"disagreement_type": "NONE", "review_recommendation": "keep_golden"}


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


def _duration_days(candidate: dict[str, Any]) -> int | None:
    period_start = candidate.get("period_start")
    period_end = candidate.get("period_end")
    if not period_start or not period_end:
        return None
    try:
        start = date.fromisoformat(str(period_start))
        end = date.fromisoformat(str(period_end))
    except ValueError:
        return None
    return (end - start).days + 1


def _candidate_score(*, field_name: str, candidate: dict[str, Any], filing_year: int, filing_period: str) -> int:
    score = 0
    if str(candidate.get("concept")) in _FIELD_CONCEPTS.get(field_name, ()):  # concept match
        score += 6
    if candidate.get("statement_type") == "IncomeStatement":
        score += 5
    if candidate.get("dimensioned") is False:
        score += 4
    if candidate.get("fiscal_year") == filing_year:
        score += 4
    if str(candidate.get("fiscal_period")) == filing_period:
        score += 3

    duration = _duration_days(candidate)
    if duration is not None and 70 <= duration <= 110:
        score += 4
    elif duration is not None and duration >= 150:
        score -= 2

    if candidate.get("dimensioned") is True:
        score -= 4
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
    cases = load_10q_numeric_batch_cases(golden_path)
    total_batches = len(cases)
    total_field_checks = 0
    candidate_recall_hits = 0
    top1_hits = 0
    batch_all_match_hits = 0
    failures: list[dict[str, Any]] = []
    by_field: dict[str, dict[str, int]] = {}

    for case in cases:
        snapshot_path = snapshot_dir / f"{case.case_id}.json"
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        snapshot_fields = {
            str(field["field_name"]): list(field.get("candidate_pool", []))
            for field in payload.get("fields", [])
        }

        batch_all_match = True
        for field in case.fields:
            total_field_checks += 1
            candidates = snapshot_fields.get(field.field_name, [])
            selected_key = field.adjudication.get("selected_candidate_key")
            available_keys = {candidate.get("fact_key") for candidate in candidates}
            recall_hit = selected_key in available_keys
            if recall_hit:
                candidate_recall_hits += 1

            ranked = sorted(
                candidates,
                key=lambda candidate: (
                    -_candidate_score(
                        field_name=field.field_name,
                        candidate=candidate,
                        filing_year=case.filing_year,
                        filing_period=case.filing_period,
                    ),
                    str(candidate.get("fact_key") or ""),
                ),
            )
            top_key = ranked[0].get("fact_key") if ranked else None
            top1_hit = top_key == selected_key
            if top1_hit:
                top1_hits += 1
            else:
                batch_all_match = False
                failures.append(
                    {
                        "case_id": case.case_id,
                        "field_name": field.field_name,
                        "expected": selected_key,
                        "actual": top_key,
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

    summary = {
        "metrics": {
            "total_batches": total_batches,
            "total_field_checks": total_field_checks,
            "candidate_recall": candidate_recall_hits / total_field_checks if total_field_checks else 0.0,
            "top1_accuracy": top1_hits / total_field_checks if total_field_checks else 0.0,
            "batch_all_match_rate": batch_all_match_hits / total_batches if total_batches else 0.0,
        }
    }
    return NumericBatchEvalResult(
        summary=summary,
        by_field=_finalize_by_field(by_field),
        failures=failures,
    )
