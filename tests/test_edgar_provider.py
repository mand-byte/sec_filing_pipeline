from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import sys

from src.pipeline.edgar_provider import fetch_filings_for_security


class FakeCompany:
    def __init__(self, cik: str):
        self.cik = cik

    def get_filings(self, *, form: list[str]) -> list[object]:
        assert "10-Q" in form
        return [
            SimpleNamespace(
                accession_no="0000000000-24-000001",
                form="10-Q/A",
                acceptance_datetime="2024-05-02T10:00:00Z",
                filing_date="2024-05-01",
                period_of_report="2024-03-31",
                amendment_no="2",
            )
        ]


class RaisingCompany:
    def __init__(self, cik: str):
        self.cik = cik

    def get_filings(self, *, form: list[str]) -> list[object]:
        del form
        raise RuntimeError("identity missing")


def test_fetch_filings_for_security_populates_filing_metadata(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "edgar", SimpleNamespace(Company=FakeCompany))

    envelopes = fetch_filings_for_security(
        security=SimpleNamespace(cik="0000789019"),
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
    )

    assert len(envelopes) == 1
    envelope = envelopes[0]
    assert envelope.filed_at == datetime(2024, 5, 1, tzinfo=timezone.utc)
    assert envelope.period_end == datetime(2024, 3, 31, tzinfo=timezone.utc)
    assert envelope.amendment_no == 2


def test_fetch_filings_for_security_applies_identity_and_surfaces_provider_error(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_set_identity(identity: str) -> None:
        captured["identity"] = identity

    monkeypatch.setitem(
        sys.modules,
        "edgar",
        SimpleNamespace(Company=RaisingCompany, set_identity=fake_set_identity),
    )

    try:
        fetch_filings_for_security(
            security=SimpleNamespace(cik="0000789019"),
            route="issuer",
            start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
            identity="Example Ops ops@example.test",
        )
    except RuntimeError as exc:
        assert "edgar fetch failed" in str(exc)
        assert "identity missing" in str(exc)
    else:
        raise AssertionError("expected runtime provider error")

    assert captured["identity"] == "Example Ops ops@example.test"


class EndDateCompany:
    def __init__(self, cik: str):
        self.cik = cik

    def get_filings(self, *, form: list[str]) -> list[object]:
        assert "10-Q" in form
        return [
            SimpleNamespace(
                accession_no="0000000000-24-000010",
                form="10-Q",
                acceptance_datetime="2024-05-02T10:00:00Z",
            ),
            SimpleNamespace(
                accession_no="0000000000-24-000011",
                form="10-Q",
                acceptance_datetime="2024-05-03T10:00:00Z",
            ),
        ]


def test_fetch_filings_for_security_respects_optional_end_accepted_at(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "edgar", SimpleNamespace(Company=EndDateCompany))

    envelopes = fetch_filings_for_security(
        security=SimpleNamespace(cik="0000789019"),
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        end_accepted_at=datetime(2024, 5, 2, 23, 59, 59, tzinfo=timezone.utc),
    )

    assert [envelope.accession_no for envelope in envelopes] == ["0000000000-24-000010"]
