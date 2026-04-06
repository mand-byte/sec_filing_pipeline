from datetime import datetime, timezone
from types import SimpleNamespace

from typer.testing import CliRunner

import src.cli as cli
from src.cli import app


runner = CliRunner()


class _RecordingRouter:
    def __init__(self, name: str, calls: list[tuple[str, str]]):
        self.name = name
        self._calls = calls

    def run(self, *, security: SimpleNamespace) -> None:
        self._calls.append((self.name, security.cik))


def test_run_once_filters_delisted_filings_using_is_filing_eligible(monkeypatch):
    calls: list[tuple[str, str]] = []
    eligibility_calls: list[tuple[bool, datetime | None, datetime]] = []

    class _IssuerRouter(_RecordingRouter):
        def __init__(self):
            super().__init__("issuer", calls)

    class _OwnerRouter(_RecordingRouter):
        def __init__(self):
            super().__init__("owner", calls)

    class _HoldingRouter(_RecordingRouter):
        def __init__(self):
            super().__init__("holding", calls)

    eligible_delisted_utc = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    ineligible_delisted_utc = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)

    securities = [
        SimpleNamespace(
            cik="0000320193",
            active=False,
            delisted_utc=eligible_delisted_utc,
            accepted_at=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            cik="0000789019",
            active=False,
            delisted_utc=ineligible_delisted_utc,
            accepted_at=datetime(2025, 1, 15, 10, 0, 1, tzinfo=timezone.utc),
        ),
    ]

    def _fake_is_filing_eligible(active: bool, delisted_utc: datetime | None, accepted_at: datetime) -> bool:
        eligibility_calls.append((active, delisted_utc, accepted_at))
        if delisted_utc is None:
            return True
        return accepted_at <= delisted_utc

    monkeypatch.setattr(cli, "IssuerRouter", _IssuerRouter, raising=False)
    monkeypatch.setattr(cli, "OwnerRouter", _OwnerRouter, raising=False)
    monkeypatch.setattr(cli, "HoldingRouter", _HoldingRouter, raising=False)
    monkeypatch.setattr(cli, "_load_run_once_securities", lambda: securities, raising=False)
    monkeypatch.setattr(cli, "is_filing_eligible", _fake_is_filing_eligible, raising=False)

    result = runner.invoke(app, ["run-once"])

    assert result.exit_code == 0
    assert "route order: issuer -> owner -> holding" in result.stdout
    assert len(eligibility_calls) == 2
    assert calls == [
        ("issuer", "0000320193"),
        ("owner", "0000320193"),
        ("holding", "0000320193"),
    ]
