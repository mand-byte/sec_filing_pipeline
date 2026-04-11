from __future__ import annotations

from functools import lru_cache

from src.pipeline.extraction._config import load_extraction_config
from src.pipeline.extraction.contracts import NumericFieldCatalogEntry, NumericFieldSpec


@lru_cache(maxsize=None)
def _load_subject_type_lookup() -> dict[tuple[str, str], str]:
    payload = load_extraction_config("subject_mappings.yaml")
    mappings = payload.get("mappings", {})
    lookup: dict[tuple[str, str], str] = {}
    if not isinstance(mappings, dict):
        return lookup

    for route, granularity_map in mappings.items():
        if not isinstance(granularity_map, dict):
            continue
        for granularity, subject_mapping in granularity_map.items():
            if not isinstance(subject_mapping, dict):
                continue
            subject_type = subject_mapping.get("subject_type")
            if isinstance(subject_type, str) and subject_type.strip():
                lookup[(str(route).strip(), str(granularity).strip())] = subject_type.strip()
    return lookup


@lru_cache(maxsize=None)
def _numeric_catalog_tuple() -> tuple[NumericFieldCatalogEntry, ...]:
    payload = load_extraction_config("catalog_numeric_fields.yaml")
    fields = payload.get("fields", [])
    entries: list[NumericFieldCatalogEntry] = []
    if not isinstance(fields, list):
        return ()

    for raw_entry in fields:
        if not isinstance(raw_entry, dict):
            continue
        entries.append(
            NumericFieldCatalogEntry(
                field_name=str(raw_entry["field_name"]),
                route=str(raw_entry["route"]),
                granularity=str(raw_entry["granularity"]),
                subject_type=str(raw_entry["subject_type"]),
                form_families=tuple(str(form) for form in raw_entry.get("form_families", ())),
            )
        )
    return tuple(entries)


def load_numeric_field_catalog() -> list[NumericFieldCatalogEntry]:
    return list(_numeric_catalog_tuple())


@lru_cache(maxsize=None)
def _numeric_catalog_lookup() -> dict[tuple[str, str], NumericFieldCatalogEntry]:
    return {(entry.route, entry.field_name): entry for entry in _numeric_catalog_tuple()}


@lru_cache(maxsize=None)
def _numeric_field_specs_tuple() -> tuple[NumericFieldSpec, ...]:
    payload = load_extraction_config("runtime_numeric_fields.yaml")
    fields = payload.get("fields", [])
    if not isinstance(fields, list):
        return ()

    catalog_lookup = _numeric_catalog_lookup()
    subject_type_lookup = _load_subject_type_lookup()
    specs: list[NumericFieldSpec] = []
    for raw_entry in fields:
        if not isinstance(raw_entry, dict):
            continue
        field_name = str(raw_entry["field_name"])
        route = str(raw_entry["route"])
        catalog_entry = catalog_lookup.get((route, field_name))
        granularity = catalog_entry.granularity if catalog_entry is not None else "document"
        subject_type = catalog_entry.subject_type if catalog_entry is not None else subject_type_lookup.get((route, granularity), "filing")
        specs.append(
            NumericFieldSpec(
                field_name=field_name,
                route=route,
                form_families=tuple(str(form) for form in raw_entry.get("form_families", ())),
                granularity=granularity,
                subject_type=subject_type,
                value_type=str(raw_entry.get("value_type", "float")),
                locators=tuple(str(locator) for locator in raw_entry.get("locators", ())),
                qa_rules=dict(raw_entry.get("qa_rules", {})),
                xbrl_concepts=tuple(str(concept) for concept in raw_entry.get("xbrl_concepts", ())),
                xbrl_statement_type=raw_entry.get("xbrl_statement_type"),
                xbrl_prefer_dimensionless=bool(raw_entry.get("xbrl_prefer_dimensionless", False)),
                xbrl_duration_days_range=tuple(raw_entry["xbrl_duration_days_range"]) if raw_entry.get("xbrl_duration_days_range") else None,
                xbrl_preferred_duration_days=tuple(raw_entry.get("xbrl_preferred_duration_days", ())),
                xbrl_period_type=raw_entry.get("xbrl_period_type"),
                xbrl_enabled_form_families=tuple(str(form) for form in raw_entry.get("xbrl_enabled_form_families", ())),
            )
        )
    return tuple(specs)


def all_numeric_field_specs() -> list[NumericFieldSpec]:
    return list(_numeric_field_specs_tuple())
