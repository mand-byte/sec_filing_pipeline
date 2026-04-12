from __future__ import annotations

import json
from types import SimpleNamespace

from src.pipeline.extraction.text_contracts import TextFieldSpec
from src.pipeline.extraction.text_normalization import (
    HttpJsonSpanNormalizer,
    RegexJsonSpanNormalizer,
    SelectedSpan,
    normalizer_from_settings,
)


def _selected_span() -> SelectedSpan:
    return SelectedSpan(
        value_text="Entry into a material definitive agreement.",
        locator_kind="section_window",
        locator_path="sections[Current report]",
        source_span="0:44",
        source_section="Current report",
        source_item_no="1.01",
        source_locator_json='{"locator_kind":"section_window"}',
        source_heading_path_json='["Current report"]',
        source_block_offsets_json='{"source_start":0,"source_end":44}',
        adequacy_signals_json='{"window_found":true}',
        retry_history_json="[]",
        selection_trace_json='{"selected_value":"agreement"}',
    )


def _current_event_spec() -> TextFieldSpec:
    return TextFieldSpec(
        field_name="current_event_quant",
        route="issuer",
        form_families=("8-K",),
        locators=("section_window",),
        anchor_terms=("current report",),
        regex_patterns=(r"(?i)\bagreement\b",),
        output_kind="json",
        output_schema="v1/current_event_quant",
        qa_rules={},
        normalizer_overrides={"mode": "regex_json"},
    )


def test_http_json_span_normalizer_accepts_value_json_payload(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        assert request.full_url == "https://example.test/normalize"
        assert timeout == 12.5
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["text"] == "Entry into a material definitive agreement."

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {
                        "value_json": {
                            "event_type": "agreement",
                            "materiality_score": 4,
                            "cash_impact_usd": None,
                            "dilution_pct": None,
                        },
                        "retry_history_json": '[{"attempt":1,"status":"http_json"}]',
                    }
                ).encode("utf-8")

        return _Response()

    monkeypatch.setattr("src.pipeline.extraction.text_normalization.urlopen", fake_urlopen)
    normalizer = HttpJsonSpanNormalizer(
        base_url="https://example.test/normalize",
        model="fake-model",
        api_key="secret",
        timeout_seconds=12.5,
    )

    outcome = normalizer.normalize(
        field_spec=_current_event_spec(),
        schema_ref="v1/current_event_quant",
        selected_span=_selected_span(),
    )

    assert outcome.value["event_type"] == "agreement"
    assert json.loads(outcome.retry_history_json)[0]["status"] == "http_json"
    assert json.loads(outcome.selection_trace_json)["normalizer_model"] == "fake-model"


def test_http_json_span_normalizer_uses_normalizer_input_text_and_captures_adequacy_signals(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        del timeout
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["text"] == "Full bounded span with surrounding context."

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {
                        "value_json": {
                            "event_type": "agreement",
                            "materiality_score": 4,
                            "cash_impact_usd": None,
                            "dilution_pct": None,
                        },
                        "adequacy_signals": {
                            "confidence": 0.91,
                            "sufficient_context": True,
                            "multiple_candidate_targets": False,
                        },
                    }
                ).encode("utf-8")

        return _Response()

    monkeypatch.setattr("src.pipeline.extraction.text_normalization.urlopen", fake_urlopen)
    normalizer = HttpJsonSpanNormalizer(
        base_url="https://example.test/normalize",
        model="fake-model",
        api_key=None,
        timeout_seconds=5.0,
    )

    outcome = normalizer.normalize(
        field_spec=_current_event_spec(),
        schema_ref="v1/current_event_quant",
        selected_span=SelectedSpan(
            value_text="agreement",
            locator_kind="section_window",
            locator_path="sections[Current report]",
            source_span="0:9",
            source_section="Current report",
            source_item_no="1.01",
            source_locator_json='{"locator_kind":"section_window"}',
            source_heading_path_json='["Current report"]',
            source_block_offsets_json='{"source_start":0,"source_end":9}',
            adequacy_signals_json='{"window_found":true}',
            retry_history_json="[]",
            selection_trace_json='{"selected_value":"agreement"}',
            normalizer_input_text="Full bounded span with surrounding context.",
        ),
    )

    assert json.loads(outcome.adequacy_signals_json)["confidence"] == 0.91


