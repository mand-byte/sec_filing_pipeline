from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import src.cli as cli_module
import src.pipeline.extraction.provider as provider_module
from src.pipeline.edgar_provider import FilingEnvelope
from src.pipeline.route_runtime import BundleBuildOutcome, FilingBundle
from src.pipeline.services import EvidenceInput, FactInput


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


class FakeEightKReport:
    def __init__(self, *, items: list[str], item_map: dict[str, str]):
        self.items = items
        self._item_map = item_map

    def __getitem__(self, key: str) -> str:
        return self._item_map[key]


class FakeEightKFiling:
    def __init__(self, *, form: str, report: FakeEightKReport, sections: list[str] | None = None):
        self.form = form
        self._report = report
        self._sections = sections or []

    def obj(self) -> FakeEightKReport:
        return self._report

    def sections(self) -> list[str]:
        return self._sections


class FakeTextFiling:
    def __init__(self, *, form: str, sections: list[str]):
        self.form = form
        self._sections = sections

    def sections(self) -> list[str]:
        return self._sections

    def parse(self) -> str:
        return "\n".join(self._sections)


class FakeXbrlTextFiling(FakeFiling):
    def __init__(self, *, form: str, records: list[dict[str, object]], sections: list[str]):
        super().__init__(form=form, records=records)
        self._sections = sections

    def sections(self) -> list[str]:
        return self._sections

    def parse(self) -> str:
        return "\n".join(self._sections)


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
            {
                "fact_key": "debt-q2",
                "concept": "us-gaap:LongTermDebtAndFinanceLeaseObligations",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-06-30",
                "value": 900.0,
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
        "total_debt",
    }

    evidence_by_field = {evidence.field_name: evidence for evidence in bundle.evidences}
    revenue_evidence = evidence_by_field["total_revenue"]
    assert revenue_evidence.locator_kind == "xbrl_xml"
    assert revenue_evidence.xbrl_concept == "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
    assert revenue_evidence.source_xpath == "revenue-q1"
    assert "duration_days=91" in revenue_evidence.source_span
    assert revenue_evidence.normalized_value == "1000.0"

    debt_evidence = evidence_by_field["total_debt"]
    assert debt_evidence.locator_kind == "xbrl_xml"
    assert debt_evidence.xbrl_concept == "us-gaap:LongTermDebtAndFinanceLeaseObligations"
    assert debt_evidence.source_xpath == "debt-q2"
    assert "instant=2024-06-30" in debt_evidence.source_span
    assert debt_evidence.normalized_value == "900.0"

    assert repo.logs == []


def test_build_bundles_from_provider_emits_10q_text_alongside_xbrl_numeric(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 1, tzinfo=timezone.utc)
    filing = FakeXbrlTextFiling(
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
                "fact_key": "cash-q1",
                "concept": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-03-31",
                "value": 450.0,
            },
        ],
        sections=[
            "MD&A\nManagement expects revenue up in the next quarter.",
            "Risk Factors\nCybersecurity incidents may materially affect our operations.",
        ],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000001A",
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
        run_id="run-1-text-10q",
    )

    assert len(bundles) == 1
    facts_by_field = {(fact.field_name, fact.subject_key): fact for fact in bundles[0].facts}
    assert facts_by_field[("total_revenue", "document")].value_numeric == 1000.0
    assert facts_by_field[("cash_and_equivalents", "document")].value_numeric == 450.0
    assert facts_by_field[("mdna_outlook_quant", "document")].value_text == "up"
    assert facts_by_field[("risk_factor_quant", "document")].value_text == "Cybersecurity"
    assert repo.logs == []


def test_build_bundles_from_provider_keeps_10q_numeric_when_mdna_text_fails(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 1, tzinfo=timezone.utc)
    filing = FakeXbrlTextFiling(
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
                "fact_key": "cash-q1",
                "concept": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-03-31",
                "value": 450.0,
            },
        ],
        sections=[
            "MD&A\nManagement expects revenue up in the next quarter.",
            "Risk Factors\nCybersecurity incidents may materially affect our operations.",
        ],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000001B",
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
    original_extract_field = provider_module.TextExtractionEngine.extract_field

    def failing_extract_field(self, *, filing, field_spec):
        if field_spec.field_name == "mdna_outlook_quant":
            return {"status": "error", "error_code": "FORCED_TEXT_FAILURE"}
        return original_extract_field(self, filing=filing, field_spec=field_spec)

    monkeypatch.setattr(provider_module.TextExtractionEngine, "extract_field", failing_extract_field)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-1-mdna-fail-10q",
    )

    assert len(bundles) == 1
    facts_by_field = {(fact.field_name, fact.subject_key): fact for fact in bundles[0].facts}
    assert facts_by_field[("total_revenue", "document")].value_numeric == 1000.0
    assert facts_by_field[("cash_and_equivalents", "document")].value_numeric == 450.0
    assert ("mdna_outlook_quant", "document") not in facts_by_field
    assert facts_by_field[("risk_factor_quant", "document")].value_text == "Cybersecurity"
    assert any(log["error_type"] == "FORCED_TEXT_FAILURE" for log in repo.logs)


def test_build_bundles_from_provider_emits_10k_numeric_xbrl_evidence(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 2, tzinfo=timezone.utc)
    filing = FakeFiling(
        form="10-K",
        records=[
            {
                "fact_key": "revenue-annual",
                "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-12-31",
                "value": 5000.0,
            },
            {
                "fact_key": "cash-annual",
                "concept": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-12-31",
                "value": 900.0,
            },
            {
                "fact_key": "shares-annual",
                "concept": "dei:EntityCommonStockSharesOutstanding",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-12-31",
                "value": 6000000.0,
            },
        ],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000016",
        cik="0000789019",
        form_type="10-K",
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
        run_id="run-1k",
    )

    assert len(bundles) == 1
    facts_by_field = {fact.field_name: fact for fact in bundles[0].facts}
    assert facts_by_field["total_revenue"].value_numeric == 5000.0
    assert facts_by_field["cash_and_equivalents"].value_numeric == 900.0
    assert facts_by_field["shares_outstanding"].value_numeric == 6000000.0


def test_build_bundles_from_provider_emits_20f_numeric_xbrl_evidence(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 3, tzinfo=timezone.utc)
    filing = FakeFiling(
        form="20-F",
        records=[
            {
                "fact_key": "revenue-20f",
                "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-12-31",
                "value": 5100.0,
            },
            {
                "fact_key": "cash-20f",
                "concept": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-12-31",
                "value": 980.0,
            },
        ],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000017",
        cik="0000789019",
        form_type="20-F",
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
        run_id="run-20f",
    )

    assert len(bundles) == 1
    facts_by_field = {fact.field_name: fact for fact in bundles[0].facts}
    assert facts_by_field["total_revenue"].value_numeric == 5100.0
    assert facts_by_field["cash_and_equivalents"].value_numeric == 980.0


def test_build_bundles_from_provider_emits_20f_risk_factor_text_alongside_xbrl_numeric(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 3, tzinfo=timezone.utc)
    filing = FakeXbrlTextFiling(
        form="20-F",
        records=[
            {
                "fact_key": "revenue-20f",
                "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-12-31",
                "value": 5100.0,
            },
            {
                "fact_key": "cash-20f",
                "concept": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-12-31",
                "value": 980.0,
            },
        ],
        sections=["Risk Factors\nCybersecurity incidents may materially affect our foreign operations."],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000017A",
        cik="0000789019",
        form_type="20-F",
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
        run_id="run-20f-text",
    )

    assert len(bundles) == 1
    facts_by_field = {(fact.field_name, fact.subject_key): fact for fact in bundles[0].facts}
    assert facts_by_field[("total_revenue", "document")].value_numeric == 5100.0
    assert facts_by_field[("cash_and_equivalents", "document")].value_numeric == 980.0
    assert facts_by_field[("risk_factor_quant", "document")].value_text == "Cybersecurity"


