from __future__ import annotations

import sys
from datetime import datetime, timezone
from types import SimpleNamespace

from src.pipeline.edgar_provider import classify_form_family, fetch_filings_for_security


def test_classify_form_family_normalizes_amendments() -> None:
    assert classify_form_family("10-K/A") == "10-K"
    assert classify_form_family("13F-HR/A") == "13F-HR/A"


def test_classify_form_family_keeps_known_forms() -> None:
    assert classify_form_family("8-K") == "8-K"
    assert classify_form_family("144") == "144"


def test_fetch_filings_for_security_returns_filtered_envelopes(monkeypatch) -> None:
    start = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)

    before = SimpleNamespace(
        accession_no="0000000001-25-000001",
        form="10-K",
        acceptance_datetime=datetime(2024, 12, 31, 23, 0, tzinfo=timezone.utc),
    )
    after = SimpleNamespace(
        accession_no="0000000001-25-000002",
        form="10-K",
        acceptance_datetime=datetime(2025, 1, 1, 1, 0, tzinfo=timezone.utc),
    )

    class _FakeCompany:
        def __init__(self, identifier: str) -> None:
            self.identifier = identifier

        def get_filings(self, *, form: list[str]):
            assert "10-K" in form
            return [before, after]

    monkeypatch.setitem(sys.modules, "edgar", SimpleNamespace(Company=_FakeCompany))

    security = SimpleNamespace(cik="0000000001")
    envelopes = fetch_filings_for_security(
        security=security,
        route="issuer",
        start_accepted_at=start,
    )

    assert len(envelopes) == 1
    envelope = envelopes[0]
    assert envelope.accession_no == "0000000001-25-000002"
    assert envelope.cik == "0000000001"
    assert envelope.form_type == "10-K"
    assert envelope.accepted_at == datetime(2025, 1, 1, 1, 0, tzinfo=timezone.utc)
    assert envelope.filing is after


def test_fetch_filings_for_security_returns_empty_for_unknown_route() -> None:
    security = SimpleNamespace(cik="0000000001")
    envelopes = fetch_filings_for_security(
        security=security,
        route="unknown",
        start_accepted_at=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
    )

    assert envelopes == []
