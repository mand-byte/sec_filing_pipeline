from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Literal, TypedDict

from src.pipeline.extraction.contracts import LocatorKind, NumericFieldSpec, ValueType
from src.pipeline.extraction.locators import run_locator_chain


class ExtractionOk(TypedDict):
    status: Literal["ok"]
    value_raw: str | float | int
    value_normalized: float | int
    locator_kind: LocatorKind
    locator_path: str


class ExtractionFailure(TypedDict):
    status: Literal["error"]
    error_code: str


ExtractionOutcome = ExtractionOk | ExtractionFailure


class NumericExtractionEngine:
    def _normalize_number(self, value: object, value_type: ValueType) -> float | int:
        if isinstance(value, bool):
            raise TypeError("boolean is not a numeric extraction value")

        if isinstance(value, (int, float)):
            numeric = float(value)
        elif isinstance(value, str):
            cleaned = value.strip().replace(",", "")
            if cleaned == "":
                raise ValueError("empty numeric string")
            numeric = float(cleaned)
        else:
            raise TypeError("unsupported numeric value type")

        if not math.isfinite(numeric):
            raise ValueError("non-finite numeric value")

        if value_type == "int":
            if not numeric.is_integer():
                raise ValueError("non-integer value for int field")
            return int(numeric)

        return numeric

    def _qa_check(self, value: float | int, qa_rules: Mapping[str, float | int | bool]) -> str | None:
        min_rule = qa_rules.get("min")
        if isinstance(min_rule, (int, float)) and not isinstance(min_rule, bool) and value < float(min_rule):
            return "VALUE_OUT_OF_RANGE"

        max_rule = qa_rules.get("max")
        if isinstance(max_rule, (int, float)) and not isinstance(max_rule, bool) and value > float(max_rule):
            return "VALUE_OUT_OF_RANGE"

        if qa_rules.get("nonnegative") is True and value < 0:
            return "VALUE_OUT_OF_RANGE"

        return None

    def extract_field(self, *, filing: object, field_spec: NumericFieldSpec) -> ExtractionOutcome:
        locator_hit = run_locator_chain(filing=filing, locators=field_spec.locators)
        if locator_hit is None:
            return {"status": "error", "error_code": "FIELD_NOT_FOUND"}

        raw_candidate: object = locator_hit["value"]
        if isinstance(raw_candidate, dict) and "value" in raw_candidate:
            raw_candidate = raw_candidate["value"]

        try:
            normalized = self._normalize_number(raw_candidate, field_spec.value_type)
        except (TypeError, ValueError, OverflowError):
            return {"status": "error", "error_code": "TYPE_MISMATCH"}

        qa_error = self._qa_check(normalized, field_spec.qa_rules)
        if qa_error is not None:
            return {"status": "error", "error_code": qa_error}

        if not isinstance(raw_candidate, (str, int, float)):
            return {"status": "error", "error_code": "TYPE_MISMATCH"}

        return {
            "status": "ok",
            "value_raw": raw_candidate,
            "value_normalized": normalized,
            "locator_kind": locator_hit["locator_kind"],
            "locator_path": locator_hit["locator_path"],
        }
