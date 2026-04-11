from __future__ import annotations

from functools import lru_cache

from src.pipeline.extraction._config import load_extraction_config
from src.pipeline.extraction.text_contracts import SpanPolicy, TextFieldCatalogEntry, TextFieldSpec


@lru_cache(maxsize=None)
def _text_catalog_tuple() -> tuple[TextFieldCatalogEntry, ...]:
    payload = load_extraction_config("catalog_text_fields.yaml")
    fields = payload.get("fields", [])
    entries: list[TextFieldCatalogEntry] = []
    if not isinstance(fields, list):
        return ()

    for raw_entry in fields:
        if not isinstance(raw_entry, dict):
            continue
        entries.append(
            TextFieldCatalogEntry(
                field_name=str(raw_entry["field_name"]),
                route=str(raw_entry["route"]),
                form_families=tuple(str(form) for form in raw_entry.get("form_families", ())),
                implemented=bool(raw_entry.get("implemented", False)),
            )
        )
    return tuple(entries)


def load_text_field_catalog() -> list[TextFieldCatalogEntry]:
    return list(_text_catalog_tuple())


@lru_cache(maxsize=None)
def _text_field_specs_tuple() -> tuple[TextFieldSpec, ...]:
    payload = load_extraction_config("runtime_text_fields.yaml")
    fields = payload.get("fields", [])
    specs: list[TextFieldSpec] = []
    if not isinstance(fields, list):
        return ()

    for raw_entry in fields:
        if not isinstance(raw_entry, dict):
            continue
        implemented = bool(raw_entry.get("implemented", True))
        if not implemented:
            continue
        span_policy_raw = raw_entry.get("span_policy")
        span_policy = None
        if isinstance(span_policy_raw, dict):
            span_policy = SpanPolicy(
                anchor_headers=tuple(str(value) for value in span_policy_raw.get("anchor_headers", ())),
                min_tokens=int(span_policy_raw.get("min_tokens", 0)),
                max_tokens=int(span_policy_raw.get("max_tokens", 0)),
                preferred_tokens=tuple(span_policy_raw["preferred_tokens"]) if span_policy_raw.get("preferred_tokens") else None,
                expand_steps=tuple(span_policy_raw.get("expand_steps", ())),
                must_include=tuple(str(value) for value in span_policy_raw.get("must_include", ())),
                avoid=tuple(str(value) for value in span_policy_raw.get("avoid", ())),
            )
        specs.append(
            TextFieldSpec(
                field_name=str(raw_entry["field_name"]),
                route=str(raw_entry["route"]),
                form_families=tuple(str(form) for form in raw_entry.get("form_families", ())),
                locators=tuple(str(locator) for locator in raw_entry.get("locators", ())),
                anchor_terms=tuple(str(term) for term in raw_entry.get("anchor_terms", ())),
                regex_patterns=tuple(str(pattern) for pattern in raw_entry.get("regex_patterns", ())),
                output_kind=str(raw_entry.get("output_kind", "text")),
                qa_rules=dict(raw_entry.get("qa_rules", {})),
                output_schema=raw_entry.get("output_schema"),
                span_policy=span_policy,
                implemented=implemented,
            )
        )
    return tuple(specs)


def all_text_field_specs() -> list[TextFieldSpec]:
    return list(_text_field_specs_tuple())
