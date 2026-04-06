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


def test_schedule_command_invokes_successfully():
    result = runner.invoke(app, ["schedule"])

    assert result.exit_code == 0
    assert "schedule placeholder" in result.stdout
