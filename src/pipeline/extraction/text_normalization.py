from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Protocol

from src.pipeline.extraction.text_contracts import TextFieldSpec, TextLocatorKind


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


@dataclass(frozen=True)
class NormalizationSuccess:
    value: Any
    retry_history_json: str = "[]"
    selection_trace_json: str | None = None


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
    ) -> NormalizationOutcome: ...


class UnavailableSpanNormalizer:
    def normalize(
        self,
        *,
        field_spec: TextFieldSpec,
        schema_ref: str,
        selected_span: SelectedSpan,
    ) -> NormalizationOutcome:
        del field_spec, schema_ref, selected_span
        return NormalizationFailure(error_code="NORMALIZATION_UNAVAILABLE")


def merge_selection_trace(*, base_json: str, additions: dict[str, Any]) -> str:
    payload = json.loads(base_json)
    if not isinstance(payload, dict):
        payload = {}
    payload.update(additions)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
