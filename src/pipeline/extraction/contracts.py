from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping

RouteName = Literal["issuer", "owner", "holding"]
ValueType = Literal["int", "float", "decimal"]
LocatorKind = Literal["obj", "xbrl_xml", "sections_search", "parse_text"]


@dataclass(frozen=True)
class NumericFieldSpec:
    field_name: str
    route: RouteName
    form_families: tuple[str, ...]
    value_type: ValueType
    locators: tuple[LocatorKind, ...]
    qa_rules: Mapping[str, float | int | bool]

    def __post_init__(self) -> None:
        object.__setattr__(self, "locators", tuple(self.locators))
        object.__setattr__(self, "qa_rules", MappingProxyType(dict(self.qa_rules)))


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
