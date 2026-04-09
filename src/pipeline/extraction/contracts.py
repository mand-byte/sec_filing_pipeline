from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping

RouteName = Literal["issuer", "owner", "holding"]
ValueType = Literal["int", "float"]
LocatorKind = Literal["obj", "xbrl_xml", "sections_search", "parse_text"]


@dataclass(frozen=True)
class NumericFieldSpec:
    field_name: str
    route: RouteName
    form_families: tuple[str, ...]
    value_type: ValueType
    locators: tuple[LocatorKind, ...]
    qa_rules: Mapping[str, float | int | bool]
    xbrl_concepts: tuple[str, ...] = ()
    xbrl_statement_type: str | None = None
    xbrl_prefer_dimensionless: bool = False
    xbrl_duration_days_range: tuple[int, int] | None = None
    xbrl_preferred_duration_days: tuple[int, ...] = ()
    xbrl_period_type: Literal["duration", "instant"] | None = None
    xbrl_enabled_form_families: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "locators", tuple(self.locators))
        object.__setattr__(
            self,
            "xbrl_concepts",
            tuple(concept.strip() for concept in self.xbrl_concepts if concept.strip()),
        )
        object.__setattr__(
            self,
            "xbrl_enabled_form_families",
            tuple(form.strip().upper() for form in self.xbrl_enabled_form_families if form.strip()),
        )
        object.__setattr__(
            self,
            "xbrl_preferred_duration_days",
            tuple(int(day) for day in self.xbrl_preferred_duration_days),
        )
        object.__setattr__(self, "qa_rules", MappingProxyType(dict(self.qa_rules)))

        if self.xbrl_statement_type is not None:
            statement_type = self.xbrl_statement_type.strip()
            object.__setattr__(self, "xbrl_statement_type", statement_type or None)

        if self.xbrl_period_type is not None:
            object.__setattr__(self, "xbrl_period_type", self.xbrl_period_type)

        if self.xbrl_duration_days_range is not None:
            min_days, max_days = self.xbrl_duration_days_range
            normalized_range = (int(min_days), int(max_days))
            if normalized_range[0] > normalized_range[1]:
                raise ValueError("xbrl_duration_days_range must be ordered")
            object.__setattr__(self, "xbrl_duration_days_range", normalized_range)


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
