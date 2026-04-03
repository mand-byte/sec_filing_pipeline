from typer.testing import CliRunner

from src.cli import app


runner = CliRunner()


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
