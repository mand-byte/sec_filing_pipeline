from __future__ import annotations

from dataclasses import dataclass
import json
import re
import socket
from typing import Any, Protocol
from urllib.request import Request, urlopen

from src.config import Settings
from src.pipeline.extraction.text_contracts import TextFieldSpec, TextLocatorKind
from src.pipeline.extraction.text_schemas import load_text_schema


@dataclass(frozen=True)
class SelectedSpan:
    value_text: str
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
    normalizer_input_text: str | None = None
    normalizer_window_text: str | None = None


@dataclass(frozen=True)
class NormalizationSuccess:
    value: Any
    retry_history_json: str = "[]"
    selection_trace_json: str | None = None
    adequacy_signals_json: str | None = None


@dataclass(frozen=True)
class NormalizationFailure:
    error_code: str


NormalizationOutcome = NormalizationSuccess | NormalizationFailure


class SpanNormalizer(Protocol):
    def normalize(
        self,
        *,
        field_spec: TextFieldSpec,
        schema_ref: str,
        selected_span: SelectedSpan,
    ) -> NormalizationOutcome:
        """Normalize one selected text span into the schema-specific output."""
        ...


class UnavailableSpanNormalizer:
    def normalize(
        self,
        *,
        field_spec: TextFieldSpec,
        schema_ref: str,
        selected_span: SelectedSpan,
    ) -> NormalizationOutcome:
        """Report that structured normalization is not currently available."""
        del field_spec, schema_ref, selected_span
        return NormalizationFailure(error_code="NORMALIZATION_UNAVAILABLE")


class RegexJsonSpanNormalizer:
    def _match_bool(
        self,
        *,
        bool_patterns: dict[Any, Any],
        text: str,
    ) -> bool | None:
        """Resolve a boolean field from configured true/false regex patterns."""
        true_pattern = bool_patterns.get("true", bool_patterns.get(True))
        false_pattern = bool_patterns.get("false", bool_patterns.get(False))

        false_matched = isinstance(false_pattern, str) and re.search(false_pattern, text)
        true_matched = isinstance(true_pattern, str) and re.search(true_pattern, text)
        if false_matched:
            return False
        if true_matched:
            return True
        return None

    def _match_numeric(
        self,
        *,
        pattern: Any,
        text: str,
        node: Any,
    ) -> float | None:
        """Resolve a numeric field from regex captures or constant pattern maps."""
        parsed: float | None = None
        matched_text = ""

        if isinstance(pattern, str):
            match = re.search(pattern, text)
            if match is not None:
                matched_text = match.group(0)
                group_value = match.group(1 if match.lastindex else 0).strip().replace(",", "")
                parsed = float(group_value)
        elif isinstance(pattern, dict):
            matched_constant = None
            for constant_value, constant_pattern in pattern.items():
                if isinstance(constant_pattern, str) and re.search(constant_pattern, text):
                    matched_constant = constant_value
                    matched_text = constant_pattern
                    break
            if matched_constant is not None:
                parsed = float(matched_constant)

        if parsed is None:
            return None

        if "%" in matched_text and node.maximum is not None and node.maximum <= 1 and parsed > 1:
            parsed /= 100.0
        return parsed

    def normalize(
        self,
        *,
        field_spec: TextFieldSpec,
        schema_ref: str,
        selected_span: SelectedSpan,
    ) -> NormalizationOutcome:
        """Normalize a span with regex-driven JSON field extraction rules."""
        schema = load_text_schema(schema_ref)
        if schema.root.type != "object":
            return NormalizationFailure(error_code="SCHEMA_VALIDATION_FAILED")

        overrides = dict(field_spec.normalizer_overrides or {})
        patterns_raw = overrides.get("field_patterns", {})
        if not isinstance(patterns_raw, dict):
            return NormalizationFailure(error_code="NORMALIZATION_FAILED")

        value: dict[str, Any] = {}
        text = selected_span.value_text
        for field_name, node in schema.root.properties.items():
            if node.type == "boolean":
                bool_patterns = patterns_raw.get(field_name, {})
                if not isinstance(bool_patterns, dict):
                    if node.nullable:
                        value[field_name] = None
                        continue
                    return NormalizationFailure(error_code="NORMALIZATION_FAILED")
                try:
                    matched_bool = self._match_bool(bool_patterns=bool_patterns, text=text)
                except re.error:
                    return NormalizationFailure(error_code="NORMALIZATION_FAILED")
                if matched_bool is not None:
                    value[field_name] = matched_bool
                    continue
                if node.nullable:
                    value[field_name] = None
                    continue
                return NormalizationFailure(error_code="SCHEMA_VALIDATION_FAILED")

            if node.enum:
                pattern_map = patterns_raw.get(field_name, {})
                if not isinstance(pattern_map, dict):
                    return NormalizationFailure(error_code="NORMALIZATION_FAILED")
                matched_value = None
                for enum_value in node.enum:
                    pattern = pattern_map.get(str(enum_value))
                    if isinstance(pattern, str) and re.search(pattern, text):
                        matched_value = enum_value
                        break
                if matched_value is None:
                    if node.nullable:
                        value[field_name] = None
                        continue
                    return NormalizationFailure(error_code="SCHEMA_VALIDATION_FAILED")
                value[field_name] = matched_value
                continue

            if node.type in {"number", "integer"}:
                pattern = patterns_raw.get(field_name)
                if not isinstance(pattern, (str, dict)):
                    if node.nullable:
                        value[field_name] = None
                        continue
                    return NormalizationFailure(error_code="NORMALIZATION_FAILED")

                try:
                    parsed = self._match_numeric(pattern=pattern, text=text, node=node)
                except (TypeError, ValueError, re.error):
                    return NormalizationFailure(error_code="SCHEMA_VALIDATION_FAILED")

                if parsed is None:
                    if node.nullable:
                        value[field_name] = None
                        continue
                    return NormalizationFailure(error_code="SCHEMA_VALIDATION_FAILED")

                value[field_name] = int(parsed) if node.type == "integer" else parsed
                continue

            if node.type == "string":
                pattern = patterns_raw.get(field_name)
                if not isinstance(pattern, str):
                    if node.nullable:
                        value[field_name] = None
                        continue
                    return NormalizationFailure(error_code="NORMALIZATION_FAILED")
                match = re.search(pattern, text)
                if match is None:
                    if node.nullable:
                        value[field_name] = None
                        continue
                    return NormalizationFailure(error_code="SCHEMA_VALIDATION_FAILED")
                value[field_name] = match.group(1 if match.lastindex else 0).strip()
                continue

            if node.type == "array":
                pattern_map = patterns_raw.get(field_name, {})
                if not isinstance(pattern_map, dict):
                    return NormalizationFailure(error_code="NORMALIZATION_FAILED")
                collected: list[str] = []
                for item_value, pattern in pattern_map.items():
                    if isinstance(pattern, str) and re.search(pattern, text):
                        collected.append(str(item_value))
                value[field_name] = collected
                continue

            return NormalizationFailure(error_code="NORMALIZATION_FAILED")

        return NormalizationSuccess(
            value=value,
            retry_history_json='[{"attempt":1,"status":"regex_json"}]',
            selection_trace_json=merge_selection_trace(
                base_json=selected_span.selection_trace_json,
                additions={"normalizer_mode": "regex_json", "output_schema": schema_ref},
            ),
        )


