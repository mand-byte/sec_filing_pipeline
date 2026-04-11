from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from src.pipeline.extraction._config import load_extraction_config


@dataclass(frozen=True)
class SubjectKeyRule:
    route: str
    granularity: str
    subject_type: str
    subject_key_prefixes: tuple[str, ...]

    def matches(self, subject_key: str) -> bool:
        normalized_subject_key = subject_key.strip()
        if not normalized_subject_key:
            return False

        for prefix in self.subject_key_prefixes:
            normalized_prefix = prefix.strip()
            if not normalized_prefix:
                continue
            if normalized_prefix == "document":
                if normalized_subject_key == "document":
                    return True
                continue
            if normalized_subject_key == normalized_prefix or normalized_subject_key.startswith(f"{normalized_prefix}:"):
                return True
        return False


@lru_cache(maxsize=None)
def load_subject_type_lookup() -> dict[tuple[str, str], str]:
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
def load_subject_key_rules() -> tuple[SubjectKeyRule, ...]:
    payload = load_extraction_config("subject_mappings.yaml")
    mappings = payload.get("mappings", {})
    rules: list[SubjectKeyRule] = []
    if not isinstance(mappings, dict):
        return ()

    for route, granularity_map in mappings.items():
        if not isinstance(granularity_map, dict):
            continue
        for granularity, subject_mapping in granularity_map.items():
            if not isinstance(subject_mapping, dict):
                continue
            subject_type = subject_mapping.get("subject_type")
            if not isinstance(subject_type, str) or not subject_type.strip():
                continue
            prefixes_raw = subject_mapping.get("subject_key_prefixes", ())
            prefixes: tuple[str, ...]
            if isinstance(prefixes_raw, str):
                prefixes = (prefixes_raw,)
            elif isinstance(prefixes_raw, list):
                prefixes = tuple(str(prefix) for prefix in prefixes_raw)
            else:
                prefixes = ()
            if not prefixes and str(granularity).strip() == "document":
                prefixes = ("document",)
            rules.append(
                SubjectKeyRule(
                    route=str(route).strip(),
                    granularity=str(granularity).strip(),
                    subject_type=subject_type.strip(),
                    subject_key_prefixes=prefixes,
                )
            )
    return tuple(rules)


def _fallback_subject_type(*, route: str, subject_key: str) -> str:
    normalized_subject_key = subject_key.strip()
    if normalized_subject_key == "document":
        return "filing"
    if route == "owner":
        return "transaction_row"
    return "filing"


def subject_type_for_key(*, route: str, subject_key: str) -> str:
    normalized_route = route.strip()
    normalized_subject_key = subject_key.strip()
    if not normalized_subject_key:
        return _fallback_subject_type(route=normalized_route, subject_key=normalized_subject_key)

    for rule in load_subject_key_rules():
        if rule.route != normalized_route:
            continue
        if rule.matches(normalized_subject_key):
            return rule.subject_type

    return _fallback_subject_type(route=normalized_route, subject_key=normalized_subject_key)


def subject_key_has_type(*, route: str, subject_key: str, subject_type: str) -> bool:
    return subject_type_for_key(route=route, subject_key=subject_key) == subject_type.strip()


def subject_key_matches_granularity(*, route: str, granularity: str, subject_key: str) -> bool:
    normalized_route = route.strip()
    normalized_granularity = granularity.strip()
    normalized_subject_key = subject_key.strip()
    if not normalized_subject_key:
        return False

    for rule in load_subject_key_rules():
        if rule.route != normalized_route or rule.granularity != normalized_granularity:
            continue
        return rule.matches(normalized_subject_key)

    if normalized_granularity == "document":
        return normalized_subject_key == "document"
    return False
