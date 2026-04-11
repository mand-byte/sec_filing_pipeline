from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Literal, TypedDict

from src.pipeline.extraction.text_contracts import SpanPolicy, TextFieldSpec, TextLocatorKind
from src.pipeline.extraction.text_locators import run_text_locator


class TextExtractionOk(TypedDict):
    status: Literal["ok"]
    value_text: str
    value_json: None
    locator_kind: TextLocatorKind
    locator_path: str
    source_span: str
    source_section: str | None
    source_item_no: str | None
    source_locator_json: str
    source_heading_path_json: str
    source_block_offsets_json: str
    adequacy_signals_json: str
    retry_history_json: str
    selection_trace_json: str


class TextExtractionFailure(TypedDict):
    status: Literal["error"]
    error_code: str


TextExtractionOutcome = TextExtractionOk | TextExtractionFailure


class TextExtractionEngine:
    def _heading_path_json(self, *, window_hit: Mapping[str, object]) -> str:
        locator_path = str(window_hit["locator_path"])
        heading = locator_path
        if "[" in locator_path and locator_path.endswith("]"):
            heading = locator_path.split("[", 1)[1][:-1]
        return json.dumps([heading], ensure_ascii=False)

    def _block_offsets_json(
        self,
        *,
        window_hit: Mapping[str, object],
        span_start: int,
        span_end: int,
        source_start: int,
        source_end: int,
    ) -> str:
        payload = {
            "window_base": int(window_hit["window_base"]),
            "span_start_in_window": span_start,
            "span_end_in_window": span_end,
            "source_start": source_start,
            "source_end": source_end,
        }
        if "item_body_offset" in window_hit and isinstance(window_hit.get("item_body_offset"), int):
            payload["item_body_offset"] = int(window_hit["item_body_offset"])
        if "section_body_offset" in window_hit and isinstance(window_hit.get("section_body_offset"), int):
            payload["section_body_offset"] = int(window_hit["section_body_offset"])
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _adequacy_signals_json(
        self,
        *,
        field_spec: TextFieldSpec,
        window_text: str,
        pattern: str,
        distinct_match_count: int,
        value_text: str,
    ) -> str:
        window_token_count = len(re.findall(r"\S+", window_text))
        value_token_count = len(re.findall(r"\S+", value_text))
        preferred_tokens_match = None
        if field_spec.span_policy is not None and field_spec.span_policy.preferred_tokens is not None:
            minimum, maximum = field_spec.span_policy.preferred_tokens
            preferred_tokens_match = minimum <= window_token_count <= maximum
        payload = {
            "window_found": True,
            "pattern": pattern,
            "distinct_match_count": distinct_match_count,
            "window_token_count": window_token_count,
            "value_token_count": value_token_count,
            "value_length": len(value_text),
            "span_policy_applied": field_spec.span_policy is not None,
            "preferred_tokens_match": preferred_tokens_match,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _span_policy_error(self, *, window_text: str, span_policy: SpanPolicy) -> str | None:
        lowered_window = window_text.casefold()
        header_text = window_text.splitlines()[0].strip().casefold() if window_text.splitlines() else ""

        if span_policy.anchor_headers:
            if not any(anchor.casefold() in header_text for anchor in span_policy.anchor_headers):
                return "SPAN_POLICY_FAILED"

        token_count = len(re.findall(r"\S+", window_text))
        min_tokens = span_policy.min_tokens
        max_tokens = span_policy.max_tokens
        if span_policy.preferred_tokens is not None:
            preferred_min, preferred_max = span_policy.preferred_tokens
            min_tokens = max(min_tokens, preferred_min)
            max_tokens = preferred_max if max_tokens == 0 else min(max_tokens, preferred_max)

        if min_tokens > 0 and token_count < min_tokens:
            return "SPAN_POLICY_FAILED"
        if max_tokens > 0 and token_count > max_tokens:
            return "SPAN_POLICY_FAILED"

        if span_policy.must_include:
            if any(required.casefold() not in lowered_window for required in span_policy.must_include):
                return "SPAN_POLICY_FAILED"

        if span_policy.avoid:
            if any(avoid.casefold() in lowered_window for avoid in span_policy.avoid):
                return "SPAN_POLICY_FAILED"

        return None

    def _qa_check(self, value_text: str, qa_rules: Mapping[str, int | float | bool]) -> str | None:
        min_len = qa_rules.get("min_len")
        if isinstance(min_len, (int, float)) and not isinstance(min_len, bool) and len(value_text) < int(min_len):
            return "QA_FAILED"

        max_len = qa_rules.get("max_len")
        if isinstance(max_len, (int, float)) and not isinstance(max_len, bool) and len(value_text) > int(max_len):
            return "QA_FAILED"

        return None

    def extract_field(self, *, filing: object, field_spec: TextFieldSpec) -> TextExtractionOutcome:
        if field_spec.output_kind != "text":
            return {"status": "error", "error_code": "NORMALIZATION_FAILED"}

        best_failure: str = "PATTERN_NOT_MATCHED"
        failure_priority = {
            "PATTERN_NOT_MATCHED": 0,
            "MULTIPLE_CANDIDATES": 1,
            "QA_FAILED": 2,
            "SPAN_POLICY_FAILED": 3,
        }
        saw_window = False

        for locator in field_spec.locators:
            window_hit = run_text_locator(filing=filing, locator=locator, anchors=field_spec.anchor_terms)
            if window_hit is None:
                continue

            saw_window = True
            window_text = window_hit["value"]
            if field_spec.span_policy is not None:
                span_policy_error = self._span_policy_error(
                    window_text=window_text,
                    span_policy=field_spec.span_policy,
                )
                if span_policy_error is not None:
                    if failure_priority[span_policy_error] > failure_priority[best_failure]:
                        best_failure = span_policy_error
                    continue

            for pattern in field_spec.regex_patterns:
                matches = list(re.finditer(pattern, window_text))
                if not matches:
                    continue

                distinct_matches: dict[str, tuple[str, re.Match[str]]] = {}
                for match in matches:
                    group_index = 1 if match.lastindex else 0
                    extracted = match.group(group_index).strip()
                    normalized_extracted = extracted.casefold()
                    if extracted and normalized_extracted not in distinct_matches:
                        distinct_matches[normalized_extracted] = (extracted, match)

                if not distinct_matches:
                    continue

                if len(distinct_matches) > 1:
                    if failure_priority["MULTIPLE_CANDIDATES"] > failure_priority[best_failure]:
                        best_failure = "MULTIPLE_CANDIDATES"
                    continue

                value_text, source_match = next(iter(distinct_matches.values()))
                qa_error = self._qa_check(value_text, field_spec.qa_rules)
                if qa_error is not None:
                    if failure_priority[qa_error] > failure_priority[best_failure]:
                        best_failure = qa_error
                    continue

                source_group = 1 if source_match.lastindex else 0
                span_start, span_end = source_match.span(source_group)
                source_start = window_hit["window_base"] + span_start
                source_end = window_hit["window_base"] + span_end

                source_span = f"{source_start}:{source_end}"
                if window_hit["locator_kind"] == "item_window":
                    item_body_offset = window_hit.get("item_body_offset")
                    if isinstance(item_body_offset, int):
                        if span_end <= item_body_offset:
                            source_span = f"header:{span_start}:{span_end}"
                        else:
                            body_start = max(0, span_start - item_body_offset)
                            body_end = max(0, span_end - item_body_offset)
                            source_span = f"{body_start}:{body_end}"
                elif window_hit["locator_kind"] == "section_window":
                    section_body_offset = window_hit.get("section_body_offset")
                    if isinstance(section_body_offset, int):
                        if span_end <= section_body_offset:
                            source_span = f"header:{span_start}:{span_end}"
                        else:
                            body_start = max(0, span_start - section_body_offset)
                            body_end = max(0, span_end - section_body_offset)
                            source_span = f"{body_start}:{body_end}"

                return {
                    "status": "ok",
                    "value_text": value_text,
                    "value_json": None,
                    "locator_kind": window_hit["locator_kind"],
                    "locator_path": window_hit["locator_path"],
                    "source_span": source_span,
                    "source_section": window_hit.get("source_section"),
                    "source_item_no": window_hit.get("source_item_no"),
                    "source_locator_json": json.dumps(
                        {
                            "locator_kind": window_hit["locator_kind"],
                            "locator_path": window_hit["locator_path"],
                            "source_section": window_hit.get("source_section"),
                            "source_item_no": window_hit.get("source_item_no"),
                            "source_span": source_span,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "source_heading_path_json": self._heading_path_json(window_hit=window_hit),
                    "source_block_offsets_json": self._block_offsets_json(
                        window_hit=window_hit,
                        span_start=span_start,
                        span_end=span_end,
                        source_start=source_start,
                        source_end=source_end,
                    ),
                    "adequacy_signals_json": self._adequacy_signals_json(
                        field_spec=field_spec,
                        window_text=window_text,
                        pattern=pattern,
                        distinct_match_count=len(distinct_matches),
                        value_text=value_text,
                    ),
                    "retry_history_json": "[]",
                    "selection_trace_json": json.dumps(
                        {
                            "pattern": pattern,
                            "distinct_match_count": len(distinct_matches),
                            "selected_value": value_text,
                            "locator_kind": window_hit["locator_kind"],
                            "locator_path": window_hit["locator_path"],
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                }

        if not saw_window:
            return {"status": "error", "error_code": "WINDOW_NOT_FOUND"}

        return {"status": "error", "error_code": best_failure}
