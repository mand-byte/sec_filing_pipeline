from __future__ import annotations

from datetime import datetime, timezone

from src.pipeline.extraction.engine import NumericExtractionEngine
from src.pipeline.extraction.registry import all_numeric_field_specs


class FakeXBRL:
    def __init__(self, records: list[dict[str, object]]):
        self.facts_view = records


class FakeFiling:
    def __init__(self, *, form: str, records: list[dict[str, object]]):
        self.form = form
        self._xbrl = FakeXBRL(records)

    def xbrl(self) -> FakeXBRL:
        return self._xbrl


def _issuer_spec(field_name: str):
    return next(
        spec
        for spec in all_numeric_field_specs()
        if spec.route == "issuer" and spec.field_name == field_name
    )


def test_extract_field_prefers_best_xbrl_fact() -> None:
    engine = NumericExtractionEngine()
    filing = FakeFiling(
        form="10-Q",
        records=[
            {
                "fact_key": "rev-secondary",
                "concept": "us-gaap:Revenues",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-03-31",
                "value": 950.0,
            },
            {
                "fact_key": "rev-best",
                "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": datetime(2024, 1, 1, tzinfo=timezone.utc),
                "period_end": datetime(2024, 3, 31, tzinfo=timezone.utc),
                "value": 1000.0,
            },
            {
                "fact_key": "rev-dimensioned",
                "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                "statement_type": "IncomeStatement",
                "dimensioned": True,
                "period_start": "2024-01-01",
                "period_end": "2024-03-31",
                "value": 5000.0,
            },
            {
                "fact_key": "rev-ytd",
                "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-06-30",
                "value": 2000.0,
            },
        ],
    )

    outcome = engine.extract_field(filing=filing, field_spec=_issuer_spec("total_revenue"))

    assert outcome["status"] == "ok"
    assert outcome["value_normalized"] == 1000.0
    assert outcome["xbrl_concept"] == "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
    assert outcome["source_xpath"] == "rev-best"
    assert "duration_days=91" in outcome["source_span"]


def test_extract_field_rejects_dimensioned_and_wrong_duration_candidates() -> None:
    engine = NumericExtractionEngine()
    filing = FakeFiling(
        form="10-Q/A",
        records=[
            {
                "fact_key": "opinc-dimensioned",
                "concept": "us-gaap:OperatingIncomeLoss",
                "statement_type": "IncomeStatement",
                "dimensioned": True,
                "period_start": "2024-01-01",
                "period_end": "2024-03-31",
                "value": 120.0,
            },
            {
                "fact_key": "opinc-ytd",
                "concept": "us-gaap:OperatingIncomeLoss",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-06-30",
                "value": 240.0,
            },
        ],
    )

    outcome = engine.extract_field(filing=filing, field_spec=_issuer_spec("operating_income"))

    assert outcome == {"status": "error", "error_code": "FIELD_NOT_FOUND"}


def test_extract_field_rejects_dimensioned_and_duration_total_debt_candidates() -> None:
    engine = NumericExtractionEngine()
    filing = FakeFiling(
        form="10-Q/A",
        records=[
            {
                "fact_key": "debt-dimensioned",
                "concept": "us-gaap:LongTermDebtAndFinanceLeaseObligations",
                "statement_type": "BalanceSheet",
                "dimensioned": True,
                "instant": "2024-06-30",
                "value": 999.0,
            },
            {
                "fact_key": "debt-duration",
                "concept": "us-gaap:LongTermDebtAndFinanceLeaseObligations",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "period_start": "2024-04-01",
                "period_end": "2024-06-30",
                "value": 888.0,
            },
        ],
    )

    outcome = engine.extract_field(filing=filing, field_spec=_issuer_spec("total_debt"))

    assert outcome == {"status": "error", "error_code": "FIELD_NOT_FOUND"}


def test_extract_field_rejects_negative_total_debt() -> None:
    engine = NumericExtractionEngine()
    filing = FakeFiling(
        form="10-Q",
        records=[
            {
                "fact_key": "debt-negative",
                "concept": "us-gaap:LongTermDebt",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-06-30",
                "value": -10.0,
            }
        ],
    )

    outcome = engine.extract_field(filing=filing, field_spec=_issuer_spec("total_debt"))

    assert outcome == {"status": "error", "error_code": "VALUE_OUT_OF_RANGE"}