def test_build_bundles_from_provider_keeps_20f_numeric_when_risk_factor_text_fails(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 3, tzinfo=timezone.utc)
    filing = FakeXbrlTextFiling(
        form="20-F",
        records=[
            {
                "fact_key": "revenue-20f",
                "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-12-31",
                "value": 5100.0,
            },
            {
                "fact_key": "cash-20f",
                "concept": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-12-31",
                "value": 980.0,
            },
        ],
        sections=["Risk Factors\nCybersecurity incidents may materially affect our foreign operations."],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000017B",
        cik="0000789019",
        form_type="20-F",
        accepted_at=accepted_at,
        filing=filing,
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    original_extract_field = provider_module.TextExtractionEngine.extract_field

    def failing_extract_field(self, *, filing, field_spec):
        if field_spec.field_name == "risk_factor_quant":
            return {"status": "error", "error_code": "FORCED_TEXT_FAILURE"}
        return original_extract_field(self, filing=filing, field_spec=field_spec)

    monkeypatch.setattr(provider_module.TextExtractionEngine, "extract_field", failing_extract_field)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-20f-risk-failure",
    )

    assert len(bundles) == 1
    facts_by_field = {(fact.field_name, fact.subject_key): fact for fact in bundles[0].facts}
    assert facts_by_field[("total_revenue", "document")].value_numeric == 5100.0
    assert facts_by_field[("cash_and_equivalents", "document")].value_numeric == 980.0
    assert ("risk_factor_quant", "document") not in facts_by_field
    assert any(log["error_type"] == "FORCED_TEXT_FAILURE" for log in repo.logs)


def test_build_bundles_from_provider_emits_6k_financial_numeric_xbrl_evidence(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 4, tzinfo=timezone.utc)
    filing = FakeFiling(
        form="6-K-financial",
        records=[
            {
                "fact_key": "cash-6k-financial",
                "concept": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-12-31",
                "value": 615.0,
            }
        ],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000018",
        cik="0000789019",
        form_type="6-K-financial",
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
        run_id="run-6kfin",
    )

    assert len(bundles) == 1
    facts_by_field = {fact.field_name: fact for fact in bundles[0].facts}
    assert facts_by_field["cash_and_equivalents"].value_numeric == 615.0


def test_build_bundles_from_provider_emits_6k_financial_mdna_text_alongside_xbrl_numeric(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 4, tzinfo=timezone.utc)
    filing = FakeXbrlTextFiling(
        form="6-K-financial",
        records=[
            {
                "fact_key": "cash-6k-financial",
                "concept": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-12-31",
                "value": 615.0,
            }
        ],
        sections=["Operating and Financial Review\nManagement expects revenue up in the next quarter."],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000018A",
        cik="0000789019",
        form_type="6-K-financial",
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
        run_id="run-6kfin-text",
    )

    assert len(bundles) == 1
    facts_by_field = {(fact.field_name, fact.subject_key): fact for fact in bundles[0].facts}
    assert facts_by_field[("cash_and_equivalents", "document")].value_numeric == 615.0
    assert facts_by_field[("mdna_outlook_quant", "document")].value_text == "up"


def test_build_bundles_from_provider_keeps_6k_financial_numeric_when_mdna_text_fails(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 4, tzinfo=timezone.utc)
    filing = FakeXbrlTextFiling(
        form="6-K-financial",
        records=[
            {
                "fact_key": "cash-6k-financial",
                "concept": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-12-31",
                "value": 615.0,
            }
        ],
        sections=["Operating and Financial Review\nManagement expects revenue up in the next quarter."],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000018B",
        cik="0000789019",
        form_type="6-K-financial",
        accepted_at=accepted_at,
        filing=filing,
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    original_extract_field = provider_module.TextExtractionEngine.extract_field

    def failing_extract_field(self, *, filing, field_spec):
        if field_spec.field_name == "mdna_outlook_quant":
            return {"status": "error", "error_code": "FORCED_TEXT_FAILURE"}
        return original_extract_field(self, filing=filing, field_spec=field_spec)

    monkeypatch.setattr(provider_module.TextExtractionEngine, "extract_field", failing_extract_field)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-6kfin-mdna-failure",
    )

    assert len(bundles) == 1
    facts_by_field = {(fact.field_name, fact.subject_key): fact for fact in bundles[0].facts}
    assert facts_by_field[("cash_and_equivalents", "document")].value_numeric == 615.0
    assert ("mdna_outlook_quant", "document") not in facts_by_field
    assert any(log["error_type"] == "FORCED_TEXT_FAILURE" for log in repo.logs)


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
            {
                "fact_key": "debt-q2a",
                "concept": "us-gaap:LongTermDebtAndFinanceLeaseObligations",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-06-30",
                "value": 910.0,
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
    assert facts_by_field["total_debt"].value_numeric == 910.0
    assert repo.logs == []


def test_build_bundles_from_provider_preserves_filing_metadata(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 8, tzinfo=timezone.utc)
    filed_at = datetime(2024, 5, 7, tzinfo=timezone.utc)
    period_end = datetime(2024, 3, 31, tzinfo=timezone.utc)
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
            }
        ],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000008",
        cik="0000789019",
        form_type="10-Q/A",
        accepted_at=accepted_at,
        filing=filing,
        filed_at=filed_at,
        period_end=period_end,
        amendment_no=2,
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    bundles = cli_module._build_bundles_from_provider(
        security=SimpleNamespace(cik="0000789019", ticker="MSFT"),
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=FakeRepo(),
        run_id="run-8",
    )

    assert len(bundles) == 1
    assert bundles[0].filing.filed_at == filed_at
    assert bundles[0].filing.period_end == period_end
    assert bundles[0].filing.amendment_no == 2


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



def test_build_bundles_from_provider_emits_8k_vote_rows(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 4, tzinfo=timezone.utc)
    filing = FakeEightKFiling(
        form="8-K",
        report=FakeEightKReport(
            items=["Item 5.07"],
            item_map={
                "Item 5.07": """
Proposal 1 Election of Directors 1,000,000 200,000 30,000 50,000
Proposal 2 Advisory Vote on Executive Compensation 900,000 250,000 20,000 110,000
""",
            },
        ),
        sections=["Current report\nvote event"],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000004",
        cik="0000789019",
        form_type="8-K",
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
        run_id="run-4",
    )

    assert len(bundles) == 1
    bundle = bundles[0]
    facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundle.facts}
    assert facts[("proposal_votes_for", "proposal:1")] == 1000000.0
    assert facts[("proposal_votes_against", "proposal:1")] == 200000.0
    assert facts[("proposal_votes_abstain", "proposal:1")] == 30000.0
    assert facts[("proposal_broker_non_votes", "proposal:1")] == 50000.0
    assert facts[("proposal_votes_for", "proposal:2")] == 900000.0
    assert facts[("proposal_broker_non_votes", "proposal:2")] == 110000.0

    evidence = {(item.field_name, item.subject_key): item for item in bundle.evidences}
    assert evidence[("proposal_votes_for", "proposal:1")].source_item_no == "5.07"
    assert evidence[("proposal_votes_for", "proposal:1")].source_span == "items[Item 5.07].line[1]"
    assert repo.logs == []


def test_build_bundles_from_provider_emits_8k_current_event_text(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 4, tzinfo=timezone.utc)
    filing = FakeEightKFiling(
        form="8-K",
        report=FakeEightKReport(
            items=["Item 1.01"],
            item_map={"Item 1.01": "Entry into a material definitive agreement."},
        ),
        sections=["Current report\nMaterial definitive agreement entered into on signing date."],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000004A",
        cik="0000789019",
        form_type="8-K",
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
        run_id="run-4-current-event",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("current_event_quant", "document")] == "agreement"
    evidence = {(item.field_name, item.subject_key): item for item in bundles[0].evidences}
    assert evidence[("current_event_quant", "document")].source_section in {"Current report", "current report"}
    assert repo.logs == []


