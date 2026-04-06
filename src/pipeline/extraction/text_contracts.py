from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping

RouteName = Literal["issuer", "owner", "holding"]
TextLocatorKind = Literal["item_window", "section_window", "parse_text_window"]
TextOutputKind = Literal["text", "json"]


@dataclass(frozen=True)
class TextFieldSpec:
    field_name: str
    route: RouteName
    form_families: tuple[str, ...]
    locators: tuple[TextLocatorKind, ...]
    anchor_terms: tuple[str, ...]
    regex_patterns: tuple[str, ...]
    output_kind: TextOutputKind
    qa_rules: Mapping[str, int | float | bool]

    def __post_init__(self) -> None:
        field_name = self.field_name.strip()
        if not field_name:
            raise ValueError("field_name must be non-empty after stripping")

        form_families = tuple(form.upper() for form in self.form_families)
        if not form_families:
            raise ValueError("form_families must be non-empty")

        locators = tuple(self.locators)
        if not 1 <= len(locators) <= 3:
            raise ValueError("locators must contain between 1 and 3 entries")

        anchor_terms = tuple(self.anchor_terms)
        if not anchor_terms:
            raise ValueError("anchor_terms must be non-empty")

        regex_patterns = tuple(self.regex_patterns)
        if not regex_patterns:
            raise ValueError("regex_patterns must be non-empty")
        if any(not pattern.strip() for pattern in regex_patterns):
            raise ValueError("regex_patterns must contain non-empty patterns")

        object.__setattr__(self, "field_name", field_name)
        object.__setattr__(self, "form_families", form_families)
        object.__setattr__(self, "locators", locators)
        object.__setattr__(self, "anchor_terms", anchor_terms)
        object.__setattr__(self, "regex_patterns", regex_patterns)
        object.__setattr__(self, "qa_rules", MappingProxyType(dict(self.qa_rules)))


@dataclass(frozen=True)
class TextCandidate:
    field_name: str
    value_text: str | None
    value_json: str | None
    locator_kind: TextLocatorKind
    locator_path: str
    source_span: str


@dataclass(frozen=True)
class TextExtractionError:
    error_code: str
    message: str
