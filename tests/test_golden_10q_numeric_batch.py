from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import pytest

from src.pipeline.golden_10q_numeric_batch import (
    _candidate_key,
    _candidate_score,
    _passes_runtime_filters,
    evaluate_10q_numeric_batch,
)


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


def test_evaluate_10q_numeric_batch_reports_phase_gate_success(tmp_path: Path) -> None:
    golden_path = tmp_path / "golden.yaml"
    snapshot_dir = tmp_path / "snapshots"
    snapshot_dir.mkdir()

    golden_path.write_text(
        """
cases:
  - case_id: case-001
    ticker: MSFT
    sic: 3571
    industry: Software
    form_type: 10-Q
    accession_no: 0000000000-24-000001
    filing_year: 2024
    filing_period: Q1
    fields:
      - field_name: total_revenue
        adjudication:
          selected_candidate_key: fact-1
phase_gates:
  - name: numeric_batch_smoke
    coverage:
      total_cases: 1
      total_candidates: 1
      required_fields: [total_revenue]
      required_form_types: [10-Q]
      required_tickers: [MSFT]
    metrics:
      min_gold_strict_accuracy: 1.0
      min_gold_coverage: 1.0
""".strip(),
        encoding="utf-8",
    )
    (snapshot_dir / "case-001.json").write_text(
        json.dumps(
            {
                "fields": [
                    {
                        "field_name": "total_revenue",
                        "candidate_pool": [
                            {
                                "id": "fact-1",
                                "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                                "statement_type": "IncomeStatement",
                                "dimensioned": False,
                                "period_start": "2024-01-01",
                                "period_end": "2024-03-31",
                                "value": 100.0,
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    result = evaluate_10q_numeric_batch(golden_path=golden_path, snapshot_dir=snapshot_dir)

    assert result.summary["phase_gates"] == {"total": 1, "passed": 1, "failed": 0, "skipped": 0}
    assert result.phase_gates == [{"name": "numeric_batch_smoke", "status": "passed", "violations": []}]


def test_evaluate_10q_numeric_batch_reports_phase_gate_failure(tmp_path: Path) -> None:
    golden_path = tmp_path / "golden.yaml"
    snapshot_dir = tmp_path / "snapshots"
    snapshot_dir.mkdir()

    golden_path.write_text(
        """
cases:
  - case_id: case-001
    ticker: MSFT
    sic: 3571
    industry: Software
    form_type: 10-Q
    accession_no: 0000000000-24-000001
    filing_year: 2024
    filing_period: Q1
    fields:
      - field_name: total_revenue
        adjudication:
          selected_candidate_key: fact-1
phase_gates:
  - name: impossible_batch_gate
    coverage:
      min_total_cases: 2
      required_tickers: [MSFT, AAPL]
    metrics:
      min_gold_strict_accuracy: 1.0
""".strip(),
        encoding="utf-8",
    )
    (snapshot_dir / "case-001.json").write_text(
        json.dumps(
            {
                "fields": [
                    {
                        "field_name": "total_revenue",
                        "candidate_pool": [
                            {
                                "id": "fact-2",
                                "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                                "statement_type": "IncomeStatement",
                                "dimensioned": False,
                                "period_start": "2024-01-01",
                                "period_end": "2024-03-31",
                                "value": 120.0,
                            },
                            {
                                "id": "fact-1",
                                "concept": "us-gaap:Revenues",
                                "statement_type": "IncomeStatement",
                                "dimensioned": False,
                                "period_start": "2024-01-01",
                                "period_end": "2024-03-31",
                                "value": 100.0,
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    result = evaluate_10q_numeric_batch(golden_path=golden_path, snapshot_dir=snapshot_dir)

    assert result.summary["phase_gates"] == {"total": 1, "passed": 0, "failed": 1, "skipped": 0}
    assert result.phase_gates[0]["name"] == "impossible_batch_gate"
    assert result.phase_gates[0]["status"] == "failed"
    assert {violation["key"] for violation in result.phase_gates[0]["violations"]} == {
        "min_total_cases",
        "required_tickers",
        "min_gold_strict_accuracy",
    }
    assert result.review_packets == [
        {
            "case_id": "case-001",
            "subject_key": "document",
            "field_name": "total_revenue",
            "expected": {"selected_candidate_key": "fact-1"},
            "actual": {
                "selected_candidate_key": "fact-2",
                "candidate_keys": ["fact-1", "fact-2"],
            },
        }
    ]