def test_build_bundles_from_provider_emits_6k_current_event_text(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 4, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000004C",
        cik="0000789019",
        form_type="6-K",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="6-K",
            sections=["Current report\nMaterial definitive agreement entered into on signing date."],
        ),
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
        run_id="run-6k-current-event",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("current_event_quant", "document")] == "agreement"
    evidence = {(item.field_name, item.subject_key): item for item in bundles[0].evidences}
    assert evidence[("current_event_quant", "document")].source_section in {"Current report", "current report"}
    assert any(log["error_type"] == "TYPE_MISMATCH" for log in repo.logs)


def test_build_bundles_from_provider_logs_missing_8k_vote_rows(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 5, tzinfo=timezone.utc)
    filing = FakeEightKFiling(
        form="8-K",
        report=FakeEightKReport(
            items=["Item 5.07"],
            item_map={
                "Item 5.07": "No tabulated vote counts were included in this item.",
            },
        ),
        sections=["Current report\nvote event"],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000005",
        cik="0000789019",
        form_type="8-K",
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
        run_id="run-5",
    )

    assert len(bundles) == 1
    vote_facts = [fact for fact in bundles[0].facts if fact.field_name.startswith("proposal_votes_") or fact.field_name == "proposal_broker_non_votes"]
    assert vote_facts == []
    assert any(log["error_type"] == "NO_VOTE_ROWS_EXTRACTED" for log in repo.logs)


def test_build_bundles_from_provider_keeps_8k_vote_rows_when_current_event_text_fails(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 4, tzinfo=timezone.utc)
    filing = FakeEightKFiling(
        form="8-K",
        report=FakeEightKReport(
            items=["Item 5.07"],
            item_map={
                "Item 5.07": "Proposal 1 Election of Directors 1,000,000 200,000 30,000 50,000",
            },
        ),
        sections=["Current report\nMaterial definitive agreement entered into on signing date."],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000004B",
        cik="0000789019",
        form_type="8-K",
        accepted_at=accepted_at,
        filing=filing,
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    original_extract_field = provider_module.TextExtractionEngine.extract_field

    def failing_extract_field(self, *, filing, field_spec):
        if field_spec.field_name == "current_event_quant":
            return {"status": "error", "error_code": "FORCED_TEXT_FAILURE"}
        return original_extract_field(self, filing=filing, field_spec=field_spec)

    monkeypatch.setattr(provider_module.TextExtractionEngine, "extract_field", failing_extract_field)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-4-current-event-failure",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("proposal_votes_for", "proposal:1")] == 1000000.0
    assert numeric_facts[("proposal_votes_against", "proposal:1")] == 200000.0
    assert numeric_facts[("proposal_votes_abstain", "proposal:1")] == 30000.0
    assert numeric_facts[("proposal_broker_non_votes", "proposal:1")] == 50000.0
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert ("current_event_quant", "document") not in text_facts
    assert any(log["error_type"] == "FORCED_TEXT_FAILURE" for log in repo.logs)


def test_build_bundles_from_provider_returns_empty_6k_bundle_when_current_event_text_fails(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 4, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000004D",
        cik="0000789019",
        form_type="6-K",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="6-K",
            sections=["Current report\nMaterial definitive agreement entered into on signing date."],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    original_extract_field = provider_module.TextExtractionEngine.extract_field

    def failing_extract_field(self, *, filing, field_spec):
        if field_spec.field_name == "current_event_quant":
            return {"status": "error", "error_code": "FORCED_TEXT_FAILURE"}
        return original_extract_field(self, filing=filing, field_spec=field_spec)

    monkeypatch.setattr(provider_module.TextExtractionEngine, "extract_field", failing_extract_field)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-6k-current-event-failure",
    )

    assert len(bundles) == 1
    assert bundles[0].facts == []
    assert bundles[0].evidences == []
    assert any(log["error_type"] == "FORCED_TEXT_FAILURE" for log in repo.logs)


def test_build_bundles_from_provider_logs_missing_8k_vote_rows_without_blocking_deal_fields(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 5, tzinfo=timezone.utc)
    filing = FakeEightKFiling(
        form="8-K",
        report=FakeEightKReport(
            items=["Item 5.07"],
            item_map={
                "Item 5.07": "No tabulated vote counts were included in this item.",
            },
        ),
        sections=[
            "Current report\nTransaction value of $7,250,000. Cash consideration per share was $14.50. Financing commitment of $3,000,000. Termination fee of $250,000."
        ],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000005B",
        cik="0000789019",
        form_type="8-K",
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
        run_id="run-5-missing-vote-with-deal",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("deal_value", "document")] == 7250000.0
    assert numeric_facts[("offer_price_per_share", "security:1")] == 14.5
    assert numeric_facts[("financing_commitment_amount", "document")] == 3000000.0
    assert numeric_facts[("termination_fee", "document")] == 250000.0
    vote_fields = {key for key in numeric_facts if key[0].startswith("proposal_votes_") or key[0] == "proposal_broker_non_votes"}
    assert vote_fields == set()
    assert any(log["error_type"] == "NO_VOTE_ROWS_EXTRACTED" for log in repo.logs)


def test_build_bundles_from_provider_logs_invalid_8k_vote_subject_contract_without_blocking_deal_fields(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 5, tzinfo=timezone.utc)
    filing = FakeEightKFiling(
        form="8-K",
        report=FakeEightKReport(
            items=["Item 5.07"],
            item_map={
                "Item 5.07": "Vote results appear in malformed bundle output.",
            },
        ),
        sections=[
            "Current report\nTransaction value of $7,250,000. Cash consideration per share was $14.50. Financing commitment of $3,000,000. Termination fee of $250,000."
        ],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000005A",
        cik="0000789019",
        form_type="8-K",
        accepted_at=accepted_at,
        filing=filing,
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    def build_invalid_vote_bundle(*, envelope, filing):
        del envelope
        return BundleBuildOutcome(
            bundle=FilingBundle(
                filing=filing,
                facts=[
                    FactInput(
                        field_name="proposal_votes_for",
                        subject_key="document",
                        value_numeric=1000000.0,
                        confidence=0.99,
                    )
                ],
                evidences=[
                    EvidenceInput(
                        field_name="proposal_votes_for",
                        subject_key="document",
                        locator_kind="obj",
                        source_span="items[Item 5.07].line[1]",
                        raw_value="1000000",
                        normalized_value="1000000.0",
                    )
                ],
            ),
            item_present=True,
        )

    monkeypatch.setattr(provider_module, "build_issuer_8k_vote_bundle", build_invalid_vote_bundle)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-5-invalid-vote-contract",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("deal_value", "document")] == 7250000.0
    assert numeric_facts[("offer_price_per_share", "security:1")] == 14.5
    assert ("proposal_votes_for", "document") not in numeric_facts
    assert any(log["error_type"] == "SPECIALIZED_SUBJECT_CONTRACT_VIOLATION" for log in repo.logs)



def test_build_bundles_from_provider_emits_8k_three_column_vote_rows(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 6, tzinfo=timezone.utc)
    filing = FakeEightKFiling(
        form="8-K",
        report=FakeEightKReport(
            items=["Item 5.07"],
            item_map={
                "Item 5.07": "Proposal 2024 Plan Approval 1,500,000 25 10",
            },
        ),
        sections=["Current report\nvote event"],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000006",
        cik="0000789019",
        form_type="8-K",
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
        run_id="run-6",
    )

    assert len(bundles) == 1
    facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts}
    assert facts[("proposal_votes_for", "proposal:1")] == 1500000.0
    assert facts[("proposal_votes_against", "proposal:1")] == 25.0
    assert facts[("proposal_votes_abstain", "proposal:1")] == 10.0
    assert ("proposal_broker_non_votes", "proposal:1") not in facts
    assert repo.logs == []



def test_build_bundles_from_provider_emits_8k_four_column_vote_rows_with_year_label(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 7, tzinfo=timezone.utc)
    filing = FakeEightKFiling(
        form="8-K",
        report=FakeEightKReport(
            items=["Item 5.07"],
            item_map={
                "Item 5.07": "Proposal 2024 Plan Approval 1,500,000 250,000 25 10",
            },
        ),
        sections=["Current report\nvote event"],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000007",
        cik="0000789019",
        form_type="8-K",
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
        run_id="run-7",
    )

    assert len(bundles) == 1
    facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts}
    assert facts[("proposal_votes_for", "proposal:1")] == 1500000.0
    assert facts[("proposal_votes_against", "proposal:1")] == 250000.0
    assert facts[("proposal_votes_abstain", "proposal:1")] == 25.0
    assert facts[("proposal_broker_non_votes", "proposal:1")] == 10.0
    assert repo.logs == []


