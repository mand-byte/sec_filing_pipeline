from datetime import datetime, timezone

import pytest
from typer.testing import CliRunner

from src.cli import app


runner = CliRunner()


class _FakeRow:
    def __init__(
        self,
        *,
        accession_no: str,
        document_id: str,
        document_filename: str,
        document_type: str,
        document_path: str,
        parser_method: str,
        status: str,
        failure_type: str | None,
        fallback_reason: str | None,
        decision_state: str | None,
        selected_candidate: bool,
        attempted_at_utc: datetime,
    ) -> None:
        self.id = f"{accession_no}:{document_id}:{parser_method}:{attempted_at_utc.isoformat()}"
        self.accession_no = accession_no
        self.document_id = document_id
        self.document_filename = document_filename
        self.document_type = document_type
        self.document_path = document_path
        self.parser_method = parser_method
        self.status = status
        self.failure_type = failure_type
        self.fallback_reason = fallback_reason
        self.decision_state = decision_state
        self.selected_candidate = selected_candidate
        self.attempted_at_utc = attempted_at_utc


class _FakeSession:
    def __init__(self, rows: list[_FakeRow]) -> None:
        self.rows = rows

    def close(self) -> None:
        return None


def test_root_help_includes_parse_log_group_and_existing_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "parse-log" in result.output
    assert "init-db" in result.output
    assert "owner-sync" in result.output
    assert "replay-accession" in result.output


def test_parse_log_query_help_exposes_expected_options() -> None:
    result = runner.invoke(app, ["parse-log", "query", "--help"])

    assert result.exit_code == 0
    assert "--document-type" in result.output
    assert "--from-utc" in result.output
    assert "--to-utc" in result.output
    assert "--failure-type" in result.output
    assert "--limit" in result.output
    assert "--offset" in result.output


def test_parse_log_timeline_help_exposes_expected_options() -> None:
    result = runner.invoke(app, ["parse-log", "timeline", "--help"])

    assert result.exit_code == 0
    assert "--accession-no" in result.output
    assert "--document-id" in result.output


def test_parse_log_timeline_requires_accession_no_and_document_id() -> None:
    result = runner.invoke(app, ["parse-log", "timeline"])

    assert result.exit_code != 0
    assert "Missing option '--accession-no'" in result.output


def test_parse_log_query_rejects_invalid_pagination_values() -> None:
    result_limit = runner.invoke(app, ["parse-log", "query", "--limit", "0"])
    result_offset = runner.invoke(app, ["parse-log", "query", "--offset", "-1"])

    assert result_limit.exit_code != 0
    assert "Invalid value for '--limit'" in result_limit.output
    assert result_offset.exit_code != 0
    assert "Invalid value for '--offset'" in result_offset.output


def test_parse_log_query_outputs_expected_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted_at = datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc)
    rows = [
        _FakeRow(
            accession_no="0000320193-24-000012",
            document_id="doc-1",
            document_filename="ownership.xml",
            document_type="4",
            document_path="raw/0000320193/0000320193-24-000012/doc.xml",
            parser_method="structured_xml",
            status="failed",
            failure_type="parse",
            fallback_reason="structured_xml_exception",
            decision_state="needs_review",
            selected_candidate=False,
            attempted_at_utc=attempted_at,
        )
    ]
    monkeypatch.setattr(
        "src.cli.SessionLocal",
        lambda: _FakeSession(rows),
    )

    result = runner.invoke(
        app,
        [
            "parse-log",
            "query",
            "--document-type",
            "4",
            "--from-utc",
            "2024-04-03T11:00:00Z",
            "--to-utc",
            "2024-04-03T13:00:00Z",
        ],
    )

    assert result.exit_code == 0
    assert "accession_no=0000320193-24-000012" in result.output
    assert "document_filename=ownership.xml" in result.output
    assert "document_type=4" in result.output
    assert "document_path=raw/0000320193/0000320193-24-000012/doc.xml" in result.output
    assert "parser_method=structured_xml" in result.output
    assert "status=failed" in result.output
    assert "failure_type=parse" in result.output
    assert "attempted_at_utc=2024-04-03T12:00:00+00:00" in result.output


def test_parse_log_query_rejects_invalid_datetime() -> None:
    result = runner.invoke(
        app,
        ["parse-log", "query", "--from-utc", "not-a-date"],
    )

    assert result.exit_code != 0
    assert "Invalid ISO datetime for --from-utc" in result.output


def test_parse_log_timeline_outputs_ordered_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        _FakeRow(
            accession_no="0000320193-24-000012",
            document_id="doc-1",
            document_filename="ownership.xml",
            document_type="4",
            document_path="raw/doc.xml",
            parser_method="structured_xml",
            status="failed",
            failure_type="logic",
            fallback_reason="structured_xml_missing_mandatory",
            decision_state="needs_review",
            selected_candidate=False,
            attempted_at_utc=datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc),
        ),
        _FakeRow(
            accession_no="0000320193-24-000012",
            document_id="doc-1",
            document_filename="ownership.txt",
            document_type="4",
            document_path="raw/doc.txt",
            parser_method="deterministic_rule",
            status="success",
            failure_type=None,
            fallback_reason=None,
            decision_state="needs_review",
            selected_candidate=True,
            attempted_at_utc=datetime(2024, 4, 3, 12, 1, tzinfo=timezone.utc),
        ),
    ]
    monkeypatch.setattr("src.cli.SessionLocal", lambda: _FakeSession(rows))

    result = runner.invoke(
        app,
        [
            "parse-log",
            "timeline",
            "--accession-no",
            "0000320193-24-000012",
            "--document-id",
            "doc-1",
        ],
    )

    assert result.exit_code == 0
    assert "parser_method=structured_xml" in result.output
    assert "parser_method=deterministic_rule" in result.output
    assert "fallback_reason=structured_xml_missing_mandatory" in result.output
    assert "decision_state=needs_review" in result.output
    assert "selected_candidate=True" in result.output


def test_owner_sync_requires_cik_and_accession_no() -> None:
    result = runner.invoke(app, ["owner-sync"])

    assert result.exit_code != 0
    assert "Missing option '--cik'" in result.output


def test_owner_sync_executes_phase3_replay_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def _fake_process_replay_accession(cik: str, accession_no: str) -> int:
        calls.append((cik, accession_no))
        return 1

    monkeypatch.setattr(
        "src.cli.process_replay_accession",
        _fake_process_replay_accession,
    )

    result = runner.invoke(
        app,
        [
            "owner-sync",
            "--cik",
            "0000320193",
            "--accession-no",
            "0000320193-24-000012",
        ],
    )

    assert result.exit_code == 0
    assert calls == [("0000320193", "0000320193-24-000012")]
