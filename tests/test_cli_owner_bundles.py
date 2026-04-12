from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pandas as pd
import src.cli as cli_module
import src.pipeline.extraction.provider as provider_module
from src.pipeline.edgar_provider import FilingEnvelope, classify_form_family
from src.pipeline.route_runtime import BundleBuildOutcome, FilingBundle
from src.pipeline.services import EvidenceInput, FactInput


class FakeTransaction:
    def __init__(self, *, shares: float, price_per_share: float, shares_owned_following_transaction: float):
        self.shares = shares
        self.price_per_share = price_per_share
        self.shares_owned_following_transaction = shares_owned_following_transaction


class FakeDerivativeTransactions:
    def __init__(self, rows: list[dict[str, object]]):
        self.data = pd.DataFrame(rows)


class FakeDerivativeHoldings:
    def __init__(self, rows: list[dict[str, object]]):
        self.data = pd.DataFrame(rows)


class FakeDerivativeTable:
    def __init__(self, rows: list[dict[str, object]], holding_rows: list[dict[str, object]] | None = None):
        self.transactions = FakeDerivativeTransactions(rows)
        self.holdings = FakeDerivativeHoldings(holding_rows or [])


class FakeNonDerivativeHoldings:
    def __init__(self, rows: list[dict[str, object]]):
        self.data = pd.DataFrame(rows)


class FakeNonDerivativeTable:
    def __init__(self, holding_rows: list[dict[str, object]] | None = None):
        self.holdings = FakeNonDerivativeHoldings(holding_rows or [])


class FakeForm4:
    def __init__(self, transactions: list[FakeTransaction], derivative_rows: list[dict[str, object]] | None = None, non_derivative_holding_rows: list[dict[str, object]] | None = None, derivative_holding_rows: list[dict[str, object]] | None = None):
        self.transactions = transactions
        self.non_derivative_table = FakeNonDerivativeTable(non_derivative_holding_rows)
        self.derivative_table = FakeDerivativeTable(derivative_rows or [], derivative_holding_rows)


class FakeForm4Filing:
    def __init__(self, transactions: list[FakeTransaction], derivative_rows: list[dict[str, object]] | None = None, non_derivative_holding_rows: list[dict[str, object]] | None = None, derivative_holding_rows: list[dict[str, object]] | None = None, form: str = "4", sections: list[str] | None = None):
        self.form = form
        self._form4 = FakeForm4(transactions, derivative_rows, non_derivative_holding_rows, derivative_holding_rows)
        self._sections = sections or []

    def obj(self) -> FakeForm4:
        return self._form4

    def sections(self) -> list[str]:
        return self._sections


class FakeRepo:
    def __init__(self) -> None:
        self.logs: list[dict[str, object]] = []

    def write_log(self, **kwargs: object) -> None:
        self.logs.append(dict(kwargs))


class FakeXmlFiling:
    def __init__(self, *, form: str, xml_text: str, sections: list[str] | None = None):
        self.form = form
        self._xml_text = xml_text
        self._sections = sections or []

    def xml(self) -> str:
        return self._xml_text

    def sections(self) -> list[str]:
        return self._sections


class FakeForm144Filing:
    def __init__(self, *, form: str, securities_information: list[dict[str, object]], securities_sold_past_3_months: list[dict[str, object]], sections: list[str] | None = None):
        self.form = form
        self._form144 = SimpleNamespace(
            securities_information=pd.DataFrame(securities_information),
            securities_sold_past_3_months=pd.DataFrame(securities_sold_past_3_months),
        )
        self._sections = sections or []

    def obj(self) -> SimpleNamespace:
        return self._form144

    def sections(self) -> list[str]:
        return self._sections


def test_build_bundles_from_provider_emits_form4_transaction_rows(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000100",
        cik="0000789019",
        form_type="4",
        accepted_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
        filing=FakeForm4Filing(
            [
                FakeTransaction(shares=100.0, price_per_share=10.5, shares_owned_following_transaction=1000.0),
                FakeTransaction(shares=-50.0, price_per_share=11.0, shares_owned_following_transaction=950.0),
            ],
            [
                {"UnderlyingShares": 500.0, "ExercisePrice": 7.5},
                {"UnderlyingShares": 250.0, "ExercisePrice": 6.25},
            ],
            sections=["Remarks\nThe reporting person is a director and this was a buy transaction."],
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
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-1",
    )

    assert len(bundles) == 1
    bundle = bundles[0]
    facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundle.facts}
    assert facts[("shares_acquired_or_disposed", "txn:1")] == 100.0
    assert facts[("shares_acquired_or_disposed", "txn:2")] == -50.0
    assert facts[("transaction_price_per_share", "txn:1")] == 10.5
    assert facts[("transaction_price_per_share", "txn:2")] == 11.0
    assert facts[("shares_owned_following_txn", "txn:1")] == 1000.0
    assert facts[("shares_owned_following_txn", "txn:2")] == 950.0
    assert facts[("derivative_underlying_shares", "dtxn:1")] == 500.0
    assert facts[("derivative_underlying_shares", "dtxn:2")] == 250.0
    assert facts[("exercise_or_conversion_price", "dtxn:1")] == 7.5
    assert facts[("exercise_or_conversion_price", "dtxn:2")] == 6.25
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundle.facts if fact.value_text is not None}
    assert text_facts[("insider_transaction_quant", "document")] == "buy"
    assert text_facts[("insider_role_ownership_structure_quant", "document")] == "director"
    json_facts = {(fact.field_name, fact.subject_key): fact.value_json for fact in bundle.facts if fact.value_json is not None}
    assert json.loads(json_facts[("insider_transaction_quant", "document")])["transaction_type"] == "purchase"
    assert json.loads(json_facts[("insider_role_ownership_structure_quant", "document")])["is_director"] is True

    evidence_keys = {(e.field_name, e.subject_key) for e in bundle.evidences}
    assert ("transaction_price_per_share", "txn:1") in evidence_keys
    assert ("shares_owned_following_txn", "txn:2") in evidence_keys
    assert ("derivative_underlying_shares", "dtxn:1") in evidence_keys
    assert ("exercise_or_conversion_price", "dtxn:2") in evidence_keys
    assert repo.logs == []


