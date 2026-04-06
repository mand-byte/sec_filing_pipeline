from src.pipeline.extraction.contracts import NumericFieldSpec

_DEFAULT_LOCATORS = ["obj", "xbrl_xml", "sections_search", "parse_text"]


def _spec(field_name: str, route: str, forms: tuple[str, ...]) -> NumericFieldSpec:
    return NumericFieldSpec(
        field_name=field_name,
        route=route,
        form_families=forms,
        value_type="float",
        locators=list(_DEFAULT_LOCATORS),
        qa_rules={},
    )


def all_numeric_field_specs() -> list[NumericFieldSpec]:
    issuer = [
        _spec("total_revenue", "issuer", ("10-K", "10-Q", "20-F", "6-K", "S-1", "424B4")),
        _spec("operating_income", "issuer", ("10-K", "10-Q", "20-F", "6-K", "S-1", "424B4")),
        _spec("net_income", "issuer", ("10-K", "10-Q", "20-F", "6-K", "S-1", "424B4")),
        _spec("diluted_eps", "issuer", ("10-K", "10-Q", "20-F", "6-K", "S-1", "424B4")),
        _spec("cash_and_equivalents", "issuer", ("10-K", "10-Q", "20-F", "S-1", "424B4")),
        _spec("total_debt", "issuer", ("10-K", "10-Q", "20-F", "S-1", "424B4")),
        _spec("operating_cash_flow", "issuer", ("10-K", "10-Q", "20-F", "S-1", "424B4")),
        _spec("capex", "issuer", ("10-K", "10-Q", "20-F", "S-1", "424B4")),
        _spec("shares_outstanding", "issuer", ("10-K", "10-Q", "20-F", "S-1", "424B4", "DEF 14A")),
        _spec("filing_delay_days", "issuer", ("NT 10-Q", "NT 10-K")),
        _spec("gross_proceeds", "issuer", ("S-1", "424B4")),
        _spec("net_proceeds", "issuer", ("S-1", "424B4")),
        _spec("offering_price_per_share", "issuer", ("S-1", "424B4")),
        _spec("securities_offered_qty", "issuer", ("S-1", "424B4")),
        _spec("underwriter_discount_total", "issuer", ("S-1", "424B4")),
        _spec("deal_value", "issuer", ("8-K", "6-K", "SC TO-I", "SC 13E3")),
        _spec("offer_price_per_share", "issuer", ("8-K", "SC TO-I", "SC 13E3")),
        _spec("tender_shares_sought", "issuer", ("SC TO-I",)),
        _spec("financing_commitment_amount", "issuer", ("8-K", "SC TO-I", "SC 13E3", "S-1")),
        _spec("termination_fee", "issuer", ("8-K", "SC TO-I", "SC 13E3")),
        _spec("exec_total_comp", "issuer", ("DEF 14A", "S-1")),
        _spec("holder_beneficial_ownership_shares", "issuer", ("DEF 14A", "S-1", "424B4")),
        _spec("holder_beneficial_ownership_pct", "issuer", ("DEF 14A", "S-1", "424B4")),
        _spec("proposal_votes_for", "issuer", ("8-K",)),
        _spec("proposal_votes_against", "issuer", ("8-K",)),
        _spec("proposal_votes_abstain", "issuer", ("8-K",)),
        _spec("proposal_broker_non_votes", "issuer", ("8-K",)),
    ]

    owner = [
        _spec("non_derivative_shares_owned", "owner", ("3", "4", "5")),
        _spec("derivative_underlying_shares", "owner", ("3", "4", "5")),
        _spec("shares_acquired_or_disposed", "owner", ("4", "5")),
        _spec("transaction_price_per_share", "owner", ("4", "5")),
        _spec("shares_owned_following_txn", "owner", ("4", "5")),
        _spec("exercise_or_conversion_price", "owner", ("3", "4", "5")),
        _spec("beneficially_owned_shares", "owner", ("13D", "13G")),
        _spec("beneficial_ownership_pct", "owner", ("13D", "13G")),
        _spec("sole_voting_power", "owner", ("13D", "13G")),
        _spec("shared_voting_power", "owner", ("13D", "13G")),
        _spec("sole_dispositive_power", "owner", ("13D", "13G")),
        _spec("shared_dispositive_power", "owner", ("13D", "13G")),
        _spec("aggregate_purchase_price", "owner", ("13D",)),
        _spec("source_of_funds_amount", "owner", ("13D",)),
        _spec("proposed_sale_shares", "owner", ("144",)),
        _spec("proposed_sale_market_value", "owner", ("144",)),
        _spec("shares_sold_past_3m", "owner", ("144",)),
        _spec("market_value_sold_past_3m", "owner", ("144",)),
    ]

    holding = [
        _spec("position_value_usd", "holding", ("13F-HR", "13F-HR/A")),
        _spec("shares_or_principal_amount", "holding", ("13F-HR", "13F-HR/A")),
        _spec("sole_voting_auth_shares", "holding", ("13F-HR", "13F-HR/A")),
        _spec("shared_voting_auth_shares", "holding", ("13F-HR", "13F-HR/A")),
        _spec("none_voting_auth_shares", "holding", ("13F-HR", "13F-HR/A")),
        _spec("other_included_managers_count", "holding", ("13F-HR", "13F-HR/A")),
        _spec("info_table_entry_total", "holding", ("13F-HR", "13F-HR/A")),
        _spec("info_table_value_total_usd", "holding", ("13F-HR", "13F-HR/A")),
    ]

    return [*issuer, *owner, *holding]
