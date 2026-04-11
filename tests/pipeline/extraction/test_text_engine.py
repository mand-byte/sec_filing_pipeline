from __future__ import annotations

from src.pipeline.extraction.text_contracts import SpanPolicy, TextFieldSpec
from src.pipeline.extraction.text_engine import TextExtractionEngine


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
    assert outcome["source_heading_path_json"] == '["Purpose of Transaction"]'
    assert '"window_found": true' in outcome["adequacy_signals_json"]
    assert outcome["retry_history_json"] == "[]"


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
