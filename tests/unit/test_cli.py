from typer.testing import CliRunner

from src.cli import app


runner = CliRunner()


def test_cli_help_includes_expected_commands():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "run-once" in result.stdout
    assert "schedule" in result.stdout


def test_run_once_command_invokes_successfully(monkeypatch):
    monkeypatch.setenv("PG_DSN", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("WRITE_OFFLINE_ARTIFACTS", "false")

    class _FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeSessionFactory:
        def __call__(self):
            return _FakeSession()

    monkeypatch.setattr("src.cli.get_session_factory", lambda settings: _FakeSessionFactory())
    monkeypatch.setattr("src.cli._load_run_once_securities", lambda session: [])

    result = runner.invoke(app, ["run-once"])

    assert result.exit_code == 0
    assert "route order: issuer -> owner -> holding" in result.stdout


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
