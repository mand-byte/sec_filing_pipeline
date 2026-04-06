from typer.testing import CliRunner

from src.cli import app


runner = CliRunner()


def test_cli_help_includes_expected_commands():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "run-once" in result.stdout
    assert "schedule" in result.stdout
