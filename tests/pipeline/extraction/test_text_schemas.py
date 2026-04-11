from __future__ import annotations

from src.pipeline.extraction.text_schemas import load_text_schema, validate_text_schema_value


def test_load_text_schema_reads_versioned_inventory_file() -> None:
    schema = load_text_schema("v1/beneficial_ownership_intent_quant")

    assert schema.version == "v1"
    assert schema.schema_id == "beneficial_ownership_intent_quant"
    assert schema.root.type == "object"
    assert "stance" in schema.root.required


def test_validate_text_schema_value_accepts_matching_payload() -> None:
    result = validate_text_schema_value(
        schema_ref="v1/beneficial_ownership_intent_quant",
        value={
            "stance": "passive",
            "group_formed": False,
            "horizon": "medium",
        },
    )

    assert result.ok is True
    assert result.errors == ()


def test_validate_text_schema_value_rejects_missing_and_extra_keys() -> None:
    result = validate_text_schema_value(
        schema_ref="v1/beneficial_ownership_intent_quant",
        value={
            "group_formed": False,
            "unexpected": True,
        },
    )

    assert result.ok is False
    assert any("missing required keys" in error for error in result.errors)
    assert any("unexpected keys" in error for error in result.errors)
