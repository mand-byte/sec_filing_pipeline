from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
import src.cli as cli_module
from src.pipeline.edgar_provider import FilingEnvelope


class FakeSummaryPage:
    def __init__(self, *, other_included_managers_count: int, total_holdings: int, total_value: Decimal):
        self.other_included_managers_count = other_included_managers_count
        self.total_holdings = total_holdings
        self.total_value = total_value


class FakePrimaryFormInformation:
    def __init__(self, *, summary_page: FakeSummaryPage):
        self.summary_page = summary_page


class Fake13F:
    def __init__(
        self,
        *,
        form: str,
        rows: list[dict[str, object]],
        other_included_managers_count: int = 0,
        total_holdings: int | None = None,
        total_value: Decimal | None = None,
        sections: list[str] | None = None,
    ):
        self.form = form
        self.infotable = pd.DataFrame(rows)
        self.primary_form_information = FakePrimaryFormInformation(
            summary_page=FakeSummaryPage(
                other_included_managers_count=other_included_managers_count,
                total_holdings=total_holdings if total_holdings is not None else len(rows),
                total_value=total_value if total_value is not None else Decimal(str(sum(float(row["Value"]) for row in rows))),
            )
        )
        self.total_holdings = total_holdings if total_holdings is not None else len(rows)
        self.total_value = total_value if total_value is not None else Decimal(str(sum(float(row["Value"]) for row in rows)))
        self._sections = sections or []

    def sections(self) -> list[str]:
        return self._sections


class Fake13FFiling:
    def __init__(self, report: Fake13F):
        self.form = report.form
        self._report = report

    def obj(self) -> Fake13F:
        return self._report

    def sections(self) -> list[str]:
        return self._report.sections()


class FakeRepo:
    def __init__(self) -> None:
        self.logs: list[dict[str, object]] = []

    def write_log(self, **kwargs: object) -> None:
        self.logs.append(dict(kwargs))


def test_build_bundles_from_provider_emits_13f_position_rows(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000200",
        cik="0001067983",
        form_type="13F-HR",
        accepted_at=datetime(2024, 5, 15, tzinfo=timezone.utc),
        filing=Fake13FFiling(
            Fake13F(
                form="13F-HR",
                rows=[
                    {
                        "Issuer": "MICROSOFT CORP",
                        "Class": "COM",
                        "Cusip": "594918104",
                        "Value": 1250,
                        "SharesPrnAmount": 10000,
                        "SoleVoting": 9000,
                        "SharedVoting": 500,
                        "NonVoting": 500,
                    },
                    {
                        "Issuer": "APPLE INC",
                        "Class": "COM",
                        "Cusip": "037833100",
                        "Value": 750,
                        "SharesPrnAmount": 4000,
                        "SoleVoting": 3000,
                        "SharedVoting": 500,
                        "NonVoting": 500,
                    },
                ],
                other_included_managers_count=2,
                total_holdings=2,
                total_value=Decimal("2000"),
            )
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
        route="holding",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-holding-1",
    )

    assert len(bundles) == 1
    bundle = bundles[0]
    facts = {(fact.field_name, fact.subject_key): fact.value_numeric for fact in bundle.facts}
    assert facts[("position_value_usd", "position:1")] == 1250000.0
    assert facts[("position_value_usd", "position:2")] == 750000.0
    assert facts[("shares_or_principal_amount", "position:1")] == 10000.0
    assert facts[("sole_voting_auth_shares", "position:1")] == 9000.0
    assert facts[("shared_voting_auth_shares", "position:2")] == 500.0
    assert facts[("none_voting_auth_shares", "position:2")] == 500.0
    assert facts[("other_included_managers_count", "document")] == 2.0
    assert facts[("info_table_entry_total", "document")] == 2.0
    assert facts[("info_table_value_total_usd", "document")] == 2000000.0

    evidence = {(item.field_name, item.subject_key): item for item in bundle.evidences}
    assert evidence[("position_value_usd", "position:1")].source_span == "infotable[0].Value"
    assert evidence[("info_table_entry_total", "document")].source_span == "summary_page.tableEntryTotal"
    assert evidence[("info_table_value_total_usd", "document")].normalized_value == "2000000.0"
    assert repo.logs == []


def test_build_bundles_from_provider_merges_13f_amendment_text(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000201",
        cik="0001067983",
        form_type="13F-HR/A",
        accepted_at=datetime(2024, 5, 16, tzinfo=timezone.utc),
        filing=Fake13FFiling(
            Fake13F(
                form="13F-HR/A",
                rows=[
                    {
                        "Issuer": "MICROSOFT CORP",
                        "Class": "COM",
                        "Cusip": "594918104",
                        "Value": 1250,
                        "SharesPrnAmount": 10000,
                        "SoleVoting": 9000,
                        "SharedVoting": 500,
                        "NonVoting": 500,
                    }
                ],
                other_included_managers_count=1,
                total_holdings=1,
                total_value=Decimal("1250"),
                sections=["Header\nThis filing is a correction of the prior filing."],
            )
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
        route="holding",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-holding-2",
    )

    assert len(bundles) == 1
    bundle = bundles[0]
    facts = {(fact.field_name, fact.subject_key): fact for fact in bundle.facts}
    assert facts[("position_value_usd", "position:1")].value_numeric == 1250000.0
    assert facts[("info_table_value_total_usd", "document")].value_numeric == 1250000.0
    assert facts[("amendment_scope_quant", "document")].value_text == "correction"

    evidence = {(item.field_name, item.subject_key): item for item in bundle.evidences}
    assert evidence[("amendment_scope_quant", "document")].locator_kind == "section_window"
    assert evidence[("position_value_usd", "position:1")].source_span == "infotable[0].Value"
    assert repo.logs == []
