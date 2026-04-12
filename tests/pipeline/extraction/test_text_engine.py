from __future__ import annotations

import json
from urllib.error import URLError

from src.pipeline.extraction.text_contracts import SpanPolicy, TextFieldSpec
import src.pipeline.extraction.text_engine as text_engine_module
from src.pipeline.extraction.text_engine import TextExtractionEngine
import src.pipeline.extraction.text_normalization as text_normalization_module
from src.pipeline.extraction.text_normalization import HttpJsonSpanNormalizer, NormalizationSuccess, normalizer_from_settings


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


def test_extract_field_returns_normalization_unavailable_for_json_output_without_normalizer(monkeypatch) -> None:
    monkeypatch.setenv("TEXT_NORMALIZER_MODE", "unavailable")
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


def test_http_json_span_normalizer_returns_structured_value(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "value": {
                        "stance": "passive",
                        "group_formed": False,
                        "horizon": "medium",
                    }
                },
                ensure_ascii=False,
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        del request, timeout
        return FakeResponse()

    monkeypatch.setattr(text_normalization_module, "urlopen", fake_urlopen)

    normalizer = HttpJsonSpanNormalizer(
        base_url="https://normalizer.local",
        model="test-model",
        api_key="secret",
        timeout_seconds=5.0,
    )
    outcome = normalizer.normalize(
        field_spec=TextFieldSpec(
            field_name="beneficial_ownership_intent_quant",
            route="owner",
            form_families=("13D",),
            locators=("section_window",),
            anchor_terms=("purpose of transaction",),
            regex_patterns=(r"(?i)\b(passive|control)\b",),
            output_kind="json",
            output_schema="v1/beneficial_ownership_intent_quant",
            qa_rules={},
        ),
        schema_ref="v1/beneficial_ownership_intent_quant",
        selected_span=text_normalization_module.SelectedSpan(
            value_text="Passive investor",
            locator_kind="section_window",
            locator_path="sections[Purpose of Transaction]",
            source_span="0:7",
            source_section="Purpose of Transaction",
            source_item_no=None,
            source_locator_json="{}",
            source_heading_path_json='["Purpose of Transaction"]',
            source_block_offsets_json="{}",
            adequacy_signals_json="{}",
            retry_history_json="[]",
            selection_trace_json="{}",
        ),
    )

    assert isinstance(outcome, text_normalization_module.NormalizationSuccess)
    assert outcome.value["stance"] == "passive"


