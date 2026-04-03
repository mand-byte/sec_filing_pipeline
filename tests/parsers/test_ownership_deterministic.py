import pytest

from src.parsers.ownership_deterministic import parse_ownership_deterministic


def test_parse_ownership_deterministic_extracts_core_facts() -> None:
    text = """
Issuer CIK: 0000320193
Reporting Owner CIK: 0001214156
Transaction Shares: 1234
"""

    parsed = parse_ownership_deterministic(
        accession_no="0000320193-24-000012",
        document_filename="primary_doc.txt",
        source_text=text,
    )

    fact_names = {fact.fact_name for fact in parsed.facts}
    assert {"issuer_cik", "reporting_owner_cik", "transaction_shares"} <= fact_names

    shares_fact = next(
        fact for fact in parsed.facts if fact.fact_name == "transaction_shares"
    )
    assert shares_fact.parser_method == "deterministic_rule"
    assert shares_fact.validation_results["is_numeric"] is True


def test_parse_ownership_deterministic_marks_non_numeric_shares() -> None:
    text = """
Issuer CIK: 0000320193
Reporting Owner CIK: 0001214156
Transaction Shares: 12x
"""

    parsed = parse_ownership_deterministic(
        accession_no="0000320193-24-000012",
        document_filename="primary_doc.txt",
        source_text=text,
    )

    shares_fact = next(
        fact for fact in parsed.facts if fact.fact_name == "transaction_shares"
    )
    assert shares_fact.validation_results["is_numeric"] is False


def test_parse_ownership_deterministic_raises_when_not_applicable() -> None:
    with pytest.raises(ValueError, match="not applicable"):
        parse_ownership_deterministic(
            accession_no="0000320193-24-000012",
            document_filename="primary_doc.txt",
            source_text="This is not an ownership filing payload.",
        )
