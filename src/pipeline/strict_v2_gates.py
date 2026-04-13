from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def selector_active(selector_context: Mapping[str, Any]) -> bool:
    """Check whether any strict-v2 selector is actively filtering the run."""
    return any(selector_context.values())


def selector_matches_expected(actual: str | None, expected: object) -> bool:
    """Match one selector value against a scalar or sequence expectation."""
    if expected is None:
        return True
    if isinstance(expected, Sequence) and not isinstance(expected, (str, bytes)):
        return actual in {str(value) for value in expected}
    return actual == str(expected)


def gate_applies_to_selectors(gate: Mapping[str, Any], selector_context: Mapping[str, Any]) -> bool:
    """Decide whether a phase gate applies to the current selector slice."""
    applies_when = gate.get("applies_when")
    if not isinstance(applies_when, Mapping):
        return not selector_active(selector_context)

    return all(
        selector_matches_expected(
            None if selector_context.get(str(key)) is None else str(selector_context.get(str(key))),
            expected,
        )
        for key, expected in applies_when.items()
    )


def compare_gate_scalar(*, actual: object, expected: object, comparator: str) -> bool:
    """Compare one scalar gate rule using equality, min, or max semantics."""
    if comparator in {"min", "max"}:
        if not isinstance(actual, (int, float)) or isinstance(actual, bool):
            return False
        if not isinstance(expected, (int, float)) or isinstance(expected, bool):
            return False
        return actual >= expected if comparator == "min" else actual <= expected
    return actual == expected


def gate_scalar_violation(
    *,
    namespace: str,
    key: str,
    expected: object,
    actual_values: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Return one scalar gate violation payload when a rule fails."""
    comparator = "eq"
    actual_key = key
    if key.startswith("min_"):
        comparator = "min"
        actual_key = key.removeprefix("min_")
    elif key.startswith("max_"):
        comparator = "max"
        actual_key = key.removeprefix("max_")

    actual = actual_values.get(actual_key)
    if compare_gate_scalar(actual=actual, expected=expected, comparator=comparator):
        return None
    return {
        "namespace": namespace,
        "key": key,
        "actual_key": actual_key,
        "comparator": comparator,
        "expected": expected,
        "actual": actual,
    }


def required_set_violation(
    *,
    namespace: str,
    key: str,
    required_values: object,
    actual_values: set[str],
) -> dict[str, Any] | None:
    """Return one set-membership gate violation when required values are missing."""
    if not isinstance(required_values, Sequence) or isinstance(required_values, (str, bytes)):
        return {
            "namespace": namespace,
            "key": key,
            "expected": required_values,
            "actual": sorted(actual_values),
            "error": "expected sequence",
        }

    expected_set = {str(value) for value in required_values}
    missing = sorted(expected_set - actual_values)
    if not missing:
        return None
    return {
        "namespace": namespace,
        "key": key,
        "expected": sorted(expected_set),
        "actual": sorted(actual_values),
        "missing": missing,
    }


def evaluate_phase_gates(
    *,
    gates_raw: object,
    coverage: Mapping[str, Any],
    metrics: Mapping[str, Any],
    set_values: Mapping[str, set[str]],
    selector_context: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate strict-v2 phase gates against coverage and metric payloads."""
    if not isinstance(gates_raw, list):
        return []

    effective_selector_context = selector_context or {}
    results: list[dict[str, Any]] = []
    for index, gate_raw in enumerate(gates_raw):
        if not isinstance(gate_raw, Mapping):
            continue
        name = str(gate_raw.get("name", f"phase_gate_{index + 1}"))
        if effective_selector_context and not gate_applies_to_selectors(gate_raw, effective_selector_context):
            results.append({"name": name, "status": "skipped", "reason": "selector mismatch"})
            continue

        violations: list[dict[str, Any]] = []
        coverage_rules = gate_raw.get("coverage", {})
        if isinstance(coverage_rules, Mapping):
            for key, expected in coverage_rules.items():
                key_text = str(key)
                if key_text in set_values:
                    violation = required_set_violation(
                        namespace="coverage",
                        key=key_text,
                        required_values=expected,
                        actual_values=set_values[key_text],
                    )
                else:
                    violation = gate_scalar_violation(
                        namespace="coverage",
                        key=key_text,
                        expected=expected,
                        actual_values=coverage,
                    )
                if violation is not None:
                    violations.append(violation)

        metric_rules = gate_raw.get("metrics", {})
        if isinstance(metric_rules, Mapping):
            for key, expected in metric_rules.items():
                violation = gate_scalar_violation(
                    namespace="metrics",
                    key=str(key),
                    expected=expected,
                    actual_values=metrics,
                )
                if violation is not None:
                    violations.append(violation)

        results.append(
            {
                "name": name,
                "status": "passed" if not violations else "failed",
                "violations": violations,
            }
        )

    return results