def test_http_json_span_normalizer_returns_timeout_failure(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        del request, timeout
        raise TimeoutError("timed out")

    monkeypatch.setattr("src.pipeline.extraction.text_normalization.urlopen", fake_urlopen)
    normalizer = HttpJsonSpanNormalizer(
        base_url="https://example.test/normalize",
        model="fake-model",
        api_key=None,
        timeout_seconds=5.0,
    )

    outcome = normalizer.normalize(
        field_spec=_current_event_spec(),
        schema_ref="v1/current_event_quant",
        selected_span=_selected_span(),
    )

    assert outcome.error_code == "NORMALIZATION_TIMEOUT"


def test_normalizer_from_settings_builds_http_json_normalizer() -> None:
    normalizer = normalizer_from_settings(
        SimpleNamespace(
            text_normalizer_mode="http_json",
            text_normalizer_base_url="https://example.test/normalize",
            text_normalizer_model="fake-model",
            text_normalizer_api_key="secret",
            text_normalizer_timeout_seconds=5.0,
        )
    )

    assert isinstance(normalizer, HttpJsonSpanNormalizer)


def test_normalizer_from_settings_returns_none_when_provider_mode_disabled() -> None:
    normalizer = normalizer_from_settings(
        SimpleNamespace(
            text_normalizer_mode="unavailable",
            text_normalizer_base_url="https://example.test/normalize",
            text_normalizer_model="fake-model",
            text_normalizer_api_key="secret",
            text_normalizer_timeout_seconds=5.0,
        )
    )

    assert normalizer is None


def test_regex_json_span_normalizer_allows_missing_nullable_string_pattern() -> None:
    spec = TextFieldSpec(
        field_name="mdna_outlook_quant",
        route="issuer",
        form_families=("S-1",),
        locators=("section_window",),
        anchor_terms=("md&a",),
        regex_patterns=(r"(?i)\b(up|down|flat)\b",),
        output_kind="json",
        output_schema="v1/mdna_outlook_quant",
        qa_rules={},
        normalizer_overrides={
            "mode": "regex_json",
            "field_patterns": {
                "direction": {
                    "up": r"(?i)\bup\b",
                    "down": r"(?i)\bdown\b",
                    "flat": r"(?i)\bflat\b",
                    "mixed": r"(?i)\bmixed\b",
                    "unclear": r"(?i)\bunclear\b",
                },
                "confidence_score": r"(?i)\bconfidence\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\b",
            },
        },
    )

    outcome = RegexJsonSpanNormalizer().normalize(
        field_spec=spec,
        schema_ref="v1/mdna_outlook_quant",
        selected_span=SelectedSpan(
            value_text="up",
            locator_kind="section_window",
            locator_path="sections[MD&A]",
            source_span="0:2",
            source_section="MD&A",
            source_item_no=None,
            source_locator_json='{"locator_kind":"section_window"}',
            source_heading_path_json='["MD&A"]',
            source_block_offsets_json='{"source_start":0,"source_end":2}',
            adequacy_signals_json='{"window_found":true}',
            retry_history_json="[]",
            selection_trace_json='{"selected_value":"up"}',
        ),
    )

    assert outcome.value == {"direction": "up", "confidence_score": None, "summary": None}


def test_regex_json_span_normalizer_prefers_false_boolean_match_on_overlap() -> None:
    spec = TextFieldSpec(
        field_name="rule144_sale_plan_quant",
        route="owner",
        form_families=("144",),
        locators=("section_window",),
        anchor_terms=("remarks",),
        regex_patterns=(r"(?i)\b(diversification|liquidity)\b",),
        output_kind="json",
        output_schema="v1/rule144_sale_plan_quant",
        qa_rules={},
        normalizer_overrides={
            "mode": "regex_json",
            "field_patterns": {
                "sale_reason": {
                    "diversification": r"(?i)\bdiversification\b",
                    "liquidity": r"(?i)\bliquidity\b",
                },
                "plan_ratio": r"(?i)\b([0-9]+(?:\.[0-9]+)?)%",
                "uses_10b5_1": {
                    "true": r"(?i)\b10b5-1\b",
                    "false": r"(?i)\bnot\s+10b5-1\b",
                },
            },
        },
    )

    outcome = RegexJsonSpanNormalizer().normalize(
        field_spec=spec,
        schema_ref="v1/rule144_sale_plan_quant",
        selected_span=SelectedSpan(
            value_text="diversification under not 10b5-1 plan",
            locator_kind="section_window",
            locator_path="sections[Remarks]",
            source_span="0:35",
            source_section="Remarks",
            source_item_no=None,
            source_locator_json='{"locator_kind":"section_window"}',
            source_heading_path_json='["Remarks"]',
            source_block_offsets_json='{"source_start":0,"source_end":35}',
            adequacy_signals_json='{"window_found":true}',
            retry_history_json="[]",
            selection_trace_json='{"selected_value":"diversification"}',
        ),
    )

    assert outcome.value == {
        "sale_reason": "diversification",
        "plan_ratio": None,
        "uses_10b5_1": False,
    }


def test_regex_json_span_normalizer_converts_percent_to_ratio_when_schema_requires() -> None:
    spec = TextFieldSpec(
        field_name="rule144_sale_plan_quant",
        route="owner",
        form_families=("144",),
        locators=("section_window",),
        anchor_terms=("remarks",),
        regex_patterns=(r"(?i)\b(diversification|liquidity)\b",),
        output_kind="json",
        output_schema="v1/rule144_sale_plan_quant",
        qa_rules={},
        normalizer_overrides={
            "mode": "regex_json",
            "field_patterns": {
                "sale_reason": {
                    "diversification": r"(?i)\bdiversification\b",
                    "liquidity": r"(?i)\bliquidity\b",
                },
                "plan_ratio": r"(?i)\b([0-9]+(?:\.[0-9]+)?)%",
            },
        },
    )

    outcome = RegexJsonSpanNormalizer().normalize(
        field_spec=spec,
        schema_ref="v1/rule144_sale_plan_quant",
        selected_span=SelectedSpan(
            value_text="diversification plan covering 25%",
            locator_kind="section_window",
            locator_path="sections[Remarks]",
            source_span="0:34",
            source_section="Remarks",
            source_item_no=None,
            source_locator_json='{"locator_kind":"section_window"}',
            source_heading_path_json='["Remarks"]',
            source_block_offsets_json='{"source_start":0,"source_end":34}',
            adequacy_signals_json='{"window_found":true}',
            retry_history_json="[]",
            selection_trace_json='{"selected_value":"diversification"}',
        ),
    )

    assert outcome.value == {
        "sale_reason": "diversification",
        "plan_ratio": 0.25,
        "uses_10b5_1": None,
    }


def test_regex_json_span_normalizer_prefers_false_for_non_derivative_overlap() -> None:
    spec = TextFieldSpec(
        field_name="insider_transaction_quant",
        route="owner",
        form_families=("4",),
        locators=("section_window",),
        anchor_terms=("remarks",),
        regex_patterns=(r"(?i)\b(sell|buy)\b",),
        output_kind="json",
        output_schema="v1/insider_transaction_quant",
        qa_rules={},
        normalizer_overrides={
            "mode": "regex_json",
            "field_patterns": {
                "transaction_type": {
                    "sale": r"(?i)\bsell\b",
                    "purchase": r"(?i)\bbuy\b",
                },
                "ownership_form": {
                    "direct": r"(?i)\bdirectly\b",
                    "indirect": r"(?i)\bindirectly\b",
                },
                "is_derivative": {
                    "true": r"(?i)\bderivative\b",
                    "false": r"(?i)\bnon-derivative|directly|indirectly\b",
                },
            },
        },
    )

    outcome = RegexJsonSpanNormalizer().normalize(
        field_spec=spec,
        schema_ref="v1/insider_transaction_quant",
        selected_span=SelectedSpan(
            value_text="sell non-derivative directly",
            locator_kind="section_window",
            locator_path="sections[Remarks]",
            source_span="0:29",
            source_section="Remarks",
            source_item_no=None,
            source_locator_json='{"locator_kind":"section_window"}',
            source_heading_path_json='["Remarks"]',
            source_block_offsets_json='{"source_start":0,"source_end":29}',
            adequacy_signals_json='{"window_found":true}',
            retry_history_json="[]",
            selection_trace_json='{"selected_value":"sell"}',
        ),
    )

    assert outcome.value == {
        "transaction_type": "sale",
        "ownership_form": "direct",
        "is_derivative": False,
    }
