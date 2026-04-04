from dataclasses import dataclass

import pytest
from typer.testing import CliRunner

from src.cli import app


runner = CliRunner()


@dataclass(frozen=True)
class _FakeOwnerSyncResult:
    discovered_count: int
    processed_count: int
    last_accession_no: str | None


def test_owner_sync_requires_cik_only() -> None:
    result = runner.invoke(app, ["owner-sync"])

    assert result.exit_code != 0
    assert "Missing option '--cik'" in result.output


def test_owner_sync_delegates_to_discovery_service(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def _fake_process_owner_sync(cik: str) -> _FakeOwnerSyncResult:
        calls.append(cik)
        return _FakeOwnerSyncResult(
            discovered_count=2,
            processed_count=5,
            last_accession_no="0000320193-24-000013",
        )

    monkeypatch.setattr("src.cli.process_owner_sync", _fake_process_owner_sync)

    result = runner.invoke(app, ["owner-sync", "--cik", "320193"])

    assert result.exit_code == 0
    assert calls == ["320193"]
    assert "owner-sync completed:" in result.output
    assert "discovered=2" in result.output
    assert "processed=5" in result.output
    assert "last_accession_no=0000320193-24-000013" in result.output


def test_replay_accession_keeps_explicit_accession_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def _fake_process_replay_accession(cik: str, accession_no: str) -> int:
        calls.append((cik, accession_no))
        return 3

    monkeypatch.setattr("src.cli.process_replay_accession", _fake_process_replay_accession)

    result = runner.invoke(
        app,
        [
            "replay-accession",
            "0000320193-24-000012",
            "--cik",
            "0000320193",
        ],
    )

    assert result.exit_code == 0
    assert calls == [("0000320193", "0000320193-24-000012")]
    assert "replay completed for 0000320193-24-000012: processed_documents=3" in result.output