def test_build_bundles_from_provider_emits_delay_reason_text(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 9, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000009",
        cik="0000789019",
        form_type="NT 10-Q",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="NT 10-Q",
            sections=["Delay reason\nThe filing was delayed because of the audit review and the registrant expects to file within 5 calendar days."],
        ),
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
        run_id="run-9",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("delay_reason_quant", "document")] == "audit"
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("filing_delay_days", "document")] == 5.0
    evidence = {(item.field_name, item.subject_key): item for item in bundles[0].evidences}
    assert evidence[("delay_reason_quant", "document")].source_section in {"delay", "Delay reason"}
    assert evidence[("filing_delay_days", "document")].locator_kind == "parse_text"
    assert any(log["error_type"] == "TYPE_MISMATCH" for log in repo.logs)


def test_build_bundles_from_provider_keeps_delay_days_when_delay_reason_text_fails(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 9, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000009A",
        cik="0000789019",
        form_type="NT 10-Q",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="NT 10-Q",
            sections=["Delay reason\nThe filing was delayed because of the audit review and the registrant expects to file within 5 calendar days."],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    original_extract_field = provider_module.TextExtractionEngine.extract_field

    def failing_extract_field(self, *, filing, field_spec):
        if field_spec.field_name == "delay_reason_quant":
            return {"status": "error", "error_code": "FORCED_TEXT_FAILURE"}
        return original_extract_field(self, filing=filing, field_spec=field_spec)

    monkeypatch.setattr(provider_module.TextExtractionEngine, "extract_field", failing_extract_field)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-9-text-failure",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("filing_delay_days", "document")] == 5.0
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert ("delay_reason_quant", "document") not in text_facts
    assert any(log["error_type"] == "FORCED_TEXT_FAILURE" for log in repo.logs)


def test_build_bundles_from_provider_keeps_nt10k_delay_days_when_delay_reason_text_fails(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 9, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000009B",
        cik="0000789019",
        form_type="NT 10-K",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="NT 10-K",
            sections=["Delay reason\nThe filing was delayed because of the audit review and the registrant expects to file within 5 calendar days."],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    original_extract_field = provider_module.TextExtractionEngine.extract_field

    def failing_extract_field(self, *, filing, field_spec):
        if field_spec.field_name == "delay_reason_quant":
            return {"status": "error", "error_code": "FORCED_TEXT_FAILURE"}
        return original_extract_field(self, filing=filing, field_spec=field_spec)

    monkeypatch.setattr(provider_module.TextExtractionEngine, "extract_field", failing_extract_field)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-9k-text-failure",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("filing_delay_days", "document")] == 5.0
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert ("delay_reason_quant", "document") not in text_facts
    assert any(log["error_type"] == "FORCED_TEXT_FAILURE" for log in repo.logs)


def test_build_bundles_from_provider_emits_mdna_outlook_text(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 9, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000013",
        cik="0000789019",
        form_type="S-1",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="S-1",
            sections=["MD&A\nManagement expects revenue up in the next quarter."],
        ),
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
        run_id="run-13",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("mdna_outlook_quant", "document")] == "up"
    evidence = {(item.field_name, item.subject_key): item for item in bundles[0].evidences}
    assert evidence[("mdna_outlook_quant", "document")].source_section in {"md&a", "MD&A"}
    assert any(log["error_type"] == "TYPE_MISMATCH" for log in repo.logs)


def test_build_bundles_from_provider_keeps_s1_offering_numeric_when_mdna_text_fails(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 9, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000013A",
        cik="0000789019",
        form_type="S-1",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="S-1",
            sections=[
                "Use of Proceeds\nGross proceeds of $5,000,000 are expected. Net proceeds of $4,500,000 after underwriting discounts and commissions of $500,000. The offering price per share was $10.00 with an offering of 500,000 shares of common stock. Financing commitment of $2,000,000 has been arranged.",
                "MD&A\nManagement expects revenue up in the next quarter.",
            ],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    original_extract_field = provider_module.TextExtractionEngine.extract_field

    def failing_extract_field(self, *, filing, field_spec):
        if field_spec.field_name == "mdna_outlook_quant":
            return {"status": "error", "error_code": "FORCED_TEXT_FAILURE"}
        return original_extract_field(self, filing=filing, field_spec=field_spec)

    monkeypatch.setattr(provider_module.TextExtractionEngine, "extract_field", failing_extract_field)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-13-mdna-failure",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("gross_proceeds", "document")] == 5000000.0
    assert numeric_facts[("net_proceeds", "document")] == 4500000.0
    assert numeric_facts[("underwriter_discount_total", "document")] == 500000.0
    assert numeric_facts[("offering_price_per_share", "security:1")] == 10.0
    assert numeric_facts[("securities_offered_qty", "security:1")] == 500000.0
    assert numeric_facts[("financing_commitment_amount", "document")] == 2000000.0
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert ("mdna_outlook_quant", "document") not in text_facts
    assert any(log["error_type"] == "FORCED_TEXT_FAILURE" for log in repo.logs)


def test_build_bundles_from_provider_emits_risk_factor_text(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 9, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000014",
        cik="0000789019",
        form_type="10-K",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="10-K",
            sections=["Risk Factors\nCybersecurity incidents may materially affect our operations."],
        ),
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
        run_id="run-14",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("risk_factor_quant", "document")] == "Cybersecurity"
    evidence = {(item.field_name, item.subject_key): item for item in bundles[0].evidences}
    assert evidence[("risk_factor_quant", "document")].source_section in {"risk factors", "Risk Factors"}


def test_build_bundles_from_provider_keeps_10k_numeric_when_risk_factor_text_fails(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 2, tzinfo=timezone.utc)
    filing = FakeXbrlTextFiling(
        form="10-K",
        records=[
            {
                "fact_key": "revenue-annual",
                "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                "statement_type": "IncomeStatement",
                "dimensioned": False,
                "period_start": "2024-01-01",
                "period_end": "2024-12-31",
                "value": 5000.0,
            },
            {
                "fact_key": "cash-annual",
                "concept": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-12-31",
                "value": 900.0,
            },
            {
                "fact_key": "shares-annual",
                "concept": "dei:EntityCommonStockSharesOutstanding",
                "statement_type": "BalanceSheet",
                "dimensioned": False,
                "instant": "2024-12-31",
                "value": 6000000.0,
            },
        ],
        sections=["Risk Factors\nCybersecurity incidents may materially affect our operations."],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000016A",
        cik="0000789019",
        form_type="10-K",
        accepted_at=accepted_at,
        filing=filing,
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    original_extract_field = provider_module.TextExtractionEngine.extract_field

    def failing_extract_field(self, *, filing, field_spec):
        if field_spec.field_name == "risk_factor_quant":
            return {"status": "error", "error_code": "FORCED_TEXT_FAILURE"}
        return original_extract_field(self, filing=filing, field_spec=field_spec)

    monkeypatch.setattr(provider_module.TextExtractionEngine, "extract_field", failing_extract_field)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-14-risk-failure",
    )

    assert len(bundles) == 1
    facts_by_field = {(fact.field_name, fact.subject_key): fact for fact in bundles[0].facts}
    assert facts_by_field[("total_revenue", "document")].value_numeric == 5000.0
    assert facts_by_field[("cash_and_equivalents", "document")].value_numeric == 900.0
    assert facts_by_field[("shares_outstanding", "document")].value_numeric == 6000000.0
    assert ("risk_factor_quant", "document") not in facts_by_field
    assert any(log["error_type"] == "FORCED_TEXT_FAILURE" for log in repo.logs)


def test_build_bundles_from_provider_emits_use_of_proceeds_text(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 10, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000010",
        cik="0000789019",
        form_type="S-1",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="S-1",
            sections=["Use of Proceeds\nWe intend to use the proceeds for working capital."],
        ),
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
        run_id="run-10",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("use_of_proceeds_quant", "document")] == "working capital"
    evidence = {(item.field_name, item.subject_key): item for item in bundles[0].evidences}
    assert evidence[("use_of_proceeds_quant", "document")].source_section in {"use of proceeds", "Use of Proceeds"}
    assert any(log["error_type"] == "TYPE_MISMATCH" for log in repo.logs)


