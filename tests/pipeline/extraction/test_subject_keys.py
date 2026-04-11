from __future__ import annotations

from src.pipeline.extraction.subject_keys import (
    load_subject_key_rules,
    subject_key_has_type,
    subject_type_for_key,
)


def test_subject_key_rules_load_configured_prefixes() -> None:
    rules = {(rule.route, rule.granularity): rule for rule in load_subject_key_rules()}

    assert rules[("issuer", "proposal_line")].subject_key_prefixes == ("proposal",)
    assert rules[("owner", "derivative_line")].subject_key_prefixes == ("dtxn", "dhold")
    assert rules[("owner", "sale_notice")].subject_key_prefixes == ("sale_notice", "sold_past_3m")
    assert rules[("holding", "position_line")].subject_key_prefixes == ("position",)


def test_subject_type_for_key_uses_configured_prefixes() -> None:
    assert subject_type_for_key(route="issuer", subject_key="proposal:1") == "proposal"
    assert subject_type_for_key(route="owner", subject_key="txn:1") == "transaction_row"
    assert subject_type_for_key(route="owner", subject_key="dtxn:2") == "transaction_row"
    assert subject_type_for_key(route="owner", subject_key="dhold:3") == "transaction_row"
    assert subject_type_for_key(route="owner", subject_key="nhold:4") == "transaction_row"
    assert subject_type_for_key(route="owner", subject_key="filer:1") == "reporting_person"
    assert subject_type_for_key(route="owner", subject_key="sold_past_3m:1") == "form144_notice"
    assert subject_type_for_key(route="holding", subject_key="position:2") == "holding_position"
    assert subject_type_for_key(route="issuer", subject_key="document") == "filing"


def test_subject_key_has_type_matches_same_config() -> None:
    assert subject_key_has_type(route="issuer", subject_key="proposal:1", subject_type="proposal")
    assert subject_key_has_type(route="owner", subject_key="sale_notice:1", subject_type="form144_notice")
    assert not subject_key_has_type(route="holding", subject_key="document", subject_type="holding_position")
