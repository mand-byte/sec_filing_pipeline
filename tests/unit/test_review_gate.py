from src.pipeline.review.review_gate import ReviewGateInput, evaluate_review_gate


class _Stats:
    def __init__(
        self,
        *,
        issuer_field_count: int,
        template_field_count: int,
        zscore: float | None,
    ) -> None:
        self._issuer_field_count = issuer_field_count
        self._template_field_count = template_field_count
        self._zscore = zscore

    def issuer_field_count(self, cik: str, route: str, field_name: str) -> int:
        del cik, route, field_name
        return self._issuer_field_count

    def template_field_count(self, template_hash: str, route: str, field_name: str) -> int:
        del template_hash, route, field_name
        return self._template_field_count

    def zscore(self, value_numeric: float, route: str, field_name: str) -> float | None:
        del value_numeric, route, field_name
        return self._zscore


def test_review_gate_marks_first_seen_for_issuer() -> None:
    outcome = evaluate_review_gate(
        candidate=ReviewGateInput(
            cik="0000320193",
            route="owner",
            field_name="intent_text",
            template_hash="template-a",
            value_numeric=2.0,
        ),
        stats=_Stats(issuer_field_count=0, template_field_count=10, zscore=0.5),
    )

    assert outcome == {
        "decision": "needs_review",
        "reason": "first_seen_for_issuer",
        "priority": "high",
    }


def test_review_gate_marks_first_seen_template_after_issuer_seen() -> None:
    outcome = evaluate_review_gate(
        candidate=ReviewGateInput(
            cik="0000320193",
            route="owner",
            field_name="intent_text",
            template_hash="template-new",
            value_numeric=1.0,
        ),
        stats=_Stats(issuer_field_count=5, template_field_count=0, zscore=0.4),
    )

    assert outcome == {
        "decision": "needs_review",
        "reason": "first_seen_template",
        "priority": "medium",
    }


def test_review_gate_marks_outlier_vs_history() -> None:
    outcome = evaluate_review_gate(
        candidate=ReviewGateInput(
            cik="0000320193",
            route="owner",
            field_name="cash_impact_text",
            template_hash="template-a",
            value_numeric=10.0,
        ),
        stats=_Stats(issuer_field_count=5, template_field_count=6, zscore=3.1),
    )

    assert outcome == {
        "decision": "needs_review",
        "reason": "outlier_vs_history",
        "priority": "high",
    }


def test_review_gate_auto_accepts_when_history_is_stable() -> None:
    outcome = evaluate_review_gate(
        candidate=ReviewGateInput(
            cik="0000320193",
            route="owner",
            field_name="cash_impact_text",
            template_hash="template-a",
            value_numeric=2.0,
        ),
        stats=_Stats(issuer_field_count=5, template_field_count=6, zscore=2.9),
    )

    assert outcome == {
        "decision": "auto_accept",
        "reason": None,
        "priority": None,
    }


def test_review_gate_uses_deterministic_reason_order() -> None:
    outcome = evaluate_review_gate(
        candidate=ReviewGateInput(
            cik="0000320193",
            route="owner",
            field_name="cash_impact_text",
            template_hash="template-new",
            value_numeric=100.0,
        ),
        stats=_Stats(issuer_field_count=0, template_field_count=0, zscore=7.2),
    )

    assert outcome == {
        "decision": "needs_review",
        "reason": "first_seen_for_issuer",
        "priority": "high",
    }


def test_review_gate_accepts_non_numeric_values_when_seen() -> None:
    outcome = evaluate_review_gate(
        candidate=ReviewGateInput(
            cik="0000320193",
            route="owner",
            field_name="intent_text",
            template_hash="template-a",
            value_numeric=None,
        ),
        stats=_Stats(issuer_field_count=5, template_field_count=6, zscore=9.9),
    )

    assert outcome == {
        "decision": "auto_accept",
        "reason": None,
        "priority": None,
    }