def test_http_json_span_normalizer_returns_failure_on_provider_error(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        del request, timeout
        raise URLError("boom")

    monkeypatch.setattr(text_normalization_module, "urlopen", fake_urlopen)

    normalizer = HttpJsonSpanNormalizer(
        base_url="https://normalizer.local",
        model="test-model",
        api_key=None,
        timeout_seconds=5.0,
    )
    outcome = normalizer.normalize(
        field_spec=TextFieldSpec(
            field_name="beneficial_ownership_intent_quant",
            route="owner",
            form_families=("13D",),
            locators=("section_window",),
            anchor_terms=("purpose of transaction",),
            regex_patterns=(r"(?i)\b(passive|control)\b",),
            output_kind="json",
            output_schema="v1/beneficial_ownership_intent_quant",
            qa_rules={},
        ),
        schema_ref="v1/beneficial_ownership_intent_quant",
        selected_span=text_normalization_module.SelectedSpan(
            value_text="Passive investor",
            locator_kind="section_window",
            locator_path="sections[Purpose of Transaction]",
            source_span="0:7",
            source_section="Purpose of Transaction",
            source_item_no=None,
            source_locator_json="{}",
            source_heading_path_json='["Purpose of Transaction"]',
            source_block_offsets_json="{}",
            adequacy_signals_json="{}",
            retry_history_json="[]",
            selection_trace_json="{}",
        ),
    )

    assert outcome == text_normalization_module.NormalizationFailure(error_code="NORMALIZATION_FAILED")


def test_normalizer_from_settings_returns_http_json_when_configured() -> None:
    settings = text_normalization_module.Settings(
        PG_DSN="sqlite+pysqlite:///:memory:",
        TEXT_NORMALIZER_MODE="http_json",
        TEXT_NORMALIZER_BASE_URL="https://normalizer.local",
        TEXT_NORMALIZER_MODEL="test-model",
        TEXT_NORMALIZER_TIMEOUT_SECONDS="15",
    )

    normalizer = normalizer_from_settings(settings)

    assert isinstance(normalizer, HttpJsonSpanNormalizer)


def test_extract_field_uses_settings_backed_http_json_normalizer_when_no_field_mode_override(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "value": {
                        "stance": "passive",
                        "group_formed": False,
                        "horizon": "medium",
                    }
                },
                ensure_ascii=False,
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        del request, timeout
        return FakeResponse()

    monkeypatch.setattr(text_normalization_module, "urlopen", fake_urlopen)
    monkeypatch.setenv("TEXT_NORMALIZER_MODE", "http_json")
    monkeypatch.setenv("TEXT_NORMALIZER_BASE_URL", "https://normalizer.local")
    monkeypatch.setenv("TEXT_NORMALIZER_MODEL", "test-model")

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

    assert outcome["status"] == "ok"
    assert json.loads(outcome["value_json"])["stance"] == "passive"


def test_extract_field_merges_provider_adequacy_signals_into_persisted_payload(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "value": {
                        "stance": "passive",
                        "group_formed": False,
                        "horizon": "medium",
                    },
                    "adequacy_signals": {
                        "confidence": 0.88,
                        "sufficient_context": True,
                        "multiple_candidate_targets": False,
                    },
                },
                ensure_ascii=False,
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        del timeout
        payload = json.loads(request.data.decode("utf-8"))
        assert "The investor remains passive" in payload["text"]
        return FakeResponse()

    monkeypatch.setattr(text_normalization_module, "urlopen", fake_urlopen)
    monkeypatch.setenv("TEXT_NORMALIZER_MODE", "http_json")
    monkeypatch.setenv("TEXT_NORMALIZER_BASE_URL", "https://normalizer.local")
    monkeypatch.setenv("TEXT_NORMALIZER_MODEL", "test-model")

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

    assert outcome["status"] == "ok"
    adequacy_payload = json.loads(outcome["adequacy_signals_json"])
    assert adequacy_payload["confidence"] == 0.88
    assert adequacy_payload["sufficient_context"] is True
    assert adequacy_payload["schema_validation_passed"] is True


def test_extract_field_retries_with_expanded_span_when_adequacy_signals_need_more_context() -> None:
    calls: list[str] = []

    class FakeNormalizer:
        def normalize(self, *, field_spec, schema_ref, selected_span):
            del field_spec, schema_ref
            calls.append(selected_span.normalizer_input_text or "")
            if len(calls) == 1:
                return text_normalization_module.NormalizationSuccess(
                    value={
                        "stance": "passive",
                        "group_formed": False,
                        "horizon": "medium",
                    },
                    adequacy_signals_json=json.dumps({"sufficient_context": False}, ensure_ascii=False),
                )
            return text_normalization_module.NormalizationSuccess(
                value={
                    "stance": "passive",
                    "group_formed": False,
                    "horizon": "medium",
                },
                adequacy_signals_json=json.dumps({"sufficient_context": True}, ensure_ascii=False),
            )

    engine = TextExtractionEngine(normalizer=FakeNormalizer())
    filing = FakeSectionFiling(
        {
            "Purpose of Transaction": (
                "Passive investor.\n"
                "Additional context about not seeking board representation."
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
        span_policy=SpanPolicy(anchor_headers=("purpose of transaction",), min_tokens=1, max_tokens=40, expand_steps=(0, 1)),
    )

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome["status"] == "ok"
    assert calls == [
        "Passive investor.",
        "Purpose of Transaction\nPassive investor.\nAdditional context about not seeking board representation.",
    ]
    retry_history = json.loads(outcome["retry_history_json"])
    assert retry_history[0]["action"] == "initial"
    assert retry_history[0]["span_step"] == 0
    assert retry_history[1]["action"] == "expand"
    assert retry_history[1]["span_step"] == 1
    assert retry_history[1]["reason"] == "sufficient_context_false"
    assert retry_history[1]["input_length"] > retry_history[0]["input_length"]


def test_extract_field_returns_unavailable_when_http_json_mode_requested_without_provider(monkeypatch) -> None:
    monkeypatch.delenv("TEXT_NORMALIZER_BASE_URL", raising=False)
    monkeypatch.delenv("TEXT_NORMALIZER_MODEL", raising=False)
    monkeypatch.setenv("TEXT_NORMALIZER_MODE", "unavailable")

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
        normalizer_overrides={"mode": "http_json"},
        qa_rules={},
        span_policy=SpanPolicy(anchor_headers=("purpose of transaction",), min_tokens=5, max_tokens=40),
    )

    monkeypatch.setenv("TEXT_NORMALIZER_MODE", "unavailable")
    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome == {"status": "error", "error_code": "NORMALIZATION_UNAVAILABLE"}


def test_extract_field_surfaces_http_json_timeout_error(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        del request, timeout
        raise TimeoutError("timed out")

    monkeypatch.setattr(text_normalization_module, "urlopen", fake_urlopen)
    monkeypatch.setenv("TEXT_NORMALIZER_MODE", "http_json")
    monkeypatch.setenv("TEXT_NORMALIZER_BASE_URL", "https://normalizer.local")
    monkeypatch.setenv("TEXT_NORMALIZER_MODEL", "test-model")

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
        normalizer_overrides={"mode": "http_json"},
        qa_rules={},
        span_policy=SpanPolicy(anchor_headers=("purpose of transaction",), min_tokens=5, max_tokens=40),
    )

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome == {"status": "error", "error_code": "NORMALIZATION_TIMEOUT"}