class HttpJsonSpanNormalizer:
    def __init__(self, *, base_url: str, model: str, api_key: str | None, timeout_seconds: float):
        """Configure the HTTP-backed JSON span normalizer."""
        self._base_url = base_url
        self._model = model
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def normalize(
        self,
        *,
        field_spec: TextFieldSpec,
        schema_ref: str,
        selected_span: SelectedSpan,
    ) -> NormalizationOutcome:
        """Call the external provider to normalize one span into structured JSON."""
        schema = load_text_schema(schema_ref)
        normalizer_input_text = (
            selected_span.normalizer_input_text
            or selected_span.normalizer_window_text
            or selected_span.value_text
        )
        payload = {
            "model": self._model,
            "field_name": field_spec.field_name,
            "schema_ref": schema_ref,
            "text": normalizer_input_text,
            "schema_id": schema.schema_id,
            "schema_version": schema.version,
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        request = Request(
            self._base_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(exc, (TimeoutError, socket.timeout)) or isinstance(reason, (TimeoutError, socket.timeout)):
                return NormalizationFailure(error_code="NORMALIZATION_TIMEOUT")
            return NormalizationFailure(error_code="NORMALIZATION_FAILED")

        if isinstance(response_payload, dict):
            value = response_payload.get("value_json", response_payload.get("value", response_payload.get("output")))
            retry_history_json = response_payload.get("retry_history_json")
            selection_trace_json = response_payload.get("selection_trace_json")
            adequacy_signals_json = response_payload.get("adequacy_signals_json")
            adequacy_signals = response_payload.get("adequacy_signals")
        else:
            value = response_payload
            retry_history_json = None
            selection_trace_json = None
            adequacy_signals_json = None
            adequacy_signals = None

        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return NormalizationFailure(error_code="SCHEMA_VALIDATION_FAILED")
        if not isinstance(value, dict):
            return NormalizationFailure(error_code="SCHEMA_VALIDATION_FAILED")

        normalized_adequacy_signals_json: str | None = None
        if isinstance(adequacy_signals_json, str):
            normalized_adequacy_signals_json = adequacy_signals_json
        elif isinstance(adequacy_signals, dict):
            normalized_adequacy_signals_json = json.dumps(adequacy_signals, ensure_ascii=False, sort_keys=True)

        return NormalizationSuccess(
            value=value,
            retry_history_json=retry_history_json if isinstance(retry_history_json, str) else '[{"attempt":1,"status":"http_json"}]',
            selection_trace_json=selection_trace_json if isinstance(selection_trace_json, str) else merge_selection_trace(
                base_json=selected_span.selection_trace_json,
                additions={
                    "normalizer_mode": "http_json",
                    "normalizer_model": self._model,
                    "output_schema": schema_ref,
                    "normalizer_input_length": len(normalizer_input_text),
                },
            ),
            adequacy_signals_json=normalized_adequacy_signals_json,
        )


def normalizer_from_settings(settings: Settings | None = None) -> SpanNormalizer | None:
    """Build the configured span normalizer from settings when supported."""
    effective_settings = settings or Settings()
    mode = str(effective_settings.text_normalizer_mode).strip().lower()
    if mode == "http_json":
        base_url = (effective_settings.text_normalizer_base_url or "").strip()
        model = (effective_settings.text_normalizer_model or "").strip()
        if not base_url or not model:
            return UnavailableSpanNormalizer()
        return HttpJsonSpanNormalizer(
            base_url=base_url,
            model=model,
            api_key=effective_settings.text_normalizer_api_key,
            timeout_seconds=float(effective_settings.text_normalizer_timeout_seconds),
        )
    return None


def merge_selection_trace(*, base_json: str, additions: dict[str, Any]) -> str:
    """Merge extra trace metadata into a persisted selection-trace JSON blob."""
    payload = json.loads(base_json)
    if not isinstance(payload, dict):
        payload = {}
    payload.update(additions)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
