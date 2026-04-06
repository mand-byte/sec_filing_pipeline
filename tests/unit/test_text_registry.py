import pytest

from src.pipeline.extraction.text_contracts import TextFieldSpec
from src.pipeline.extraction.text_registry import all_text_field_specs


def test_text_registry_includes_exact_starter_fields() -> None:
    expected = {
        ("issuer", "current_event_quant"),
        ("owner", "beneficial_ownership_intent_quant"),
        ("holding", "amendment_scope_quant"),
    }
    actual = {(spec.route, spec.field_name) for spec in all_text_field_specs()}
    assert actual == expected


def test_text_registry_has_unique_route_field_pairs() -> None:
    route_field_pairs = [(spec.route, spec.field_name) for spec in all_text_field_specs()]
    assert len(route_field_pairs) == len(set(route_field_pairs))


def test_text_registry_starter_specs_use_text_output_kind() -> None:
    for spec in all_text_field_specs():
        assert spec.output_kind == "text"


def test_text_registry_enforces_locator_limit() -> None:
    for spec in all_text_field_specs():
        assert 1 <= len(spec.locators) <= 3


def test_text_registry_routes_are_upper_form_families() -> None:
    for spec in all_text_field_specs():
        for form in spec.form_families:
            assert form == form.upper()


@pytest.mark.parametrize(
    "field_name,form_families,locators,anchor_terms,regex_patterns",
    [
        ("   ", ("8-K",), ("item_window",), ("item",), (r"(?i)item",)),
        ("valid", (), ("item_window",), ("item",), (r"(?i)item",)),
        ("valid", ("8-K",), (), ("item",), (r"(?i)item",)),
        ("valid", ("8-K",), ("item_window",), (), (r"(?i)item",)),
        ("valid", ("8-K",), ("item_window",), ("item",), ()),
        ("valid", ("8-K",), ("item_window",), ("item",), ("   ",)),
    ],
)
def test_text_field_spec_rejects_invalid_invariants(
    field_name: str,
    form_families: tuple[str, ...],
    locators: tuple[str, ...],
    anchor_terms: tuple[str, ...],
    regex_patterns: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError):
        TextFieldSpec(
            field_name=field_name,
            route="issuer",
            form_families=form_families,
            locators=locators,
            anchor_terms=anchor_terms,
            regex_patterns=regex_patterns,
            output_kind="json",
            qa_rules={"flag": True},
        )