def test_build_bundles_from_provider_keeps_s1_offering_numeric_when_use_of_proceeds_text_fails(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 10, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000010A",
        cik="0000789019",
        form_type="S-1",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="S-1",
            sections=[
                "Use of Proceeds\nGross proceeds of $5,000,000 are expected. Net proceeds of $4,500,000 after underwriting discounts and commissions of $500,000. The offering price per share was $10.00 with an offering of 500,000 shares of common stock. Financing commitment of $2,000,000 has been arranged. We intend to use the proceeds for working capital."
            ],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    original_extract_field = provider_module.TextExtractionEngine.extract_field

    def failing_extract_field(self, *, filing, field_spec):
        if field_spec.field_name == "use_of_proceeds_quant":
            return {"status": "error", "error_code": "FORCED_TEXT_FAILURE"}
        return original_extract_field(self, filing=filing, field_spec=field_spec)

    monkeypatch.setattr(provider_module.TextExtractionEngine, "extract_field", failing_extract_field)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-10-text-failure",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("gross_proceeds", "document")] == 5000000.0
    assert numeric_facts[("net_proceeds", "document")] == 4500000.0
    assert numeric_facts[("underwriter_discount_total", "document")] == 500000.0
    assert numeric_facts[("offering_price_per_share", "security:1")] == 10.0
    assert numeric_facts[("securities_offered_qty", "security:1")] == 500000.0
    assert numeric_facts[("financing_commitment_amount", "document")] == 2000000.0
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert ("use_of_proceeds_quant", "document") not in text_facts
    assert any(log["error_type"] == "FORCED_TEXT_FAILURE" for log in repo.logs)


def test_build_bundles_from_provider_emits_proxy_proposal_text(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 11, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000011",
        cik="0000789019",
        form_type="DEF 14A",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="DEF 14A",
            sections=["Proposal 1\nThe board recommends election of directors at the annual meeting."],
        ),
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
        run_id="run-11",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("proxy_proposal_quant", "document")] == "election"
    evidence = {(item.field_name, item.subject_key): item for item in bundles[0].evidences}
    assert evidence[("proxy_proposal_quant", "document")].source_section in {"proposal", "Proposal 1"}


def test_build_bundles_from_provider_emits_comp_policy_text(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 11, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000015",
        cik="0000789019",
        form_type="DEF 14A",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="DEF 14A",
            sections=["CD&A\nThe company emphasizes pay for performance in executive compensation."],
        ),
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
        run_id="run-15",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("comp_policy_quant", "document")] == "pay for performance"
    evidence = {(item.field_name, item.subject_key): item for item in bundles[0].evidences}
    assert evidence[("comp_policy_quant", "document")].source_section in {"cd&a", "CD&A"}


def test_build_bundles_from_provider_emits_tender_going_private_text(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 12, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000012",
        cik="0000789019",
        form_type="SC TO-I",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="SC TO-I",
            sections=["Summary term sheet\nThis transaction is a cash merger that the committee determined was fair."],
        ),
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
        run_id="run-12",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("tender_going_private_quant", "document")] == "cash merger"
    evidence = {(item.field_name, item.subject_key): item for item in bundles[0].evidences}
    assert evidence[("tender_going_private_quant", "document")].source_section in {"summary term sheet", "Summary term sheet"}
    assert any(log["error_type"] == "TYPE_MISMATCH" for log in repo.logs)


def test_build_bundles_from_provider_keeps_sc_toi_deal_numeric_when_text_field_extraction_fails(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 12, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000012B",
        cik="0000789019",
        form_type="SC TO-I",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="SC TO-I",
            sections=[
                "Summary term sheet\nThis transaction is a cash merger that the committee determined was fair. Transaction value of $12,000,000. Offer price per share was $24.00. 500,000 shares sought. Financing commitment of $8,000,000. Termination fee of $600,000."
            ],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    original_extract_field = provider_module.TextExtractionEngine.extract_field

    def failing_extract_field(self, *, filing, field_spec):
        if field_spec.field_name == "tender_going_private_quant":
            return {"status": "error", "error_code": "FORCED_TEXT_FAILURE"}
        return original_extract_field(self, filing=filing, field_spec=field_spec)

    monkeypatch.setattr(provider_module.TextExtractionEngine, "extract_field", failing_extract_field)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-sc-toi-text-failure",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("deal_value", "document")] == 12000000.0
    assert numeric_facts[("offer_price_per_share", "security:1")] == 24.0
    assert numeric_facts[("tender_shares_sought", "security:1")] == 500000.0
    assert numeric_facts[("financing_commitment_amount", "document")] == 8000000.0
    assert numeric_facts[("termination_fee", "document")] == 600000.0
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert ("tender_going_private_quant", "document") not in text_facts
    assert any(log["error_type"] == "FORCED_TEXT_FAILURE" for log in repo.logs)


def test_build_bundles_from_provider_keeps_sc_13e3_deal_numeric_when_text_field_extraction_fails(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 15, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000021B",
        cik="0000789019",
        form_type="SC 13E3",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="SC 13E3",
            sections=[
                "Special factors\nThis transaction is a cash merger that the committee determined was fair. Deal value of $9,500,000. Cash consideration per share was $19.00. Financing commitment of $4,000,000. Break-up fee of $350,000."
            ],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    original_extract_field = provider_module.TextExtractionEngine.extract_field

    def failing_extract_field(self, *, filing, field_spec):
        if field_spec.field_name == "tender_going_private_quant":
            return {"status": "error", "error_code": "FORCED_TEXT_FAILURE"}
        return original_extract_field(self, filing=filing, field_spec=field_spec)

    monkeypatch.setattr(provider_module.TextExtractionEngine, "extract_field", failing_extract_field)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-sc-13e3-text-failure",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("deal_value", "document")] == 9500000.0
    assert numeric_facts[("offer_price_per_share", "security:1")] == 19.0
    assert numeric_facts[("financing_commitment_amount", "document")] == 4000000.0
    assert numeric_facts[("termination_fee", "document")] == 350000.0
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert ("tender_going_private_quant", "document") not in text_facts
    assert any(log["error_type"] == "FORCED_TEXT_FAILURE" for log in repo.logs)


def test_build_bundles_from_provider_emits_s1_offering_numeric_fields(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 13, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000019",
        cik="0000789019",
        form_type="S-1",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="S-1",
            sections=[
                "Use of Proceeds\nGross proceeds of $5,000,000 are expected. Net proceeds of $4,500,000 after underwriting discounts and commissions of $500,000. The offering price per share was $10.00 with an offering of 500,000 shares of common stock. Financing commitment of $2,000,000 has been arranged."
            ],
        ),
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
        run_id="run-s1-offering",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("gross_proceeds", "document")] == 5000000.0
    assert numeric_facts[("net_proceeds", "document")] == 4500000.0
    assert numeric_facts[("underwriter_discount_total", "document")] == 500000.0
    assert numeric_facts[("offering_price_per_share", "security:1")] == 10.0
    assert numeric_facts[("securities_offered_qty", "security:1")] == 500000.0
    assert numeric_facts[("financing_commitment_amount", "document")] == 2000000.0
    evidence = {(item.field_name, item.subject_key): item for item in bundles[0].evidences}
    assert evidence[("gross_proceeds", "document")].source_section == "Use of Proceeds"
    assert evidence[("offering_price_per_share", "security:1")].source_section == "Use of Proceeds"


def test_build_bundles_from_provider_emits_s1_offering_numeric_and_risk_text(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 13, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000019F",
        cik="0000789019",
        form_type="S-1",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="S-1",
            sections=[
                "Use of Proceeds\nGross proceeds of $5,000,000 are expected. Net proceeds of $4,500,000 after underwriting discounts and commissions of $500,000. The offering price per share was $10.00 with an offering of 500,000 shares of common stock. Financing commitment of $2,000,000 has been arranged.",
                "Risk Factors\nCybersecurity incidents may materially affect our operations.",
            ],
        ),
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
        run_id="run-s1-offering-risk",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("gross_proceeds", "document")] == 5000000.0
    assert numeric_facts[("net_proceeds", "document")] == 4500000.0
    assert numeric_facts[("underwriter_discount_total", "document")] == 500000.0
    assert numeric_facts[("offering_price_per_share", "security:1")] == 10.0
    assert numeric_facts[("securities_offered_qty", "security:1")] == 500000.0
    assert numeric_facts[("financing_commitment_amount", "document")] == 2000000.0
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("risk_factor_quant", "document")] == "Cybersecurity"


