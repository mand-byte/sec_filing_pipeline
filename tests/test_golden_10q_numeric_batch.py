from __future__ import annotations

from datetime import datetime, timezone

from src.pipeline.golden_10q_numeric_batch import _candidate_key, _candidate_score, _passes_runtime_filters


def test_candidate_score_respects_concept_priority() -> None:
    preferred = {
        "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "statement_type": "IncomeStatement",
        "dimensioned": False,
        "period_start": "2024-01-01",
        "period_end": "2024-03-31",
        "value": 100.0,
    }
    fallback = {
        "concept": "us-gaap:Revenues",
        "statement_type": "IncomeStatement",
        "dimensioned": False,
        "period_start": "2024-01-01",
        "period_end": "2024-03-31",
        "value": 100.0,
    }

    assert _candidate_score(field_name="total_revenue", candidate=preferred) > _candidate_score(
        field_name="total_revenue", candidate=fallback
    )


def test_passes_runtime_filters_supports_runtime_aliases() -> None:
    candidate = {
        "qname": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "statementType": "IncomeStatement",
        "dimensions": {},
        "periodStart": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "periodEnd": datetime(2024, 3, 31, tzinfo=timezone.utc),
        "numeric_value": 123.0,
    }

    assert _passes_runtime_filters(field_name="total_revenue", candidate=candidate) is True


def test_passes_runtime_filters_rejects_dimensioned_aliases() -> None:
    candidate = {
        "name": "us-gaap:OperatingIncomeLoss",
        "statementType": "IncomeStatement",
        "is_dimensioned": True,
        "periodStart": "2024-01-01",
        "periodEnd": "2024-03-31",
        "amount": 50.0,
    }

    assert _passes_runtime_filters(field_name="operating_income", candidate=candidate) is False


def test_candidate_key_supports_id_fallback() -> None:
    candidate = {
        "id": "fact-123",
        "name": "us-gaap:NetIncomeLoss",
        "periodStart": "2024-01-01",
        "periodEnd": "2024-03-31",
    }

    assert _candidate_key(candidate) == "fact-123"