def test_build_bundles_from_provider_emits_form5_transaction_rows(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000100E",
        cik="0000789019",
        form_type="5",
        accepted_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
        filing=FakeForm4Filing(
            [
                FakeTransaction(shares=75.0, price_per_share=9.5, shares_owned_following_transaction=1075.0),
            ],
            [
                {"UnderlyingShares": 125.0, "ExercisePrice": 8.0},
            ],
            sections=["Remarks\nThe reporting person is a director and this was a buy transaction."],
            form="5",
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
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-1b",
    )

    assert len(bundles) == 1
    bundle = bundles[0]
    facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundle.facts}
    assert facts[("shares_acquired_or_disposed", "txn:1")] == 75.0
    assert facts[("transaction_price_per_share", "txn:1")] == 9.5
    assert facts[("shares_owned_following_txn", "txn:1")] == 1075.0
    assert facts[("derivative_underlying_shares", "dtxn:1")] == 125.0
    assert facts[("exercise_or_conversion_price", "dtxn:1")] == 8.0
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundle.facts if fact.value_text is not None}
    assert text_facts[("insider_transaction_quant", "document")] == "buy"
    assert text_facts[("insider_role_ownership_structure_quant", "document")] == "director"
    assert repo.logs == []


def test_build_bundles_from_provider_keeps_form5_numeric_when_text_field_extraction_fails(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000100F",
        cik="0000789019",
        form_type="5",
        accepted_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
        filing=FakeForm4Filing(
            [
                FakeTransaction(shares=75.0, price_per_share=9.5, shares_owned_following_transaction=1075.0),
            ],
            [
                {"UnderlyingShares": 125.0, "ExercisePrice": 8.0},
            ],
            sections=["Remarks\nThe reporting person is a director and this was a buy transaction."],
            form="5",
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    original_extract_field = provider_module.TextExtractionEngine.extract_field

    def failing_extract_field(self, *, filing, field_spec):
        if field_spec.field_name == "insider_transaction_quant":
            return {"status": "error", "error_code": "FORCED_TEXT_FAILURE"}
        return original_extract_field(self, filing=filing, field_spec=field_spec)

    monkeypatch.setattr(provider_module.TextExtractionEngine, "extract_field", failing_extract_field)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-1c",
    )

    assert len(bundles) == 1
    bundle = bundles[0]
    facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundle.facts if fact.value_numeric is not None}
    assert facts[("shares_acquired_or_disposed", "txn:1")] == 75.0
    assert facts[("transaction_price_per_share", "txn:1")] == 9.5
    assert facts[("shares_owned_following_txn", "txn:1")] == 1075.0
    assert facts[("derivative_underlying_shares", "dtxn:1")] == 125.0
    assert facts[("exercise_or_conversion_price", "dtxn:1")] == 8.0
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundle.facts if fact.value_text is not None}
    assert ("insider_transaction_quant", "document") not in text_facts
    assert text_facts[("insider_role_ownership_structure_quant", "document")] == "director"
    assert any(log["error_type"] == "FORCED_TEXT_FAILURE" for log in repo.logs)


def test_build_bundles_from_provider_keeps_form4_numeric_when_text_field_extraction_fails(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000100D",
        cik="0000789019",
        form_type="4",
        accepted_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
        filing=FakeForm4Filing(
            [
                FakeTransaction(shares=100.0, price_per_share=10.5, shares_owned_following_transaction=1000.0),
                FakeTransaction(shares=-50.0, price_per_share=11.0, shares_owned_following_transaction=950.0),
            ],
            [
                {"UnderlyingShares": 500.0, "ExercisePrice": 7.5},
                {"UnderlyingShares": 250.0, "ExercisePrice": 6.25},
            ],
            sections=["Remarks\nThe reporting person is a director and this was a buy transaction."],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    original_extract_field = provider_module.TextExtractionEngine.extract_field

    def failing_extract_field(self, *, filing, field_spec):
        if field_spec.field_name == "insider_transaction_quant":
            return {"status": "error", "error_code": "FORCED_TEXT_FAILURE"}
        return original_extract_field(self, filing=filing, field_spec=field_spec)

    monkeypatch.setattr(provider_module.TextExtractionEngine, "extract_field", failing_extract_field)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-form4-text-failure",
    )

    assert len(bundles) == 1
    bundle = bundles[0]
    facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundle.facts if fact.value_numeric is not None}
    assert facts[("shares_acquired_or_disposed", "txn:1")] == 100.0
    assert facts[("transaction_price_per_share", "txn:2")] == 11.0
    assert facts[("derivative_underlying_shares", "dtxn:1")] == 500.0
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundle.facts if fact.value_text is not None}
    assert ("insider_transaction_quant", "document") not in text_facts
    assert text_facts[("insider_role_ownership_structure_quant", "document")] == "director"
    assert any(log["error_type"] == "FORCED_TEXT_FAILURE" for log in repo.logs)