def test_build_bundles_from_provider_logs_invalid_s1_offering_contract_without_blocking_row_numeric(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 13, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000019A",
        cik="0000789019",
        form_type="S-1",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="S-1",
            sections=[
                "Use of Proceeds\nGross proceeds of $5,000,000 are expected. Net proceeds of $4,500,000 after underwriting discounts and commissions of $500,000. The offering price per share was $10.00 with an offering of 500,000 shares of common stock. Financing commitment of $2,000,000 has been arranged.",
                "Summary Compensation Table\nJane Doe Total 1,250,000",
                "Beneficial Ownership Table\nAlpha Fund 500,000 shares 12.5%",
            ],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    def build_invalid_offering_bundle(*, filing, text_sections):
        del text_sections
        return FilingBundle(
            filing=filing,
            facts=[
                FactInput(
                    field_name="offering_price_per_share",
                    subject_key="document",
                    value_numeric=10.0,
                    confidence=0.99,
                )
            ],
            evidences=[
                EvidenceInput(
                    field_name="offering_price_per_share",
                    subject_key="document",
                    locator_kind="parse_text",
                    source_span="offering_text",
                    source_section="Use of Proceeds",
                    raw_value="10.0",
                    normalized_value="10.0",
                )
            ],
        )

    monkeypatch.setattr(provider_module, "_build_issuer_offering_text_facts", build_invalid_offering_bundle)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-s1-offering-invalid-contract",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("exec_total_comp", "exec:1")] == 1250000.0
    assert numeric_facts[("holder_beneficial_ownership_shares", "holder:1")] == 500000.0
    assert numeric_facts[("holder_beneficial_ownership_pct", "holder:1")] == 12.5
    assert ("offering_price_per_share", "document") not in numeric_facts
    assert any(log["error_type"] == "SPECIALIZED_SUBJECT_CONTRACT_VIOLATION" for log in repo.logs)


def test_build_bundles_from_provider_keeps_s1_offering_numeric_when_risk_text_fails(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 13, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000019G",
        cik="0000789019",
        form_type="S-1",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="S-1",
            sections=[
                "Use of Proceeds\nGross proceeds of $5,000,000 are expected. Net proceeds of $4,500,000 after underwriting discounts and commissions of $500,000. The offering price per share was $10.00 with an offering of 500,000 shares of common stock. Financing commitment of $2,000,000 has been arranged.",
                "Risk Factors\nCybersecurity incidents may materially affect our operations.",
            ],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    original_extract_field = provider_module.TextExtractionEngine.extract_field

    def failing_extract_field(self, *, filing, field_spec):
        if field_spec.field_name == "risk_factor_quant":
            return {"status": "error", "error_code": "FORCED_TEXT_FAILURE"}
        return original_extract_field(self, filing=filing, field_spec=field_spec)

    monkeypatch.setattr(provider_module.TextExtractionEngine, "extract_field", failing_extract_field)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-s1-risk-failure",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("gross_proceeds", "document")] == 5000000.0
    assert numeric_facts[("net_proceeds", "document")] == 4500000.0
    assert numeric_facts[("underwriter_discount_total", "document")] == 500000.0
    assert numeric_facts[("offering_price_per_share", "security:1")] == 10.0
    assert numeric_facts[("securities_offered_qty", "security:1")] == 500000.0
    assert numeric_facts[("financing_commitment_amount", "document")] == 2000000.0
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert ("risk_factor_quant", "document") not in text_facts
    assert any(log["error_type"] == "FORCED_TEXT_FAILURE" for log in repo.logs)


def test_build_bundles_from_provider_logs_invalid_s1_row_contract_without_blocking_offering_and_text(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 13, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000019B",
        cik="0000789019",
        form_type="S-1",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="S-1",
            sections=[
                "Use of Proceeds\nGross proceeds of $5,000,000 are expected. Net proceeds of $4,500,000 after underwriting discounts and commissions of $500,000. The offering price per share was $10.00 with an offering of 500,000 shares of common stock. Financing commitment of $2,000,000 has been arranged.",
                "CD&A\nThe company emphasizes pay for performance in executive compensation.",
            ],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    def build_invalid_row_bundle(*, filing, text_sections):
        del text_sections
        return FilingBundle(
            filing=filing,
            facts=[
                FactInput(
                    field_name="exec_total_comp",
                    subject_key="document",
                    value_numeric=1250000.0,
                    confidence=0.99,
                )
            ],
            evidences=[
                EvidenceInput(
                    field_name="exec_total_comp",
                    subject_key="document",
                    locator_kind="parse_text",
                    source_span="Jane Doe Total 1,250,000",
                    source_section="Summary Compensation Table",
                    raw_value="1250000",
                    normalized_value="1250000.0",
                )
            ],
        )

    monkeypatch.setattr(provider_module, "_build_issuer_row_numeric_text_facts", build_invalid_row_bundle)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-s1-row-invalid-contract",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("gross_proceeds", "document")] == 5000000.0
    assert numeric_facts[("net_proceeds", "document")] == 4500000.0
    assert numeric_facts[("underwriter_discount_total", "document")] == 500000.0
    assert numeric_facts[("offering_price_per_share", "security:1")] == 10.0
    assert numeric_facts[("securities_offered_qty", "security:1")] == 500000.0
    assert numeric_facts[("financing_commitment_amount", "document")] == 2000000.0
    assert ("exec_total_comp", "document") not in numeric_facts
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("comp_policy_quant", "document")] == "pay for performance"
    assert any(log["error_type"] == "SPECIALIZED_SUBJECT_CONTRACT_VIOLATION" for log in repo.logs)


def test_build_bundles_from_provider_emits_424b4_offering_numeric_and_use_of_proceeds_text(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 13, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000019C",
        cik="0000789019",
        form_type="424B4",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="424B4",
            sections=[
                "Use of Proceeds\nGross proceeds of $6,000,000 are expected. Net proceeds of $5,400,000 after underwriting discounts and commissions of $600,000. The offering price per share was $12.00 with an offering of 500,000 shares of common stock. Financing commitment of $2,500,000 has been arranged.",
                "Risk Factors\nCybersecurity incidents may materially affect our distribution and settlement process.",
            ],
        ),
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
        run_id="run-424b4-offering",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("gross_proceeds", "document")] == 6000000.0
    assert numeric_facts[("net_proceeds", "document")] == 5400000.0
    assert numeric_facts[("underwriter_discount_total", "document")] == 600000.0
    assert numeric_facts[("offering_price_per_share", "security:1")] == 12.0
    assert numeric_facts[("securities_offered_qty", "security:1")] == 500000.0
    assert numeric_facts[("financing_commitment_amount", "document")] == 2500000.0
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("risk_factor_quant", "document")] == "Cybersecurity"


