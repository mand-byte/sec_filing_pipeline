from __future__ import annotations

from collections import Counter

from src.pipeline.extraction.registry import all_numeric_field_specs, load_numeric_field_catalog
from src.pipeline.extraction.text_registry import all_text_field_specs, load_text_field_catalog


def test_numeric_catalog_freezes_53_fields_and_subject_type_distribution() -> None:
    catalog = load_numeric_field_catalog()

    assert len(catalog) == 53
    distribution = Counter((entry.route, entry.subject_type) for entry in catalog)
    assert distribution == Counter(
        {
            ("issuer", "filing"): 20,
            ("issuer", "proposal"): 4,
            ("issuer", "executive"): 1,
            ("issuer", "holder_row"): 2,
            ("owner", "transaction_row"): 6,
            ("owner", "reporting_person"): 8,
            ("owner", "form144_notice"): 4,
            ("holding", "holding_position"): 5,
            ("holding", "filing"): 3,
        }
    )


def test_runtime_numeric_specs_load_from_yaml_with_subject_mapping() -> None:
    specs = { (spec.route, spec.field_name): spec for spec in all_numeric_field_specs() }

    assert len(specs) == 53
    assert specs[("issuer", "total_revenue")].granularity == "document"
    assert specs[("issuer", "total_revenue")].subject_type == "filing"
    assert specs[("issuer", "exec_total_comp")].subject_type == "executive"
    assert specs[("issuer", "holder_beneficial_ownership_shares")].subject_type == "holder_row"
    assert specs[("owner", "derivative_underlying_shares")].subject_type == "transaction_row"
    assert specs[("holding", "position_value_usd")].subject_type == "holding_position"


def test_text_catalog_tracks_documented_and_implemented_fields() -> None:
    catalog = load_text_field_catalog()
    specs = {(spec.route, spec.field_name): spec for spec in all_text_field_specs()}

    assert len(catalog) == 15
    implemented = {
        (entry.route, entry.field_name)
        for entry in catalog
        if entry.implemented
    }
    assert implemented == set(specs) == {
        ("issuer", "mdna_outlook_quant"),
        ("issuer", "risk_factor_quant"),
        ("issuer", "current_event_quant"),
        ("issuer", "delay_reason_quant"),
        ("issuer", "use_of_proceeds_quant"),
        ("issuer", "proxy_proposal_quant"),
        ("issuer", "comp_policy_quant"),
        ("issuer", "tender_going_private_quant"),
        ("owner", "beneficial_ownership_intent_quant"),
        ("owner", "insider_transaction_quant"),
        ("owner", "insider_role_ownership_structure_quant"),
        ("owner", "rule144_sale_plan_quant"),
        ("owner", "source_of_funds_quant"),
        ("holding", "manager_structure_quant"),
        ("holding", "amendment_scope_quant"),
    }
    assert specs[("issuer", "mdna_outlook_quant")].span_policy is not None
    assert specs[("issuer", "risk_factor_quant")].span_policy is not None
    assert specs[("issuer", "current_event_quant")].span_policy is not None
    assert specs[("issuer", "delay_reason_quant")].span_policy is not None
    assert specs[("issuer", "use_of_proceeds_quant")].span_policy is not None
    assert specs[("issuer", "proxy_proposal_quant")].span_policy is not None
    assert specs[("issuer", "comp_policy_quant")].span_policy is not None
    assert specs[("issuer", "tender_going_private_quant")].span_policy is not None
    assert specs[("owner", "beneficial_ownership_intent_quant")].span_policy is not None
    assert specs[("owner", "insider_transaction_quant")].span_policy is not None
    assert specs[("owner", "insider_role_ownership_structure_quant")].span_policy is not None
    assert specs[("owner", "rule144_sale_plan_quant")].span_policy is not None
    assert specs[("owner", "source_of_funds_quant")].span_policy is not None
    assert specs[("holding", "manager_structure_quant")].span_policy is not None
    assert specs[("holding", "amendment_scope_quant")].span_policy is not None