def test_build_bundles_from_provider_rejects_owner_bundle_with_invalid_subject_contract(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000100A",
        cik="0000789019",
        form_type="4",
        accepted_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
        filing=FakeForm4Filing(
            [],
            sections=["Remarks\nThe reporting person is a director and this was a buy transaction."],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    def build_invalid_owner_bundle(*, envelope, filing):
        del envelope
        return BundleBuildOutcome(
            bundle=FilingBundle(
                filing=filing,
                facts=[
                    FactInput(
                        field_name="shares_acquired_or_disposed",
                        subject_key="document",
                        value_numeric=100.0,
                        confidence=0.99,
                    )
                ],
                evidences=[
                    EvidenceInput(
                        field_name="shares_acquired_or_disposed",
                        subject_key="document",
                        locator_kind="obj",
                        source_span="transactions[0].shares",
                        raw_value="100",
                        normalized_value="100.0",
                    )
                ],
            )
        )

    monkeypatch.setattr(provider_module, "build_owner_ownership_bundle", build_invalid_owner_bundle)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-invalid-ownership",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("insider_transaction_quant", "document")] == "buy"
    assert text_facts[("insider_role_ownership_structure_quant", "document")] == "director"
    numeric_fields = {(fact.field_name, fact.subject_key) for fact in bundles[0].facts if fact.value_numeric is not None}
    assert ("shares_acquired_or_disposed", "document") not in numeric_fields
    assert repo.logs[-1]["error_type"] == "SPECIALIZED_SUBJECT_CONTRACT_VIOLATION"
    assert "shares_acquired_or_disposed:document" in str(repo.logs[-1]["error_detail"])


def test_build_bundles_from_provider_preserves_form4_text_when_obj_bundle_unavailable(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000100B",
        cik="0000789019",
        form_type="4",
        accepted_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
        filing=FakeForm4Filing(
            [],
            sections=["Remarks\nThe reporting person is a director and this was a buy transaction."],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    def fail_owner_bundle(*, envelope, filing):
        del envelope, filing
        return BundleBuildOutcome(bundle=None, error_detail="mock form4 obj failure")

    monkeypatch.setattr(provider_module, "build_owner_ownership_bundle", fail_owner_bundle)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-invalid-unavailable",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("insider_transaction_quant", "document")] == "buy"
    assert text_facts[("insider_role_ownership_structure_quant", "document")] == "director"
    numeric_fields = {(fact.field_name, fact.subject_key) for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_fields == set()
    assert repo.logs[-1]["error_type"] == "OWNERSHIP_OBJ_UNAVAILABLE"


def test_build_bundles_from_provider_preserves_form4_text_when_bundle_has_no_rows(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000100C",
        cik="0000789019",
        form_type="4",
        accepted_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
        filing=FakeForm4Filing(
            [],
            sections=["Remarks\nThe reporting person is a director and this was a buy transaction."],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    def empty_owner_bundle(*, envelope, filing):
        del envelope
        return BundleBuildOutcome(
            bundle=FilingBundle(
                filing=filing,
                facts=[],
                evidences=[],
            )
        )

    monkeypatch.setattr(provider_module, "build_owner_ownership_bundle", empty_owner_bundle)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-empty-form4",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("insider_transaction_quant", "document")] == "buy"
    assert text_facts[("insider_role_ownership_structure_quant", "document")] == "director"
    numeric_fields = {(fact.field_name, fact.subject_key) for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_fields == set()
    assert repo.logs[-1]["error_type"] == "NO_OWNER_ROWS_EXTRACTED"


def test_build_bundles_from_provider_emits_owner_holding_rows(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000101",
        cik="0000789019",
        form_type="3",
        accepted_at=datetime(2024, 5, 2, tzinfo=timezone.utc),
        filing=FakeForm4Filing(
            transactions=[],
            non_derivative_holding_rows=[
                {"Shares": 1500.0},
                {"Shares": 2000.0},
            ],
            derivative_holding_rows=[
                {"UnderlyingShares": 300.0, "ExercisePrice": 4.5},
                {"UnderlyingShares": 450.0, "ExercisePrice": 5.25},
            ],
            form="3",
            sections=["Remarks\nThe reporting person is a director and holds shares directly."],
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
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-2",
    )

    assert len(bundles) == 1
    bundle = bundles[0]
    facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundle.facts}
    assert facts[("non_derivative_shares_owned", "nhold:1")] == 1500.0
    assert facts[("non_derivative_shares_owned", "nhold:2")] == 2000.0
    assert facts[("derivative_underlying_shares", "dhold:1")] == 300.0
    assert facts[("derivative_underlying_shares", "dhold:2")] == 450.0
    assert facts[("exercise_or_conversion_price", "dhold:1")] == 4.5
    assert facts[("exercise_or_conversion_price", "dhold:2")] == 5.25
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundle.facts if fact.value_text is not None}
    assert text_facts[("insider_role_ownership_structure_quant", "document")] == "director"

    evidence_keys = {(e.field_name, e.subject_key) for e in bundle.evidences}
    assert ("non_derivative_shares_owned", "nhold:1") in evidence_keys
    assert ("derivative_underlying_shares", "dhold:2") in evidence_keys
    assert ("exercise_or_conversion_price", "dhold:1") in evidence_keys
    assert repo.logs == []


def test_build_bundles_from_provider_keeps_form3_numeric_when_text_field_extraction_fails(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000101A",
        cik="0000789019",
        form_type="3",
        accepted_at=datetime(2024, 5, 2, tzinfo=timezone.utc),
        filing=FakeForm4Filing(
            transactions=[],
            non_derivative_holding_rows=[
                {"Shares": 1500.0},
            ],
            derivative_holding_rows=[
                {"UnderlyingShares": 300.0, "ExercisePrice": 4.5},
            ],
            form="3",
            sections=["Remarks\nThe reporting person is a director and holds shares directly."],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    original_extract_field = provider_module.TextExtractionEngine.extract_field

    def failing_extract_field(self, *, filing, field_spec):
        if field_spec.field_name == "insider_role_ownership_structure_quant":
            return {"status": "error", "error_code": "FORCED_TEXT_FAILURE"}
        return original_extract_field(self, filing=filing, field_spec=field_spec)

    monkeypatch.setattr(provider_module.TextExtractionEngine, "extract_field", failing_extract_field)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0000789019", ticker="MSFT")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-form3-text-failure",
    )

    assert len(bundles) == 1
    bundle = bundles[0]
    facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundle.facts if fact.value_numeric is not None}
    assert facts[("non_derivative_shares_owned", "nhold:1")] == 1500.0
    assert facts[("derivative_underlying_shares", "dhold:1")] == 300.0
    assert facts[("exercise_or_conversion_price", "dhold:1")] == 4.5
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundle.facts if fact.value_text is not None}
    assert ("insider_role_ownership_structure_quant", "document") not in text_facts
    assert any(log["error_type"] == "FORCED_TEXT_FAILURE" for log in repo.logs)


def test_build_bundles_from_provider_emits_13g_owner_rows(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000102",
        cik="0001067983",
        form_type="SC 13G",
        accepted_at=datetime(2024, 5, 3, tzinfo=timezone.utc),
        filing=FakeXmlFiling(
            form="SC 13G",
            xml_text="""
<submission>
  <coverPageHeaderReportingPersonDetails>
    <reportingPersonBeneficiallyOwnedAggregateNumberOfShares>1234567</reportingPersonBeneficiallyOwnedAggregateNumberOfShares>
    <classPercent>7.5</classPercent>
    <soleVotingPower>1200000</soleVotingPower>
    <sharedVotingPower>34567</sharedVotingPower>
    <soleDispositivePower>1100000</soleDispositivePower>
    <sharedDispositivePower>14567</sharedDispositivePower>
  </coverPageHeaderReportingPersonDetails>
</submission>
""",
            sections=["Purpose of Transaction\nThis filing is passive."],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    repo = FakeRepo()
    security = SimpleNamespace(cik="0001067983", ticker="BRK")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-3",
    )

    assert len(bundles) == 1
    bundle = bundles[0]
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundle.facts}
    assert numeric_facts[("beneficially_owned_shares", "filer:1")] == 1234567.0
    assert numeric_facts[("beneficial_ownership_pct", "filer:1")] == 7.5
    assert numeric_facts[("sole_voting_power", "filer:1")] == 1200000.0
    assert numeric_facts[("shared_voting_power", "filer:1")] == 34567.0
    assert numeric_facts[("sole_dispositive_power", "filer:1")] == 1100000.0
    assert numeric_facts[("shared_dispositive_power", "filer:1")] == 14567.0
    numeric_fact_keys = [(fact.field_name, fact.subject_key) for fact in bundle.facts if fact.value_numeric is not None]
    assert len(numeric_fact_keys) == len(set(numeric_fact_keys))
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundle.facts if fact.value_text is not None}
    assert text_facts[("beneficial_ownership_intent_quant", "document")] == "passive"
    json_facts = {(fact.field_name, fact.subject_key): fact.value_json for fact in bundle.facts if fact.value_json is not None}
    assert json.loads(json_facts[("beneficial_ownership_intent_quant", "document")])["stance"] == "passive"
    assert repo.logs == []


def test_build_bundles_from_provider_keeps_13g_schedule_numeric_when_text_field_extraction_fails(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000102D",
        cik="0001067983",
        form_type="SC 13G",
        accepted_at=datetime(2024, 5, 3, tzinfo=timezone.utc),
        filing=FakeXmlFiling(
            form="SC 13G",
            xml_text="""
<submission>
  <coverPageHeaderReportingPersonDetails>
    <reportingPersonBeneficiallyOwnedAggregateNumberOfShares>1234567</reportingPersonBeneficiallyOwnedAggregateNumberOfShares>
    <classPercent>7.5</classPercent>
    <soleVotingPower>1200000</soleVotingPower>
    <sharedVotingPower>34567</sharedVotingPower>
    <soleDispositivePower>1100000</soleDispositivePower>
    <sharedDispositivePower>14567</sharedDispositivePower>
  </coverPageHeaderReportingPersonDetails>
</submission>
""",
            sections=["Purpose of Transaction\nThis filing is passive."],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    original_extract_field = provider_module.TextExtractionEngine.extract_field

    def failing_extract_field(self, *, filing, field_spec):
        if field_spec.field_name == "beneficial_ownership_intent_quant":
            return {"status": "error", "error_code": "FORCED_TEXT_FAILURE"}
        return original_extract_field(self, filing=filing, field_spec=field_spec)

    monkeypatch.setattr(provider_module.TextExtractionEngine, "extract_field", failing_extract_field)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0001067983", ticker="BRK")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-13g-text-failure",
    )

    assert len(bundles) == 1
    bundle = bundles[0]
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundle.facts}
    assert numeric_facts[("beneficially_owned_shares", "filer:1")] == 1234567.0
    assert numeric_facts[("beneficial_ownership_pct", "filer:1")] == 7.5
    assert numeric_facts[("sole_voting_power", "filer:1")] == 1200000.0
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundle.facts if fact.value_text is not None}
    assert ("beneficial_ownership_intent_quant", "document") not in text_facts
    assert any(log["error_type"] == "FORCED_TEXT_FAILURE" for log in repo.logs)


def test_build_bundles_from_provider_rejects_schedule_bundle_with_invalid_subject_contract(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000102A",
        cik="0001067983",
        form_type="SC 13G",
        accepted_at=datetime(2024, 5, 3, tzinfo=timezone.utc),
        filing=FakeXmlFiling(
            form="SC 13G",
            xml_text="<submission />",
            sections=["Purpose of Transaction\nThis filing is passive."],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    def build_invalid_schedule_bundle(*, envelope, filing, form_family):
        del envelope, form_family
        return BundleBuildOutcome(
            bundle=FilingBundle(
                filing=filing,
                facts=[
                    FactInput(
                        field_name="beneficially_owned_shares",
                        subject_key="document",
                        value_numeric=1234567.0,
                        confidence=0.99,
                    )
                ],
                evidences=[
                    EvidenceInput(
                        field_name="beneficially_owned_shares",
                        subject_key="document",
                        locator_kind="obj",
                        source_span="xml.reportingPerson[0].aggregateAmountOwned",
                        raw_value="1234567",
                        normalized_value="1234567.0",
                    )
                ],
            )
        )

    monkeypatch.setattr(provider_module, "build_owner_schedule_13dg_bundle", build_invalid_schedule_bundle)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0001067983", ticker="BRK")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-invalid-13g",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("beneficial_ownership_intent_quant", "document")] == "passive"
    numeric_fields = {(fact.field_name, fact.subject_key) for fact in bundles[0].facts if fact.value_numeric is not None}
    assert ("beneficially_owned_shares", "document") not in numeric_fields
    assert repo.logs[-1]["error_type"] == "SPECIALIZED_SUBJECT_CONTRACT_VIOLATION"
    assert "beneficially_owned_shares:document" in str(repo.logs[-1]["error_detail"])


def test_build_bundles_from_provider_preserves_13d_text_when_schedule_bundle_violates_subject_contract(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000103D",
        cik="0001326380",
        form_type="SCHEDULE 13D/A",
        accepted_at=datetime(2024, 5, 4, tzinfo=timezone.utc),
        filing=FakeXmlFiling(
            form="SCHEDULE 13D/A",
            xml_text="<submission />",
            sections=[
                "Purpose of Transaction\nThis filer is activist.",
                "Item 3 Source and Amount of Funds\nCash on hand was used for the purchases.",
            ],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    def invalid_schedule_bundle(*, envelope, filing, form_family):
        del envelope, form_family
        return BundleBuildOutcome(
            bundle=FilingBundle(
                filing=filing,
                facts=[
                    FactInput(
                        field_name="beneficially_owned_shares",
                        subject_key="document",
                        value_numeric=400000.0,
                        confidence=0.99,
                    )
                ],
                evidences=[
                    EvidenceInput(
                        field_name="beneficially_owned_shares",
                        subject_key="document",
                        locator_kind="obj",
                        source_span="xml.reportingPerson[0].aggregateAmountOwned",
                        raw_value="400000",
                        normalized_value="400000.0",
                    )
                ],
            )
        )

    monkeypatch.setattr(provider_module, "build_owner_schedule_13dg_bundle", invalid_schedule_bundle)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0001326380", ticker="XYZ")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-invalid-13d-contract",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("beneficial_ownership_intent_quant", "document")] == "activist"
    assert text_facts[("source_of_funds_quant", "document")] == "Cash"
    json_facts = {(fact.field_name, fact.subject_key): fact.value_json for fact in bundles[0].facts if fact.value_json is not None}
    assert json.loads(json_facts[("source_of_funds_quant", "document")])["cash_pct"] == 100
    numeric_fields = {(fact.field_name, fact.subject_key) for fact in bundles[0].facts if fact.value_numeric is not None}
    assert ("beneficially_owned_shares", "document") not in numeric_fields
    assert repo.logs[-1]["error_type"] == "SPECIALIZED_SUBJECT_CONTRACT_VIOLATION"


def test_build_bundles_from_provider_preserves_schedule_text_when_xml_bundle_unavailable(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000102B",
        cik="0001067983",
        form_type="SC 13G",
        accepted_at=datetime(2024, 5, 3, tzinfo=timezone.utc),
        filing=FakeXmlFiling(
            form="SC 13G",
            xml_text="<submission />",
            sections=["Purpose of Transaction\nThis filing is passive."],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    def fail_schedule_bundle(*, envelope, filing, form_family):
        del envelope, filing, form_family
        return BundleBuildOutcome(bundle=None, error_detail="mock 13G xml failure")

    monkeypatch.setattr(provider_module, "build_owner_schedule_13dg_bundle", fail_schedule_bundle)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0001067983", ticker="BRK")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-invalid-13g-xml",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("beneficial_ownership_intent_quant", "document")] == "passive"
    numeric_fields = {(fact.field_name, fact.subject_key) for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_fields == set()
    assert repo.logs[-1]["error_type"] == "OWNER_XML_UNAVAILABLE"


def test_build_bundles_from_provider_preserves_13g_text_when_schedule_bundle_has_no_rows(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000102C",
        cik="0001067983",
        form_type="SC 13G",
        accepted_at=datetime(2024, 5, 3, tzinfo=timezone.utc),
        filing=FakeXmlFiling(
            form="SC 13G",
            xml_text="<submission />",
            sections=["Purpose of Transaction\nThis filing is passive."],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    def empty_schedule_bundle(*, envelope, filing, form_family):
        del envelope, form_family
        return BundleBuildOutcome(
            bundle=FilingBundle(
                filing=filing,
                facts=[],
                evidences=[],
            )
        )

    monkeypatch.setattr(provider_module, "build_owner_schedule_13dg_bundle", empty_schedule_bundle)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0001067983", ticker="BRK")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-empty-13g",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("beneficial_ownership_intent_quant", "document")] == "passive"
    numeric_fields = {(fact.field_name, fact.subject_key) for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_fields == set()
    assert repo.logs[-1]["error_type"] == "NO_OWNER_ROWS_EXTRACTED"


def test_build_bundles_from_provider_preserves_13d_text_when_xml_bundle_unavailable(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000103B",
        cik="0001326380",
        form_type="SCHEDULE 13D/A",
        accepted_at=datetime(2024, 5, 4, tzinfo=timezone.utc),
        filing=FakeXmlFiling(
            form="SCHEDULE 13D/A",
            xml_text="<submission />",
            sections=[
                "Purpose of Transaction\nThis filer is activist.",
                "Item 3 Source and Amount of Funds\nCash on hand was used for the purchases.",
            ],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    def fail_schedule_bundle(*, envelope, filing, form_family):
        del envelope, filing, form_family
        return BundleBuildOutcome(bundle=None, error_detail="mock 13D xml failure")

    monkeypatch.setattr(provider_module, "build_owner_schedule_13dg_bundle", fail_schedule_bundle)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0001326380", ticker="XYZ")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-invalid-13d-xml",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("beneficial_ownership_intent_quant", "document")] == "activist"
    assert text_facts[("source_of_funds_quant", "document")] == "Cash"
    numeric_fields = {(fact.field_name, fact.subject_key) for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_fields == set()
    assert repo.logs[-1]["error_type"] == "OWNER_XML_UNAVAILABLE"


def test_build_bundles_from_provider_preserves_13d_text_when_schedule_bundle_has_no_rows(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000103C",
        cik="0001326380",
        form_type="SCHEDULE 13D/A",
        accepted_at=datetime(2024, 5, 4, tzinfo=timezone.utc),
        filing=FakeXmlFiling(
            form="SCHEDULE 13D/A",
            xml_text="<submission />",
            sections=[
                "Purpose of Transaction\nThis filer is activist.",
                "Item 3 Source and Amount of Funds\nCash on hand was used for the purchases.",
            ],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    def empty_schedule_bundle(*, envelope, filing, form_family):
        del envelope, form_family
        return BundleBuildOutcome(
            bundle=FilingBundle(
                filing=filing,
                facts=[],
                evidences=[],
            )
        )

    monkeypatch.setattr(provider_module, "build_owner_schedule_13dg_bundle", empty_schedule_bundle)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0001326380", ticker="XYZ")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-empty-13d-xml",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("beneficial_ownership_intent_quant", "document")] == "activist"
    assert text_facts[("source_of_funds_quant", "document")] == "Cash"
    numeric_fields = {(fact.field_name, fact.subject_key) for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_fields == set()
    assert repo.logs[-1]["error_type"] == "NO_OWNER_ROWS_EXTRACTED"


def test_build_bundles_from_provider_emits_13d_owner_rows_and_funds(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000103",
        cik="0001326380",
        form_type="SCHEDULE 13D/A",
        accepted_at=datetime(2024, 5, 4, tzinfo=timezone.utc),
        filing=FakeXmlFiling(
            form="SCHEDULE 13D/A",
            xml_text="""
<submission>
  <fundsSource>Item 3. Source and Amount of Funds. Total funds used was $2,500,000 in cash.</fundsSource>
  <reportingPerson>
    <aggregateAmountOwned>400000</aggregateAmountOwned>
    <percentOfClass>9.9</percentOfClass>
    <soleVotingPower>390000</soleVotingPower>
    <sharedVotingPower>10000</sharedVotingPower>
    <soleDispositivePower>380000</soleDispositivePower>
    <sharedDispositivePower>20000</sharedDispositivePower>
    <fundsSource>Item 3. Reporting person used $1,250,000 of working capital.</fundsSource>
  </reportingPerson>
  <reportingPerson>
    <aggregateAmountOwned>100000</aggregateAmountOwned>
    <percentOfClass>2.5</percentOfClass>
    <soleVotingPower>100000</soleVotingPower>
    <sharedVotingPower>0</sharedVotingPower>
    <soleDispositivePower>100000</soleDispositivePower>
    <sharedDispositivePower>0</sharedDispositivePower>
    <fundsSource>$950,000 in cash contributed by affiliates.</fundsSource>
  </reportingPerson>
</submission>
""",
            sections=[
                "Purpose of Transaction\nThis filer is activist.",
                "Item 3 Source and Amount of Funds\nCash on hand was used for the purchases.",
            ],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    repo = FakeRepo()
    security = SimpleNamespace(cik="0001326380", ticker="XYZ")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-4",
    )

    assert len(bundles) == 1
    bundle = bundles[0]
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundle.facts}
    assert numeric_facts[("beneficially_owned_shares", "filer:1")] == 400000.0
    assert numeric_facts[("beneficial_ownership_pct", "filer:1")] == 9.9
    assert numeric_facts[("source_of_funds_amount", "filer:1")] == 1250000.0
    assert numeric_facts[("source_of_funds_amount", "filer:2")] == 950000.0
    assert numeric_facts[("aggregate_purchase_price", "filer:1")] == 1250000.0
    assert numeric_facts[("aggregate_purchase_price", "filer:2")] == 950000.0
    assert ("aggregate_purchase_price", "document") not in numeric_facts
    numeric_fact_keys = [(fact.field_name, fact.subject_key) for fact in bundle.facts if fact.value_numeric is not None]
    assert len(numeric_fact_keys) == len(set(numeric_fact_keys))
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundle.facts if fact.value_text is not None}
    assert text_facts[("beneficial_ownership_intent_quant", "document")] == "activist"
    assert text_facts[("source_of_funds_quant", "document")] == "Cash"
    assert repo.logs == []


def test_build_bundles_from_provider_keeps_13d_schedule_numeric_when_text_field_extraction_fails(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000103E",
        cik="0001326380",
        form_type="SCHEDULE 13D/A",
        accepted_at=datetime(2024, 5, 4, tzinfo=timezone.utc),
        filing=FakeXmlFiling(
            form="SCHEDULE 13D/A",
            xml_text="""
<submission>
  <fundsSource>Item 3. Source and Amount of Funds. Total funds used was $2,500,000 in cash.</fundsSource>
  <reportingPerson>
    <aggregateAmountOwned>400000</aggregateAmountOwned>
    <percentOfClass>9.9</percentOfClass>
    <soleVotingPower>390000</soleVotingPower>
    <sharedVotingPower>10000</sharedVotingPower>
    <soleDispositivePower>380000</soleDispositivePower>
    <sharedDispositivePower>20000</sharedDispositivePower>
    <fundsSource>Item 3. Reporting person used $1,250,000 of working capital.</fundsSource>
  </reportingPerson>
</submission>
""",
            sections=[
                "Purpose of Transaction\nThis filer is activist.",
                "Item 3 Source and Amount of Funds\nCash on hand was used for the purchases.",
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
        if field_spec.field_name == "beneficial_ownership_intent_quant":
            return {"status": "error", "error_code": "FORCED_TEXT_FAILURE"}
        return original_extract_field(self, filing=filing, field_spec=field_spec)

    monkeypatch.setattr(provider_module.TextExtractionEngine, "extract_field", failing_extract_field)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0001326380", ticker="XYZ")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-13d-text-failure",
    )

    assert len(bundles) == 1
    bundle = bundles[0]
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundle.facts}
    assert numeric_facts[("beneficially_owned_shares", "filer:1")] == 400000.0
    assert numeric_facts[("source_of_funds_amount", "filer:1")] == 1250000.0
    assert numeric_facts[("aggregate_purchase_price", "filer:1")] == 1250000.0
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundle.facts if fact.value_text is not None}
    assert ("beneficial_ownership_intent_quant", "document") not in text_facts
    assert text_facts[("source_of_funds_quant", "document")] == "Cash"
    assert any(log["error_type"] == "FORCED_TEXT_FAILURE" for log in repo.logs)


def test_build_bundles_from_provider_uses_single_filer_top_level_funds_fallback(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000103A",
        cik="0001326380",
        form_type="SCHEDULE 13D",
        accepted_at=datetime(2024, 5, 4, tzinfo=timezone.utc),
        filing=FakeXmlFiling(
            form="SCHEDULE 13D",
            xml_text="""
<submission>
  <fundsSource>Item 3. Source and Amount of Funds. Total funds used was $3,500,000 in cash.</fundsSource>
  <reportingPerson>
    <aggregateAmountOwned>450000</aggregateAmountOwned>
    <percentOfClass>11.1</percentOfClass>
    <soleVotingPower>450000</soleVotingPower>
    <sharedVotingPower>0</sharedVotingPower>
    <soleDispositivePower>450000</soleDispositivePower>
    <sharedDispositivePower>0</sharedDispositivePower>
  </reportingPerson>
</submission>
""",
            sections=[
                "Purpose of Transaction\nThis filer is activist.",
                "Item 3 Source and Amount of Funds\nCash on hand was used for the purchases.",
            ],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    repo = FakeRepo()
    security = SimpleNamespace(cik="0001326380", ticker="XYZ")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-4a",
    )

    assert len(bundles) == 1
    bundle = bundles[0]
    numeric_facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundle.facts}
    assert numeric_facts[("source_of_funds_amount", "filer:1")] == 3500000.0
    assert numeric_facts[("aggregate_purchase_price", "filer:1")] == 3500000.0
    assert ("aggregate_purchase_price", "document") not in numeric_facts
    assert repo.logs == []


def test_build_bundles_from_provider_emits_form144_sale_notice_rows(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000104",
        cik="0001326380",
        form_type="144",
        accepted_at=datetime(2024, 5, 5, tzinfo=timezone.utc),
        filing=FakeForm144Filing(
            form="144",
            securities_information=[
                {"units_to_be_sold": 17087, "market_value": 1282000.0},
            ],
            securities_sold_past_3_months=[
                {"amount_sold": 5000, "gross_proceeds": 410000.0},
            ],
            sections=["Remarks\nThe planned sale is for diversification."],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    repo = FakeRepo()
    security = SimpleNamespace(cik="0001326380", ticker="XYZ")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-5",
    )

    assert len(bundles) == 1
    bundle = bundles[0]
    facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundle.facts}
    assert facts[("proposed_sale_shares", "sale_notice:1")] == 17087.0
    assert facts[("proposed_sale_market_value", "sale_notice:1")] == 1282000.0
    assert facts[("shares_sold_past_3m", "sold_past_3m:1")] == 5000.0
    assert facts[("market_value_sold_past_3m", "sold_past_3m:1")] == 410000.0
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundle.facts if fact.value_text is not None}
    assert text_facts[("rule144_sale_plan_quant", "document")] == "diversification"
    json_facts = {(fact.field_name, fact.subject_key): fact.value_json for fact in bundle.facts if fact.value_json is not None}
    assert json.loads(json_facts[("rule144_sale_plan_quant", "document")])["sale_reason"] == "diversification"
    assert repo.logs == []


def test_build_bundles_from_provider_keeps_form144_numeric_when_text_field_extraction_fails(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000104B",
        cik="0001326380",
        form_type="144",
        accepted_at=datetime(2024, 5, 5, tzinfo=timezone.utc),
        filing=FakeForm144Filing(
            form="144",
            securities_information=[
                {"units_to_be_sold": 17087, "market_value": 1282000.0},
            ],
            securities_sold_past_3_months=[
                {"amount_sold": 5000, "gross_proceeds": 410000.0},
            ],
            sections=["Remarks\nThe planned sale is for diversification."],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    original_extract_field = provider_module.TextExtractionEngine.extract_field

    def failing_extract_field(self, *, filing, field_spec):
        if field_spec.field_name == "rule144_sale_plan_quant":
            return {"status": "error", "error_code": "FORCED_TEXT_FAILURE"}
        return original_extract_field(self, filing=filing, field_spec=field_spec)

    monkeypatch.setattr(provider_module.TextExtractionEngine, "extract_field", failing_extract_field)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0001326380", ticker="XYZ")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-144-text-failure",
    )

    assert len(bundles) == 1
    bundle = bundles[0]
    facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundle.facts if fact.value_numeric is not None}
    assert facts[("proposed_sale_shares", "sale_notice:1")] == 17087.0
    assert facts[("proposed_sale_market_value", "sale_notice:1")] == 1282000.0
    assert facts[("shares_sold_past_3m", "sold_past_3m:1")] == 5000.0
    assert facts[("market_value_sold_past_3m", "sold_past_3m:1")] == 410000.0
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundle.facts if fact.value_text is not None}
    assert ("rule144_sale_plan_quant", "document") not in text_facts
    assert any(log["error_type"] == "FORCED_TEXT_FAILURE" for log in repo.logs)


def test_build_bundles_from_provider_preserves_form144_text_when_row_bundle_violates_subject_contract(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000104A",
        cik="0001326380",
        form_type="144",
        accepted_at=datetime(2024, 5, 5, tzinfo=timezone.utc),
        filing=FakeForm144Filing(
            form="144",
            securities_information=[],
            securities_sold_past_3_months=[],
            sections=["Remarks\nThe planned sale is for diversification."],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    def build_invalid_form144_bundle(*, envelope, filing):
        del envelope
        return BundleBuildOutcome(
            bundle=FilingBundle(
                filing=filing,
                facts=[
                    FactInput(
                        field_name="proposed_sale_shares",
                        subject_key="document",
                        value_numeric=17087.0,
                        confidence=0.99,
                    )
                ],
                evidences=[
                    EvidenceInput(
                        field_name="proposed_sale_shares",
                        subject_key="document",
                        locator_kind="obj",
                        source_span="securities_information.units_to_be_sold[0]",
                        raw_value="17087",
                        normalized_value="17087.0",
                    )
                ],
            )
        )

    monkeypatch.setattr(provider_module, "build_owner_form144_bundle", build_invalid_form144_bundle)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0001326380", ticker="XYZ")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-5-invalid-contract",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("rule144_sale_plan_quant", "document")] == "diversification"
    numeric_fields = {(fact.field_name, fact.subject_key) for fact in bundles[0].facts if fact.value_numeric is not None}
    assert ("proposed_sale_shares", "document") not in numeric_fields
    assert repo.logs[-1]["error_type"] == "SPECIALIZED_SUBJECT_CONTRACT_VIOLATION"


def test_build_bundles_from_provider_keeps_form144_rows_without_sale_notice_table(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000105",
        cik="0001326380",
        form_type="144",
        accepted_at=datetime(2024, 5, 6, tzinfo=timezone.utc),
        filing=FakeForm144Filing(
            form="144",
            securities_information=[],
            securities_sold_past_3_months=[
                {"amount_sold": 5000, "gross_proceeds": 410000.0},
            ],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    repo = FakeRepo()
    security = SimpleNamespace(cik="0001326380", ticker="XYZ")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-6",
    )

    assert len(bundles) == 1
    bundle = bundles[0]
    facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundle.facts}
    assert facts[("shares_sold_past_3m", "sold_past_3m:1")] == 5000.0
    assert facts[("market_value_sold_past_3m", "sold_past_3m:1")] == 410000.0
    assert repo.logs == []


def test_build_bundles_from_provider_preserves_form144_text_when_row_bundle_fails(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000106",
        cik="0001326380",
        form_type="144",
        accepted_at=datetime(2024, 5, 7, tzinfo=timezone.utc),
        filing=FakeForm144Filing(
            form="144",
            securities_information=[],
            securities_sold_past_3_months=[],
            sections=["Remarks\nThe planned sale is for diversification."],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    def fail_form144_bundle(*, envelope, filing):
        del envelope, filing
        return BundleBuildOutcome(bundle=None, error_detail="mock form144 failure")

    monkeypatch.setattr(provider_module, "build_owner_form144_bundle", fail_form144_bundle)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0001326380", ticker="XYZ")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-7",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("rule144_sale_plan_quant", "document")] == "diversification"
    numeric_fields = {(fact.field_name, fact.subject_key) for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_fields == set()
    assert repo.logs[-1]["error_type"] == "OWNER_OBJ_UNAVAILABLE"


def test_build_bundles_from_provider_preserves_form144_text_when_bundle_has_no_rows(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000106A",
        cik="0001326380",
        form_type="144",
        accepted_at=datetime(2024, 5, 7, tzinfo=timezone.utc),
        filing=FakeForm144Filing(
            form="144",
            securities_information=[],
            securities_sold_past_3_months=[],
            sections=["Remarks\nThe planned sale is for diversification."],
        ),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    def empty_form144_bundle(*, envelope, filing):
        del envelope
        return BundleBuildOutcome(
            bundle=FilingBundle(
                filing=filing,
                facts=[],
                evidences=[],
            )
        )

    monkeypatch.setattr(provider_module, "build_owner_form144_bundle", empty_form144_bundle)

    repo = FakeRepo()
    security = SimpleNamespace(cik="0001326380", ticker="XYZ")
    bundles = cli_module._build_bundles_from_provider(
        security=security,
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-empty-form144",
    )

    assert len(bundles) == 1
    text_facts = {(fact.field_name, fact.subject_key): fact.value_text for fact in bundles[0].facts if fact.value_text is not None}
    assert text_facts[("rule144_sale_plan_quant", "document")] == "diversification"
    numeric_fields = {(fact.field_name, fact.subject_key) for fact in bundles[0].facts if fact.value_numeric is not None}
    assert numeric_fields == set()
    assert repo.logs[-1]["error_type"] == "NO_OWNER_ROWS_EXTRACTED"


def test_classify_form_family_normalizes_schedule_aliases() -> None:
    assert classify_form_family("SC 13G") == "13G"
    assert classify_form_family("SC 13D/A") == "13D"
    assert classify_form_family("SCHEDULE 13D") == "13D"
    assert classify_form_family("SCHEDULE 13G/A") == "13G"