def test_extract_field_prefers_primary_total_debt_concept() -> None:
    engine = NumericExtractionEngine()
    filing = FakeFiling(
        form="10-Q",
        records=[
            {
                "fact_key": "debt-fallback",
                "concept": "us-gaap:LongTermDebt",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-06-30",
                "value": 700.0,
            },
            {
                "fact_key": "debt-primary",
                "concept": "us-gaap:LongTermDebtAndFinanceLeaseObligations",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-06-30",
                "value": 710.0,
            },
        ],
    )

    outcome = engine.extract_field(filing=filing, field_spec=_issuer_spec("total_debt"))

    assert outcome["status"] == "ok"
    assert outcome["value_normalized"] == 710.0
    assert outcome["xbrl_concept"] == "us-gaap:LongTermDebtAndFinanceLeaseObligations"
    assert outcome["source_xpath"] == "debt-primary"


def test_extract_field_allows_negative_net_income() -> None:
    engine = NumericExtractionEngine()
    filing = FakeFiling(
        form="10-Q",
        records=[
            {
                "fact_key": "net-loss",
                "concept": "us-gaap:NetIncomeLoss",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-03-31",
                "value": -25.0,
            }
        ],
    )

    outcome = engine.extract_field(filing=filing, field_spec=_issuer_spec("net_income"))

    assert outcome["status"] == "ok"
    assert outcome["value_normalized"] == -25.0


def test_xbrl_logic_does_not_run_outside_enabled_form_families() -> None:
    engine = NumericExtractionEngine()
    filing = FakeFiling(
        form="10-K",
        records=[
            {
                "fact_key": "rev-annual",
                "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-12-31",
                "value": 999.0,
            }
        ],
    )

    outcome = engine.extract_field(filing=filing, field_spec=_issuer_spec("total_revenue"))

    assert outcome == {"status": "error", "error_code": "FIELD_NOT_FOUND"}


class FakeObjFirstFiling(FakeFiling):
    def obj(self) -> float:
        return 777.0


class FakeBrokenXBRL:
    def query(self):
        raise RuntimeError("broken query")


class FakeBrokenFiling:
    form = "10-Q"

    def xbrl(self) -> FakeBrokenXBRL:
        return FakeBrokenXBRL()


def test_xbrl_locator_precedes_obj_locator() -> None:
    engine = NumericExtractionEngine()
    filing = FakeObjFirstFiling(
        form="10-Q",
        records=[
            {
                "fact_key": "rev-best",
                "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-03-31",
                "value": 1000.0,
            }
        ],
    )

    outcome = engine.extract_field(filing=filing, field_spec=_issuer_spec("total_revenue"))

    assert outcome["status"] == "ok"
    assert outcome["locator_kind"] == "xbrl_xml"
    assert outcome["value_normalized"] == 1000.0


def test_extract_field_surfaces_xbrl_query_failures() -> None:
    engine = NumericExtractionEngine()

    outcome = engine.extract_field(
        filing=FakeBrokenFiling(),
        field_spec=_issuer_spec("total_revenue"),
    )

    assert outcome == {"status": "error", "error_code": "XBRL_QUERY_FAILED"}


def test_extract_field_selects_diluted_eps() -> None:
    engine = NumericExtractionEngine()
    filing = FakeFiling(
        form="10-Q",
        records=[
            {
                "fact_key": "eps-basic-diluted",
                "concept": "us-gaap:EarningsPerShareBasicAndDiluted",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-03-31",
                "value": 1.25,
            },
            {
                "fact_key": "eps-dimensioned",
                "concept": "us-gaap:EarningsPerShareDiluted",
                "statement_type": "IncomeStatement",
                "dimensioned": True,
                "period_start": "2024-01-01",
                "period_end": "2024-03-31",
                "value": 9.99,
            },
        ],
    )

    outcome = engine.extract_field(filing=filing, field_spec=_issuer_spec("diluted_eps"))

    assert outcome["status"] == "ok"
    assert outcome["value_normalized"] == 1.25
    assert outcome["xbrl_concept"] == "us-gaap:EarningsPerShareBasicAndDiluted"


