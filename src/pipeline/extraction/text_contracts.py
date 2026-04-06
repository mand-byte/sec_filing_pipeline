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
    qa_rules: Mapping[str, str | float | int | bool | None]

    def __post_init__(self) -> None:
        object.__setattr__(self, "form_families", tuple(form.upper() for form in self.form_families))
        object.__setattr__(self, "locators", tuple(self.locators))
        object.__setattr__(self, "anchor_terms", tuple(self.anchor_terms))
        object.__setattr__(self, "regex_patterns", tuple(self.regex_patterns))
        object.__setattr__(self, "qa_rules", MappingProxyType(dict(self.qa_rules)))


@dataclass(frozen=True)
class TextCandidate:
    field_name: str
    value_text: str | None
    value_json: Mapping[str, object] | None
    locator_kind: TextLocatorKind
    locator_path: str
    source_span: str | None


@dataclass(frozen=True)
class TextExtractionError:
    error_code: str
    message: str
