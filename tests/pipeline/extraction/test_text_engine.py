from __future__ import annotations

import json

from src.pipeline.extraction.text_contracts import SpanPolicy, TextFieldSpec
from src.pipeline.extraction.text_engine import TextExtractionEngine
from src.pipeline.extraction.text_normalization import NormalizationSuccess


class FakeSectionFiling:
    def __init__(self, sections: dict[str, str]):
        self._sections = sections

    def sections(self) -> dict[str, str]:
        return self._sections


def test_extract_field_honors_span_policy() -> None:
    engine = TextExtractionEngine()
    filing = FakeSectionFiling(
        {
            "Purpose of Transaction": (
                "The investor remains passive and is not seeking board representation."
            )
        }
    )
    spec = TextFieldSpec(
        field_name="beneficial_ownership_intent_quant",
        route="owner",
        form_families=("13D",),
        locators=("section_window",),
        anchor_terms=("purpose of transaction",),
        regex_patterns=(r"(?i)\b(passive|control)\b",),
        output_kind="text",
        qa_rules={},
        span_policy=SpanPolicy(
            anchor_headers=("purpose of transaction",),
            min_tokens=5,
            max_tokens=40,
            must_include=("investor",),
            avoid=("table of contents",),
        ),
    )

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome["status"] == "ok"
    assert outcome["value_text"] == "passive"
    assert outcome["locator_kind"] == "section_window"
    assert outcome["source_section"] == "Purpose of Transaction"
    assert outcome["source_item_no"] is None
    assert outcome["source_heading_path_json"] == '["Purpose of Transaction"]'
    assert '"window_found": true' in outcome["adequacy_signals_json"]
    assert outcome["retry_history_json"] == "[]"
    assert '"selected_value": "passive"' in outcome["selection_trace_json"]


def test_extract_field_rejects_span_policy_failures() -> None:
    engine = TextExtractionEngine()
    filing = FakeSectionFiling(
        {
            "Purpose of Transaction": "Passive.",
        }
    )
    spec = TextFieldSpec(
        field_name="beneficial_ownership_intent_quant",
        route="owner",
        form_families=("13D",),
        locators=("section_window",),
        anchor_terms=("purpose of transaction",),
        regex_patterns=(r"(?i)\b(passive|control)\b",),
        output_kind="text",
        qa_rules={},
        span_policy=SpanPolicy(
            anchor_headers=("purpose of transaction",),
            min_tokens=5,
            max_tokens=40,
        ),
    )

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome == {"status": "error", "error_code": "SPAN_POLICY_FAILED"}


def test_extract_field_returns_normalization_unavailable_for_json_output_without_normalizer() -> None:
    engine = TextExtractionEngine()
    filing = FakeSectionFiling(
        {
            "Purpose of Transaction": (
                "The investor remains passive and is not seeking board representation."
            )
        }
    )
    spec = TextFieldSpec(
        field_name="beneficial_ownership_intent_quant",
        route="owner",
        form_families=("13D",),
        locators=("section_window",),
        anchor_terms=("purpose of transaction",),
        regex_patterns=(r"(?i)\b(passive|control)\b",),
        output_kind="json",
        output_schema="v1/beneficial_ownership_intent_quant",
        qa_rules={},
        span_policy=SpanPolicy(anchor_headers=("purpose of transaction",), min_tokens=5, max_tokens=40),
    )

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome == {"status": "error", "error_code": "NORMALIZATION_UNAVAILABLE"}


def test_extract_field_serializes_schema_valid_json_output() -> None:
    class FakeNormalizer:
        def normalize(self, *, field_spec, schema_ref, selected_span):
            assert field_spec.field_name == "beneficial_ownership_intent_quant"
            assert schema_ref == "v1/beneficial_ownership_intent_quant"
            assert selected_span.value_text == "passive"
            return NormalizationSuccess(
                value={
                    "stance": "passive",
                    "group_formed": False,
                    "horizon": "medium",
                },
                retry_history_json='[{"attempt":1,"status":"selected"}]',
            )

    engine = TextExtractionEngine(normalizer=FakeNormalizer())
    filing = FakeSectionFiling(
        {
            "Purpose of Transaction": (
                "The investor remains passive and is not seeking board representation."
            )
        }
    )
    spec = TextFieldSpec(
        field_name="beneficial_ownership_intent_quant",
        route="owner",
        form_families=("13D",),
        locators=("section_window",),
        anchor_terms=("purpose of transaction",),
        regex_patterns=(r"(?i)\b(passive|control)\b",),
        output_kind="json",
        output_schema="v1/beneficial_ownership_intent_quant",
        qa_rules={},
        span_policy=SpanPolicy(anchor_headers=("purpose of transaction",), min_tokens=5, max_tokens=40),
    )

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome["status"] == "ok"
    assert outcome["value_text"] == "passive"
    assert json.loads(outcome["value_json"]) == {
        "group_formed": False,
        "horizon": "medium",
        "stance": "passive",
    }
    assert json.loads(outcome["retry_history_json"]) == [{"attempt": 1, "status": "selected"}]
    assert json.loads(outcome["adequacy_signals_json"])["schema_validation_passed"] is True
    assert json.loads(outcome["selection_trace_json"])["output_schema"] == "v1/beneficial_ownership_intent_quant"


def test_extract_field_rejects_schema_invalid_json_output() -> None:
    class FakeNormalizer:
        def normalize(self, *, field_spec, schema_ref, selected_span):
            del field_spec, schema_ref, selected_span
            return NormalizationSuccess(value={"stance": "invalid-enum"})

    engine = TextExtractionEngine(normalizer=FakeNormalizer())
    filing = FakeSectionFiling(
        {
            "Purpose of Transaction": (
                "The investor remains passive and is not seeking board representation."
            )
        }
    )
    spec = TextFieldSpec(
        field_name="beneficial_ownership_intent_quant",
        route="owner",
        form_families=("13D",),
        locators=("section_window",),
        anchor_terms=("purpose of transaction",),
        regex_patterns=(r"(?i)\b(passive|control)\b",),
        output_kind="json",
        output_schema="v1/beneficial_ownership_intent_quant",
        qa_rules={},
        span_policy=SpanPolicy(anchor_headers=("purpose of transaction",), min_tokens=5, max_tokens=40),
    )

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome == {"status": "error", "error_code": "SCHEMA_VALIDATION_FAILED"}
