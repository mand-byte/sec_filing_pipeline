from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from typer.testing import CliRunner

import src.cli as cli_module
import src.pipeline.runtime_preflight as runtime_preflight_module
from src.db.base import Base
from src.db.models import SecurityMaster
from src.pipeline.runtime_preflight import run_runtime_preflight


runner = CliRunner()


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _session_factory(engine):
    return sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False)


def test_run_runtime_preflight_passes_with_ready_runtime(monkeypatch) -> None:
    engine = _engine()
    factory = _session_factory(engine)
    with factory() as session:
        session.add(
            SecurityMaster(
                composite_figi="BBG000BPH459",
                ticker="MSFT",
                cik="0000789019",
                active=True,
                delisted_utc=None,
                last_updated_utc=None,
            )
        )
        session.commit()

    class FakeQueryResult:
        def __init__(self, rows):
            self.result_rows = rows

    class FakeClient:
        def query(self, query: str):
            if query == "SELECT 1":
                return FakeQueryResult([(1,)])
            if query.startswith("EXISTS TABLE"):
                return FakeQueryResult([(1,)])
            raise AssertionError(query)

        def close(self):
            return None

    monkeypatch.setattr(runtime_preflight_module, "get_session_factory", lambda settings=None: factory)

    result = run_runtime_preflight(
        settings=SimpleNamespace(
            pg_dsn="sqlite+pysqlite:///:memory:",
            ch_dsn="clickhouse://default@localhost/default",
            security_universe_table="quant_data.us_stock_universe",
            edgar_identity="Example Ops ops@example.test",
            text_normalizer_mode="http_json",
            text_normalizer_base_url="https://example.test/v1",
            text_normalizer_model="gpt-5.4",
            text_normalizer_api_key="secret",
        ),
        engine=engine,
        clickhouse_client_factory=lambda **kwargs: FakeClient(),
    )

    assert result.passed is True
    assert {check.name: check.status for check in result.checks} == {
        "postgres_schema": "pass",
        "edgar_identity": "pass",
        "text_normalizer": "pass",
        "clickhouse_connectivity": "pass",
        "security_universe_source": "pass",
    }


def test_run_runtime_preflight_fails_for_missing_identity_and_universe_table(monkeypatch) -> None:
    engine = _engine()
    factory = _session_factory(engine)

    class FakeQueryResult:
        def __init__(self, rows):
            self.result_rows = rows

    class FakeClient:
        def query(self, query: str):
            if query == "SELECT 1":
                return FakeQueryResult([(1,)])
            if query.startswith("EXISTS TABLE"):
                return FakeQueryResult([(0,)])
            if "FROM system.tables" in query:
                return FakeQueryResult([("quant_data", "us_stock_universe")])
            raise AssertionError(query)

        def close(self):
            return None

    monkeypatch.setattr(runtime_preflight_module, "get_session_factory", lambda settings=None: factory)

    result = run_runtime_preflight(
        settings=SimpleNamespace(
            pg_dsn="sqlite+pysqlite:///:memory:",
            ch_dsn="clickhouse://default@localhost/default",
            security_universe_table="data_quant.us_stock_universe",
            edgar_identity=None,
            text_normalizer_mode="unavailable",
            text_normalizer_base_url=None,
            text_normalizer_model=None,
            text_normalizer_api_key=None,
        ),
        engine=engine,
        clickhouse_client_factory=lambda **kwargs: FakeClient(),
    )

    assert result.passed is False
    by_name = {check.name: check for check in result.checks}
    assert by_name["edgar_identity"].status == "fail"
    assert by_name["security_universe_source"].status == "fail"
    assert "similar tables: quant_data.us_stock_universe" in by_name["security_universe_source"].detail


def test_cli_runtime_preflight_uses_result_and_exit_code(monkeypatch) -> None:
    class FakeResult:
        def __init__(self, *, passed: bool):
            self.passed = passed

        def asdict(self):
            return {"passed": self.passed, "checks": []}

    monkeypatch.setattr(cli_module, "Settings", lambda: object())
    monkeypatch.setattr(cli_module, "run_runtime_preflight", lambda settings: FakeResult(passed=False))

    result = runner.invoke(cli_module.app, ["runtime-preflight"])

    assert result.exit_code == 1
    assert '"passed": false' in result.stdout
