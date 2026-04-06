from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict


ReviewReason = Literal["first_seen_for_issuer", "first_seen_template", "outlier_vs_history"]


class ReviewGateDecision(TypedDict):
    decision: Literal["auto_accept", "needs_review"]
    reason: ReviewReason | None
    priority: str | None


class ReviewStats(Protocol):
    def issuer_field_count(self, cik: str, route: str, field_name: str) -> int: ...

    def template_field_count(self, template_hash: str, route: str, field_name: str) -> int: ...

    def zscore(self, value_numeric: float, route: str, field_name: str) -> float | None: ...


@dataclass(frozen=True)
class ReviewGateInput:
    cik: str
    route: str
    field_name: str
    template_hash: str | None
    value_numeric: float | int | None


REVIEW_PRIORITY_BY_REASON: dict[ReviewReason, str] = {
    "first_seen_for_issuer": "high",
    "first_seen_template": "medium",
    "outlier_vs_history": "high",
}


def evaluate_review_gate(
    *,
    candidate: ReviewGateInput,
    stats: ReviewStats,
    outlier_zscore_threshold: float = 3.0,
) -> ReviewGateDecision:
    if stats.issuer_field_count(candidate.cik, candidate.route, candidate.field_name) <= 0:
        reason: ReviewReason = "first_seen_for_issuer"
        return {
            "decision": "needs_review",
            "reason": reason,
            "priority": REVIEW_PRIORITY_BY_REASON[reason],
        }

    if candidate.template_hash and stats.template_field_count(
        candidate.template_hash,
        candidate.route,
        candidate.field_name,
    ) <= 0:
        reason = "first_seen_template"
        return {
            "decision": "needs_review",
            "reason": reason,
            "priority": REVIEW_PRIORITY_BY_REASON[reason],
        }

    if isinstance(candidate.value_numeric, (int, float)) and not isinstance(candidate.value_numeric, bool):
        z_score = stats.zscore(float(candidate.value_numeric), candidate.route, candidate.field_name)
        if isinstance(z_score, (int, float)) and not isinstance(z_score, bool) and z_score > outlier_zscore_threshold:
            reason = "outlier_vs_history"
            return {
                "decision": "needs_review",
                "reason": reason,
                "priority": REVIEW_PRIORITY_BY_REASON[reason],
            }

    return {
        "decision": "auto_accept",
        "reason": None,
        "priority": None,
    }
