from __future__ import annotations


REVIEW_ERROR_CODES: tuple[str, ...] = (
    "locator_miss",
    "row_match_error",
    "unit_scaling",
    "period_selection",
    "dimension_selection",
    "schema_mismatch",
    "not_applicable_false_positive",
)


def normalize_review_error_code(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized not in REVIEW_ERROR_CODES:
        allowed = ", ".join(REVIEW_ERROR_CODES)
        raise ValueError(f"error_code must be one of: {allowed}")
    return normalized
