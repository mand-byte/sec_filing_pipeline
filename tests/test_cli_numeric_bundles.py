from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import src.cli as cli_module
from src.pipeline.edgar_provider import FilingEnvelope


class FakeXBRL:
    def __init__(self, records: list[dict[str, object]]):
        self.facts_view = records


class FakeFiling:
    def __init__(self, *, form: str, records: list[dict[str, object]]):
        self.form = form
        self._xbrl = FakeXBRL(records)

    def xbrl(self) -> FakeXBRL:
        return self._xbrl


class FakeObjBackedFiling(FakeFiling):
    def obj(self) -> float:
        return 777.0


class FakeRepo:
    def __init__(self) -> None:
        self.logs: list[dict[str, object]] = []

    def write_log(self, **kwargs: object) -> None:
        self.logs.append(dict(kwargs))


def test_build_bundles_from_provider_emits_numeric_xbrl_evidence(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 1, tzinfo=timezone.utc)
    filing = FakeObjBackedFiling(
        form="10-Q",
        records=[
            {
                "fact_key": "revenue-q1",
                "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-03-31",
                "value": 1000.0,
            },
            {
                "fact_key": "opinc-q1",
                "concept": "us-gaap:OperatingIncomeLoss",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-03-31",
                "value": 200.0,
            },
            {
                "fact_key": "netinc-q1",
                "concept": "us-gaap:NetIncomeLoss",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-03-31",
                "value": 150.0,
            },
            {
                "fact_key": "eps-q1",
                "concept": "us-gaap:EarningsPerShareDiluted",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-03-31",
                "value": 1.25,
            },
            {
                "fact_key": "ocf-q2",
                "concept": "us-gaap:NetCashProvidedByUsedInOperatingActivities",
                "statement_type": "CashFlowStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-06-30",
                "value": 320.0,
            },
            {
                "fact_key": "cash-q1",
                "concept": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-03-31",
                "value": 450.0,
            },
            {
                "fact_key": "capex-q2",
                "concept": "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
                "statement_type": "CashFlowStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-06-30",
                "value": 88.0,
            },
            {
                "fact_key": "shares-q2",
                "concept": "dei:EntityCommonStockSharesOutstanding",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-06-30",
                "value": 5100000.0,
            },
        ],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000001",
        cik="0000789019",
        form_type="10-Q",
        accepted_at=accepted_at,
        filing=filing,
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )
    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-1",
    )

    assert len(bundles) == 1
    bundle = bundles[0]
    facts_by_field = {fact.field_name: fact for fact in bundle.facts}
    assert set(facts_by_field) == {
        "total_revenue",
        "operating_income",
        "net_income",
        "diluted_eps",
        "operating_cash_flow",
        "cash_and_equivalents",
        "capex",
        "shares_outstanding",
    }

    evidence_by_field = {evidence.field_name: evidence for evidence in bundle.evidences}
    revenue_evidence = evidence_by_field["total_revenue"]
    assert revenue_evidence.locator_kind == "xbrl_xml"
    assert revenue_evidence.xbrl_concept == "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
    assert revenue_evidence.source_xpath == "revenue-q1"
    assert "duration_days=91" in revenue_evidence.source_span
    assert revenue_evidence.normalized_value == "1000.0"

    assert repo.logs == []


def test_build_bundles_from_provider_supports_10q_amendments(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 2, tzinfo=timezone.utc)
    filing = FakeFiling(
        form="10-Q/A",
        records=[
            {
                "fact_key": "revenue-q1a",
                "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-03-31",
                "value": 1100.0,
            },
            {
                "fact_key": "opinc-q1a",
                "concept": "us-gaap:OperatingIncomeLoss",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-03-31",
                "value": 210.0,
            },
            {
                "fact_key": "netinc-q1a",
                "concept": "us-gaap:NetIncomeLoss",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-03-31",
                "value": 160.0,
            },
            {
                "fact_key": "eps-q1a",
                "concept": "us-gaap:EarningsPerShareDiluted",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-03-31",
                "value": 1.35,
            },
            {
                "fact_key": "ocf-q2a",
                "concept": "us-gaap:NetCashProvidedByUsedInOperatingActivities",
                "statement_type": "CashFlowStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-06-30",
                "value": 330.0,
            },
            {
                "fact_key": "cash-q1a",
                "concept": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-03-31",
                "value": 460.0,
            },
            {
                "fact_key": "capex-q2a",
                "concept": "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
                "statement_type": "CashFlowStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-06-30",
                "value": 91.0,
            },
            {
                "fact_key": "shares-q2a",
                "concept": "dei:EntityCommonStockSharesOutstanding",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-06-30",
                "value": 5200000.0,
            },
        ],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000002",
        cik="0000789019",
        form_type="10-Q/A",
        accepted_at=accepted_at,
        filing=filing,
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-2",
    )

    assert len(bundles) == 1
    bundle = bundles[0]
    assert bundle.filing.is_amendment is True
    facts_by_field = {fact.field_name: fact for fact in bundle.facts}
    assert facts_by_field["total_revenue"].value_numeric == 1100.0
    assert facts_by_field["operating_income"].value_numeric == 210.0
    assert facts_by_field["net_income"].value_numeric == 160.0
    assert facts_by_field["diluted_eps"].value_numeric == 1.35
    assert facts_by_field["operating_cash_flow"].value_numeric == 330.0
    assert facts_by_field["cash_and_equivalents"].value_numeric == 460.0
    assert facts_by_field["capex"].value_numeric == 91.0
    assert facts_by_field["shares_outstanding"].value_numeric == 5200000.0
    assert repo.logs == []


def test_build_bundles_from_provider_skips_empty_issuer_10q_bundles(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 3, tzinfo=timezone.utc)
    filing = FakeFiling(
        form="10-Q",
        records=[
            {
                "fact_key": "rev-ytd-only",
                "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-06-30",
                "value": 2000.0,
            }
        ],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000003",
        cik="0000789019",
        form_type="10-Q",
        accepted_at=accepted_at,
        filing=filing,
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-3",
    )

    assert bundles == []
    assert len(repo.logs) == 1
    assert repo.logs[0]["error_type"] == "NO_TARGET_FIELDS_EXTRACTED"