def test_build_bundles_from_provider_logs_invalid_424b4_offering_contract_without_blocking_text(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 13, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000019CC",
        cik="0000789019",
        form_type="424B4",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="424B4",
            sections=[
                "Use of Proceeds\nGross proceeds of $6,000,000 are expected. Net proceeds of $5,400,000 after underwriting discounts and commissions of $600,000. The offering price per share was $12.00 with an offering of 500,000 shares of common stock. Financing commitment of $2,500,000 has been arranged.",
                "Risk Factors\nCybersecurity incidents may materially affect our distribution and settlement process.",
            ],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    def build_invalid_offering_bundle(*, filing, text_sections):
        del text_sections
        return FilingBundle(
            filing=filing,
            facts=[
                FactInput(
                    field_name="offering_price_per_share",
                    subject_key="document",
                    value_numeric=12.0,
                    confidence=0.99,
                )
            ],
            evidences=[
                EvidenceInput(
                    field_name="offering_price_per_share",
                    subject_key="document",
                    locator_kind="parse_text",
                    source_span="offering_text",
                    source_section="Use of Proceeds",
                    raw_value="12.0",
                    normalized_value="12.0",
                )
            ],
        )

    monkeypatch.setattr(provider_module, "_build_issuer_offering_text_facts", build_invalid_offering_bundle)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-424b4-offering-invalid-contract",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert ("offering_price_per_share", "document") not in numeric_facts
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("risk_factor_quant", "document")] == "Cybersecurity"
    assert any(log["error_type"] == "SPECIALIZED_SUBJECT_CONTRACT_VIOLATION" for log in repo.logs)


def test_build_bundles_from_provider_logs_invalid_424b4_row_contract_without_blocking_offering_and_text(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 13, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000019D",
        cik="0000789019",
        form_type="424B4",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="424B4",
            sections=[
                "Use of Proceeds\nGross proceeds of $6,000,000 are expected. Net proceeds of $5,400,000 after underwriting discounts and commissions of $600,000. The offering price per share was $12.00 with an offering of 500,000 shares of common stock. Financing commitment of $2,500,000 has been arranged.",
                "Risk Factors\nCybersecurity incidents may materially affect our distribution and settlement process.",
            ],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    def build_invalid_row_bundle(*, filing, text_sections):
        del text_sections
        return FilingBundle(
            filing=filing,
            facts=[
                FactInput(
                    field_name="exec_total_comp",
                    subject_key="document",
                    value_numeric=1250000.0,
                    confidence=0.99,
                )
            ],
            evidences=[
                EvidenceInput(
                    field_name="exec_total_comp",
                    subject_key="document",
                    locator_kind="parse_text",
                    source_span="Jane Doe Total 1,250,000",
                    source_section="Summary Compensation Table",
                    raw_value="1250000",
                    normalized_value="1250000.0",
                )
            ],
        )

    monkeypatch.setattr(provider_module, "_build_issuer_row_numeric_text_facts", build_invalid_row_bundle)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-424b4-row-invalid-contract",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("gross_proceeds", "document")] == 6000000.0
    assert numeric_facts[("net_proceeds", "document")] == 5400000.0
    assert numeric_facts[("underwriter_discount_total", "document")] == 600000.0
    assert numeric_facts[("offering_price_per_share", "security:1")] == 12.0
    assert numeric_facts[("securities_offered_qty", "security:1")] == 500000.0
    assert numeric_facts[("financing_commitment_amount", "document")] == 2500000.0
    assert ("exec_total_comp", "document") not in numeric_facts
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("risk_factor_quant", "document")] == "Cybersecurity"
    assert any(log["error_type"] == "SPECIALIZED_SUBJECT_CONTRACT_VIOLATION" for log in repo.logs)


def test_build_bundles_from_provider_keeps_424b4_offering_numeric_when_risk_text_fails(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 13, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000019E",
        cik="0000789019",
        form_type="424B4",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="424B4",
            sections=[
                "Use of Proceeds\nGross proceeds of $6,000,000 are expected. Net proceeds of $5,400,000 after underwriting discounts and commissions of $600,000. The offering price per share was $12.00 with an offering of 500,000 shares of common stock. Financing commitment of $2,500,000 has been arranged.",
                "Risk Factors\nCybersecurity incidents may materially affect our distribution and settlement process.",
            ],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    original_extract_field = provider_module.TextExtractionEngine.extract_field

    def failing_extract_field(self, *, filing, field_spec):
        if field_spec.field_name == "risk_factor_quant":
            return {"status": "error", "error_code": "FORCED_TEXT_FAILURE"}
        return original_extract_field(self, filing=filing, field_spec=field_spec)

    monkeypatch.setattr(provider_module.TextExtractionEngine, "extract_field", failing_extract_field)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-424b4-risk-failure",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("gross_proceeds", "document")] == 6000000.0
    assert numeric_facts[("net_proceeds", "document")] == 5400000.0
    assert numeric_facts[("underwriter_discount_total", "document")] == 600000.0
    assert numeric_facts[("offering_price_per_share", "security:1")] == 12.0
    assert numeric_facts[("securities_offered_qty", "security:1")] == 500000.0
    assert numeric_facts[("financing_commitment_amount", "document")] == 2500000.0
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert ("risk_factor_quant", "document") not in text_facts
    assert any(log["error_type"] == "FORCED_TEXT_FAILURE" for log in repo.logs)


def test_build_bundles_from_provider_emits_sc_toi_deal_numeric_fields(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 14, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000020",
        cik="0000789019",
        form_type="SC TO-I",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="SC TO-I",
            sections=[
                "Summary term sheet\nTransaction value of $12,000,000. Offer price per share was $24.00. 500,000 shares sought. Financing commitment of $8,000,000. Termination fee of $600,000."
            ],
        ),
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
        run_id="run-sc-toi-deal",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("deal_value", "document")] == 12000000.0
    assert numeric_facts[("offer_price_per_share", "security:1")] == 24.0
    assert numeric_facts[("tender_shares_sought", "security:1")] == 500000.0
    assert numeric_facts[("financing_commitment_amount", "document")] == 8000000.0
    assert numeric_facts[("termination_fee", "document")] == 600000.0
    evidence = {(item.field_name, item.subject_key): item for item in bundles[0].evidences}
    assert evidence[("deal_value", "document")].source_section == "Summary term sheet"
    assert evidence[("offer_price_per_share", "security:1")].source_section == "Summary term sheet"


def test_build_bundles_from_provider_logs_invalid_sc_toi_deal_contract_without_blocking_text(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 14, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000020A",
        cik="0000789019",
        form_type="SC TO-I",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="SC TO-I",
            sections=[
                "Summary term sheet\nThis transaction is a cash merger that the committee determined was fair. Transaction value of $12,000,000. Offer price per share was $24.00. 500,000 shares sought. Financing commitment of $8,000,000. Termination fee of $600,000."
            ],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    def build_invalid_deal_bundle(*, filing, text_sections):
        del text_sections
        return FilingBundle(
            filing=filing,
            facts=[
                FactInput(
                    field_name="offer_price_per_share",
                    subject_key="document",
                    value_numeric=24.0,
                    confidence=0.99,
                )
            ],
            evidences=[
                EvidenceInput(
                    field_name="offer_price_per_share",
                    subject_key="document",
                    locator_kind="parse_text",
                    source_span="deal_text",
                    source_section="Summary term sheet",
                    raw_value="24.0",
                    normalized_value="24.0",
                )
            ],
        )

    monkeypatch.setattr(provider_module, "_build_issuer_deal_text_facts", build_invalid_deal_bundle)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-sc-toi-invalid-deal-contract",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("tender_going_private_quant", "document")] == "cash merger"
    numeric_fields = {(fact.field_name, fact.subject_key) for fact in bundles[0].facts if fact.value_numeric is not None}
    assert ("offer_price_per_share", "document") not in numeric_fields
    assert any(log["error_type"] == "SPECIALIZED_SUBJECT_CONTRACT_VIOLATION" for log in repo.logs)


def test_build_bundles_from_provider_emits_def14a_exec_and_holder_rows(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 17, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000023",
        cik="0000789019",
        form_type="DEF 14A",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="DEF 14A",
            sections=[
                "Summary Compensation Table\nJane Doe Total 1,250,000",
                "Beneficial Ownership Table\nAlpha Fund 500,000 shares 12.5%",
            ],
        ),
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
        run_id="run-def14a-rows",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("exec_total_comp", "exec:1")] == 1250000.0
    assert numeric_facts[("holder_beneficial_ownership_shares", "holder:1")] == 500000.0
    assert numeric_facts[("holder_beneficial_ownership_pct", "holder:1")] == 12.5
    evidence = {(item.field_name, item.subject_key): item for item in bundles[0].evidences}
    assert evidence[("exec_total_comp", "exec:1")].locator_kind == "parse_text"
    assert evidence[("holder_beneficial_ownership_pct", "holder:1")].locator_kind == "parse_text"
    assert evidence[("exec_total_comp", "exec:1")].source_section == "Summary Compensation Table"
    assert evidence[("holder_beneficial_ownership_pct", "holder:1")].source_section == "Beneficial Ownership Table"


