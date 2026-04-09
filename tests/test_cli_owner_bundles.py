from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import src.cli as cli_module
from src.pipeline.edgar_provider import FilingEnvelope


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
    def __init__(self, transactions: list[FakeTransaction], derivative_rows: list[dict[str, object]] | None = None, non_derivative_holding_rows: list[dict[str, object]] | None = None, derivative_holding_rows: list[dict[str, object]] | None = None, form: str = "4"):
        self.form = form
        self._form4 = FakeForm4(transactions, derivative_rows, non_derivative_holding_rows, derivative_holding_rows)

    def obj(self) -> FakeForm4:
        return self._form4


class FakeRepo:
    def __init__(self) -> None:
        self.logs: list[dict[str, object]] = []

    def write_log(self, **kwargs: object) -> None:
        self.logs.append(dict(kwargs))


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

    evidence_keys = {(e.field_name, e.subject_key) for e in bundle.evidences}
    assert ("transaction_price_per_share", "txn:1") in evidence_keys
    assert ("shares_owned_following_txn", "txn:2") in evidence_keys
    assert ("derivative_underlying_shares", "dtxn:1") in evidence_keys
    assert ("exercise_or_conversion_price", "dtxn:2") in evidence_keys
    assert repo.logs == []


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

    evidence_keys = {(e.field_name, e.subject_key) for e in bundle.evidences}
    assert ("non_derivative_shares_owned", "nhold:1") in evidence_keys
    assert ("derivative_underlying_shares", "dhold:2") in evidence_keys
    assert ("exercise_or_conversion_price", "dhold:1") in evidence_keys
    assert repo.logs == []
