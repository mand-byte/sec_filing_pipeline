from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Literal, TypedDict

from src.pipeline.extraction.text_contracts import TextFieldSpec, TextLocatorKind
from src.pipeline.extraction.text_locators import run_text_locator_chain


class TextExtractionOk(TypedDict):
    status: Literal["ok"]
    value_text: str
    value_json: None
    locator_kind: TextLocatorKind
    locator_path: str
    source_span: str


class TextExtractionFailure(TypedDict):
    status: Literal["error"]
    error_code: str


TextExtractionOutcome = TextExtractionOk | TextExtractionFailure


class TextExtractionEngine:
    def _qa_check(self, value_text: str, qa_rules: Mapping[str, int | float | bool]) -> str | None:
        min_len = qa_rules.get("min_len")
        if isinstance(min_len, (int, float)) and not isinstance(min_len, bool) and len(value_text) < int(min_len):
            return "QA_FAILED"

        max_len = qa_rules.get("max_len")
        if isinstance(max_len, (int, float)) and not isinstance(max_len, bool) and len(value_text) > int(max_len):
            return "QA_FAILED"

        return None

    def extract_field(self, *, filing: object, field_spec: TextFieldSpec) -> TextExtractionOutcome:
        window_hit = run_text_locator_chain(filing=filing, locators=field_spec.locators, anchors=field_spec.anchor_terms)
        if window_hit is None:
            return {"status": "error", "error_code": "WINDOW_NOT_FOUND"}

        window_text = window_hit["value"]

        for pattern in field_spec.regex_patterns:
            matches = list(re.finditer(pattern, window_text))
            if not matches:
                continue

            distinct_matches: dict[str, re.Match[str]] = {}
            for match in matches:
                group_index = 1 if match.lastindex else 0
                extracted = match.group(group_index).strip()
                if extracted and extracted not in distinct_matches:
                    distinct_matches[extracted] = match

            if not distinct_matches:
                continue

            if len(distinct_matches) > 1:
                return {"status": "error", "error_code": "MULTIPLE_CANDIDATES"}

            value_text, source_match = next(iter(distinct_matches.items()))
            qa_error = self._qa_check(value_text, field_spec.qa_rules)
            if qa_error is not None:
                return {"status": "error", "error_code": qa_error}

            source_group = 1 if source_match.lastindex else 0
            span_start, span_end = source_match.span(source_group)

            return {
                "status": "ok",
                "value_text": value_text,
                "value_json": None,
                "locator_kind": window_hit["locator_kind"],
                "locator_path": window_hit["locator_path"],
                "source_span": f"{span_start}:{span_end}",
            }

        return {"status": "error", "error_code": "PATTERN_NOT_MATCHED"}