def test_extract_field_selects_operating_cash_flow() -> None:
    engine = NumericExtractionEngine()
    filing = FakeFiling(
        form="10-Q",
        records=[
            {
                "fact_key": "ocf-q2-best",
                "concept": "us-gaap:NetCashProvidedByUsedInOperatingActivities",
                "statement_type": "CashFlowStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-06-30",
                "value": 320.0,
            },
            {
                "fact_key": "ocf-income-statement",
                "concept": "us-gaap:NetCashProvidedByUsedInOperatingActivities",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-06-30",
                "value": 999.0,
            },
            {
                "fact_key": "ocf-too-long",
                "concept": "us-gaap:NetCashProvidedByUsedInOperatingActivities",
                "statement_type": "CashFlowStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-12-31",
                "value": 111.0,
            },
        ],
    )

    outcome = engine.extract_field(filing=filing, field_spec=_issuer_spec("operating_cash_flow"))

    assert outcome["status"] == "ok"
    assert outcome["value_normalized"] == 320.0
    assert outcome["xbrl_concept"] == "us-gaap:NetCashProvidedByUsedInOperatingActivities"


def test_extract_field_selects_cash_and_equivalents_from_instant_fact() -> None:
    engine = NumericExtractionEngine()
    filing = FakeFiling(
        form="10-Q",
        records=[
            {
                "fact_key": "cash-current",
                "concept": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-03-31",
                "value": 450.0,
            },
            {
                "fact_key": "cash-prior",
                "concept": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2023-12-31",
                "value": 999.0,
            },
            {
                "fact_key": "cash-duration",
                "concept": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-03-31",
                "value": 777.0,
            },
        ],
    )

    outcome = engine.extract_field(filing=filing, field_spec=_issuer_spec("cash_and_equivalents"))

    assert outcome["status"] == "ok"
    assert outcome["value_normalized"] == 450.0
    assert outcome["xbrl_concept"] == "us-gaap:CashAndCashEquivalentsAtCarryingValue"
    assert "instant=2024-03-31" in outcome["source_span"]


def test_extract_field_selects_capex() -> None:
    engine = NumericExtractionEngine()
    filing = FakeFiling(
        form="10-Q",
        records=[
            {
                "fact_key": "capex-q2-best",
                "concept": "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
                "statement_type": "CashFlowStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-06-30",
                "value": 88.0,
            },
            {
                "fact_key": "capex-q2-dimensioned",
                "concept": "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
                "statement_type": "CashFlowStatement",
                "dimensioned": True,
                "period_start": "2024-01-01",
                "period_end": "2024-06-30",
                "value": 999.0,
            },
            {
                "fact_key": "capex-q4-too-long",
                "concept": "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
                "statement_type": "CashFlowStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-12-31",
                "value": 500.0,
            },
        ],
    )

    outcome = engine.extract_field(filing=filing, field_spec=_issuer_spec("capex"))

    assert outcome["status"] == "ok"
    assert outcome["value_normalized"] == 88.0
    assert outcome["xbrl_concept"] == "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment"


def test_extract_field_selects_shares_outstanding_from_current_instant() -> None:
    engine = NumericExtractionEngine()
    filing = FakeFiling(
        form="10-Q",
        records=[
            {
                "fact_key": "shares-current",
                "concept": "dei:EntityCommonStockSharesOutstanding",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-06-30",
                "value": 5100000.0,
            },
            {
                "fact_key": "shares-prior",
                "concept": "dei:EntityCommonStockSharesOutstanding",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-03-31",
                "value": 4900000.0,
            },
            {
                "fact_key": "shares-dimensioned",
                "concept": "us-gaap:CommonStockSharesOutstanding",
                "statement_type": "BalanceSheet",
                "dimensioned": True,
                "instant": "2024-06-30",
                "value": 9999999.0,
            },
        ],
    )

    outcome = engine.extract_field(filing=filing, field_spec=_issuer_spec("shares_outstanding"))

    assert outcome["status"] == "ok"
    assert outcome["value_normalized"] == 5100000.0
    assert outcome["xbrl_concept"] == "dei:EntityCommonStockSharesOutstanding"


def test_extract_field_selects_total_debt_from_current_instant_fact() -> None:
    engine = NumericExtractionEngine()
    filing = FakeFiling(
        form="10-Q",
        records=[
            {
                "fact_key": "debt-current-best",
                "concept": "us-gaap:LongTermDebtAndFinanceLeaseObligations",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-06-30",
                "value": 900.0,
            },
            {
                "fact_key": "debt-prior",
                "concept": "us-gaap:LongTermDebtAndFinanceLeaseObligations",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-03-31",
                "value": 850.0,
            },
        ],
    )

    outcome = engine.extract_field(filing=filing, field_spec=_issuer_spec("total_debt"))

    assert outcome["status"] == "ok"
    assert outcome["value_normalized"] == 900.0
    assert outcome["xbrl_concept"] == "us-gaap:LongTermDebtAndFinanceLeaseObligations"
    assert "instant=2024-06-30" in outcome["source_span"]
