from dataclasses import dataclass
from typing import Literal

RouteName = Literal["issuer", "owner", "holding"]
ValueType = Literal["int", "float", "decimal"]
LocatorKind = Literal["obj", "xbrl_xml", "sections_search", "parse_text"]


@dataclass(frozen=True)
class NumericFieldSpec:
    field_name: str
    route: RouteName
    form_families: tuple[str, ...]
    value_type: ValueType
    locators: list[LocatorKind]
    qa_rules: dict[str, float | int | bool]


@dataclass(frozen=True)
class NumericCandidate:
    field_name: str
    value_raw: str | float | int
    value_normalized: float | int
    unit_raw: str | None
    unit_normalized: str | None
    locator_kind: LocatorKind
    locator_path: str
    confidence: float
    source_span_ref: str | None


@dataclass(frozen=True)
class ExtractionError:
    error_code: str
    message: str
