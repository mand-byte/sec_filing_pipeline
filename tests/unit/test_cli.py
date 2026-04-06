from src.cli import app


def test_cli_has_expected_command_name():
    command_names = [command.name for command in app.registered_commands]

    assert "run-once" in command_names
