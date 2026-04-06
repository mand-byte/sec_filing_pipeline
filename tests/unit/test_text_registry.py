from src.pipeline.extraction.text_registry import all_text_field_specs


def test_text_registry_includes_starter_fields() -> None:
    expected = {
        ("issuer", "current_event_quant"),
        ("owner", "beneficial_ownership_intent_quant"),
        ("holding", "amendment_scope_quant"),
    }
    actual = {(spec.route, spec.field_name) for spec in all_text_field_specs()}
    assert expected.issubset(actual)


def test_text_registry_enforces_locator_limit() -> None:
    for spec in all_text_field_specs():
        assert 1 <= len(spec.locators) <= 3


def test_text_registry_routes_are_upper_form_families() -> None:
    for spec in all_text_field_specs():
        for form in spec.form_families:
            assert form == form.upper()
