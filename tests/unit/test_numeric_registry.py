from src.pipeline.extraction.registry import all_numeric_field_specs


def test_numeric_registry_covers_all_phase2_fields() -> None:
    expected = {
        # issuer
        "total_revenue",
        "operating_income",
        "net_income",
        "diluted_eps",
        "cash_and_equivalents",
        "total_debt",
        "operating_cash_flow",
        "capex",
        "shares_outstanding",
        "filing_delay_days",
        "gross_proceeds",
        "net_proceeds",
        "offering_price_per_share",
        "securities_offered_qty",
        "underwriter_discount_total",
        "deal_value",
        "offer_price_per_share",
        "tender_shares_sought",
        "financing_commitment_amount",
        "termination_fee",
        "exec_total_comp",
        "holder_beneficial_ownership_shares",
        "holder_beneficial_ownership_pct",
        "proposal_votes_for",
        "proposal_votes_against",
        "proposal_votes_abstain",
        "proposal_broker_non_votes",
        # owner
        "non_derivative_shares_owned",
        "derivative_underlying_shares",
        "shares_acquired_or_disposed",
        "transaction_price_per_share",
        "shares_owned_following_txn",
        "exercise_or_conversion_price",
        "beneficially_owned_shares",
        "beneficial_ownership_pct",
        "sole_voting_power",
        "shared_voting_power",
        "sole_dispositive_power",
        "shared_dispositive_power",
        "aggregate_purchase_price",
        "source_of_funds_amount",
        "proposed_sale_shares",
        "proposed_sale_market_value",
        "shares_sold_past_3m",
        "market_value_sold_past_3m",
        # holding
        "position_value_usd",
        "shares_or_principal_amount",
        "sole_voting_auth_shares",
        "shared_voting_auth_shares",
        "none_voting_auth_shares",
        "other_included_managers_count",
        "info_table_entry_total",
        "info_table_value_total_usd",
    }
    actual = {spec.field_name for spec in all_numeric_field_specs()}
    assert actual == expected


def test_registry_is_numeric_only_and_has_fixed_locator_order() -> None:
    specs = all_numeric_field_specs()
    assert specs
    field_names = [spec.field_name for spec in specs]
    assert len(field_names) == len(set(field_names))
    for spec in specs:
        assert spec.value_type in {"int", "float", "decimal"}
        assert spec.locators == ("obj", "xbrl_xml", "sections_search", "parse_text")
        assert not spec.field_name.endswith("_quant")