def test_build_bundles_from_provider_logs_invalid_def14a_row_contract_without_blocking_text(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 17, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000023A",
        cik="0000789019",
        form_type="DEF 14A",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="DEF 14A",
            sections=[
                "Proposal 1\nThe board recommends election of the nominee.",
                "CD&A\nThe company emphasizes pay for performance in executive compensation.",
            ],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    def build_invalid_row_bundle(*, filing, text_sections):
        del text_sections
        return FilingBundle(
            filing=filing,
            facts=[
                FactInput(
                    field_name="exec_total_comp",
                    subject_key="document",
                    value_numeric=1250000.0,
                    confidence=0.99,
                )
            ],
            evidences=[
                EvidenceInput(
                    field_name="exec_total_comp",
                    subject_key="document",
                    locator_kind="parse_text",
                    source_span="Jane Doe Total 1,250,000",
                    source_section="Summary Compensation Table",
                    raw_value="1250000",
                    normalized_value="1250000.0",
                )
            ],
        )

    monkeypatch.setattr(provider_module, "_build_issuer_row_numeric_text_facts", build_invalid_row_bundle)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-def14a-invalid-row-contract",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("proxy_proposal_quant", "document")] == "election"
    assert text_facts[("comp_policy_quant", "document")] == "pay for performance"
    numeric_fields = {(fact.field_name, fact.subject_key) for fact in bundles[0].facts if fact.value_numeric is not None}
    assert ("exec_total_comp", "document") not in numeric_fields
    assert any(log["error_type"] == "SPECIALIZED_SUBJECT_CONTRACT_VIOLATION" for log in repo.logs)


def test_build_bundles_from_provider_emits_sc_13e3_deal_numeric_fields(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 15, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000021",
        cik="0000789019",
        form_type="SC 13E3",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="SC 13E3",
            sections=[
                "Special factors\nDeal value of $9,500,000. Cash consideration per share was $19.00. Financing commitment of $4,000,000. Break-up fee of $350,000."
            ],
        ),
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
        run_id="run-sc-13e3-deal",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("deal_value", "document")] == 9500000.0
    assert numeric_facts[("offer_price_per_share", "security:1")] == 19.0
    assert numeric_facts[("financing_commitment_amount", "document")] == 4000000.0
    assert numeric_facts[("termination_fee", "document")] == 350000.0
    evidence = {(item.field_name, item.subject_key): item for item in bundles[0].evidences}
    assert evidence[("deal_value", "document")].source_section == "Special factors"


def test_build_bundles_from_provider_logs_invalid_sc_13e3_deal_contract_without_blocking_text(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 15, tzinfo=timezone.utc)
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000021A",
        cik="0000789019",
        form_type="SC 13E3",
        accepted_at=accepted_at,
        filing=FakeTextFiling(
            form="SC 13E3",
            sections=[
                "Special factors\nThis transaction is a cash merger that the committee determined was fair. Deal value of $9,500,000. Cash consideration per share was $19.00. Financing commitment of $4,000,000. Break-up fee of $350,000."
            ],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    def build_invalid_deal_bundle(*, filing, text_sections):
        del text_sections
        return FilingBundle(
            filing=filing,
            facts=[
                FactInput(
                    field_name="offer_price_per_share",
                    subject_key="document",
                    value_numeric=19.0,
                    confidence=0.99,
                )
            ],
            evidences=[
                EvidenceInput(
                    field_name="offer_price_per_share",
                    subject_key="document",
                    locator_kind="parse_text",
                    source_span="deal_text",
                    source_section="Special factors",
                    raw_value="19.0",
                    normalized_value="19.0",
                )
            ],
        )

    monkeypatch.setattr(provider_module, "_build_issuer_deal_text_facts", build_invalid_deal_bundle)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-sc-13e3-invalid-deal-contract",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("tender_going_private_quant", "document")] == "cash merger"
    numeric_fields = {(fact.field_name, fact.subject_key) for fact in bundles[0].facts if fact.value_numeric is not None}
    assert ("offer_price_per_share", "document") not in numeric_fields
    assert any(log["error_type"] == "SPECIALIZED_SUBJECT_CONTRACT_VIOLATION" for log in repo.logs)


def test_build_bundles_from_provider_emits_8k_deal_numeric_fields(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 16, tzinfo=timezone.utc)
    filing = FakeEightKFiling(
        form="8-K",
        report=FakeEightKReport(
            items=["Item 1.01"],
            item_map={"Item 1.01": "Entry into a material definitive agreement."},
        ),
        sections=[
            "Current report\nTransaction value of $7,250,000. Cash consideration per share was $14.50. Financing commitment of $3,000,000. Termination fee of $250,000."
        ],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000022",
        cik="0000789019",
        form_type="8-K",
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
        run_id="run-8k-deal",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("deal_value", "document")] == 7250000.0
    assert numeric_facts[("offer_price_per_share", "security:1")] == 14.5
    assert numeric_facts[("financing_commitment_amount", "document")] == 3000000.0
    assert numeric_facts[("termination_fee", "document")] == 250000.0
    evidence = {(item.field_name, item.subject_key): item for item in bundles[0].evidences}
    assert evidence[("deal_value", "document")].source_section == "Current report"


def test_build_bundles_from_provider_logs_invalid_8k_deal_contract_without_blocking_vote_rows(monkeypatch) -> None:
    accepted_at = datetime(2024, 5, 16, tzinfo=timezone.utc)
    filing = FakeEightKFiling(
        form="8-K",
        report=FakeEightKReport(
            items=["Item 5.07"],
            item_map={"Item 5.07": "Proposal 2024 Plan Approval 1,500,000 250,000 25 10"},
        ),
        sections=[
            "Current report\nTransaction value of $7,250,000. Cash consideration per share was $14.50. Financing commitment of $3,000,000. Termination fee of $250,000."
        ],
    )
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000022A",
        cik="0000789019",
        form_type="8-K",
        accepted_at=accepted_at,
        filing=filing,
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    def build_invalid_deal_bundle(*, filing, text_sections):
        del text_sections
        return FilingBundle(
            filing=filing,
            facts=[
                FactInput(
                    field_name="offer_price_per_share",
                    subject_key="document",
                    value_numeric=14.5,
                    confidence=0.99,
                )
            ],
            evidences=[
                EvidenceInput(
                    field_name="offer_price_per_share",
                    subject_key="document",
                    locator_kind="parse_text",
                    source_span="deal_text",
                    source_section="Current report",
                    raw_value="14.5",
                    normalized_value="14.5",
                )
            ],
        )

    monkeypatch.setattr(provider_module, "_build_issuer_deal_text_facts", build_invalid_deal_bundle)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-8k-invalid-deal-contract",
    )

    assert len(bundles) == 1
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_facts[("proposal_votes_for", "proposal:1")] == 1500000.0
    assert numeric_facts[("proposal_votes_against", "proposal:1")] == 250000.0
    assert numeric_facts[("proposal_votes_abstain", "proposal:1")] == 25.0
    assert numeric_facts[("proposal_broker_non_votes", "proposal:1")] == 10.0
    assert ("offer_price_per_share", "document") not in numeric_facts
    assert any(log["error_type"] == "SPECIALIZED_SUBJECT_CONTRACT_VIOLATION" for log in repo.logs)
