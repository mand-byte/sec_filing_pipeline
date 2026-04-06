from typer.testing import CliRunner

from src.cli import app


runner = CliRunner()


def test_cli_help_includes_expected_commands():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "run-once" in result.stdout
    assert "schedule" in result.stdout


def test_run_once_command_invokes_successfully():
    result = runner.invoke(app, ["run-once"])

    assert result.exit_code == 0
    assert "run-once placeholder" in result.stdout


def test_schedule_command_invokes_successfully(monkeypatch):
    monkeypatch.setenv("PG_DSN", "postgresql://user:pass@localhost:5432/sec_filings")

    class _StubScheduler:
        def start(self) -> None:
            print("schedule placeholder (task5 wiring)")

    monkeypatch.setattr(
        "src.cli.build_blocking_scheduler",
        lambda interval_minutes, tick_callable: _StubScheduler(),
    )

    result = runner.invoke(app, ["schedule"])

    assert result.exit_code == 0
    assert "schedule placeholder" in result.stdout
