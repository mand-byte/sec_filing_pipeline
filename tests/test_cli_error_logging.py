from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import src.cli as cli_module
from src.pipeline.edgar_provider import FilingEnvelope


class ExplodingForm4Filing:
    form = "4"

    def obj(self) -> object:
        raise RuntimeError("obj exploded")


class FakeRepo:
    def __init__(self) -> None:
        self.logs: list[dict[str, object]] = []

    def write_log(self, **kwargs: object) -> None:
        self.logs.append(dict(kwargs))


def test_build_bundles_from_provider_logs_error_detail_for_owner_obj_failure(monkeypatch) -> None:
    envelope = FilingEnvelope(
        accession_no="0000000000-24-000999",
        cik="0000789019",
        form_type="4",
        accepted_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
        filing=ExplodingForm4Filing(),
    )

    monkeypatch.setattr(
        cli_module,
        "fetch_filings_for_security",
        lambda *, security, route, start_accepted_at: [envelope],
    )

    repo = FakeRepo()
    bundles = cli_module._build_bundles_from_provider(
        security=SimpleNamespace(cik="0000789019", ticker="MSFT"),
        route="owner",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        repo=repo,
        run_id="run-owner-error",
    )

    assert bundles == []
    assert len(repo.logs) == 1
    assert repo.logs[0]["error_type"] == "OWNERSHIP_OBJ_UNAVAILABLE"
    assert "RuntimeError: obj exploded" in str(repo.logs[0]["error_detail"])
    assert "in obj" in str(repo.logs[0]["error_detail"])
