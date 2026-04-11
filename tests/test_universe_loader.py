from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import src.pipeline.universe as universe_module
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.db.base import Base
from src.db.models import SecurityMaster
from src.pipeline.universe import load_security_universe


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False)()


def test_load_security_universe_reads_configured_table_when_present() -> None:
    session = _session()
    session.execute(
        text(
            """
            CREATE TABLE security_universe_feed (
                ticker TEXT NOT NULL,
                composite_figi TEXT NOT NULL,
                cik TEXT NOT NULL,
                active INTEGER NOT NULL,
                delisted_utc TIMESTAMP NULL
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO security_universe_feed
            (ticker, composite_figi, cik, active, delisted_utc)
            VALUES
            ('MSFT', 'BBG000BPH459', '0000789019', 1, NULL),
            ('AAPL', 'BBG000B9XRY4', '0000320193', 0, '2024-05-01 00:00:00')
            """
        )
    )
    session.commit()

    rows = load_security_universe(
        session=session,
        settings=SimpleNamespace(security_universe_table="security_universe_feed"),
    )

    assert [(row.cik, row.ticker) for row in rows] == [
        ("0000320193", "AAPL"),
        ("0000789019", "MSFT"),
    ]
    assert rows[0].active is False
    assert rows[0].delisted_utc == datetime(2024, 5, 1, tzinfo=timezone.utc)


def test_load_security_universe_falls_back_to_security_master() -> None:
    session = _session()
    session.add(
        SecurityMaster(
            composite_figi="BBG000BPH459",
            ticker="MSFT",
            cik="0000789019",
            active=True,
            delisted_utc=None,
            last_updated_utc=datetime(2024, 5, 1, tzinfo=timezone.utc),
        )
    )
    session.commit()

    rows = load_security_universe(
        session=session,
        settings=SimpleNamespace(security_universe_table="missing_universe_table"),
    )

    assert [(row.cik, row.ticker, row.composite_figi) for row in rows] == [
        ("0000789019", "MSFT", "BBG000BPH459"),
    ]


def test_load_security_universe_reads_clickhouse_when_ch_dsn_present(monkeypatch) -> None:
    session = _session()

    class FakeResult:
        named_results = [
            {
                "ticker": "MSFT",
                "composite_figi": "BBG000BPH459",
                "cik": "0000789019",
                "active": 1,
                "delisted_utc": None,
            },
            {
                "ticker": "AAPL",
                "composite_figi": "BBG000B9XRY4",
                "cik": "0000320193",
                "active": 0,
                "delisted_utc": "2024-05-01T00:00:00Z",
            },
        ]

    class FakeClient:
        def __init__(self) -> None:
            self.queries: list[str] = []
            self.closed = False

        def query(self, query: str) -> FakeResult:
            self.queries.append(query)
            return FakeResult()

        def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()

    def fake_get_client(*, dsn: str):
        assert dsn == "clickhouse://default@localhost/default"
        return fake_client

    monkeypatch.setattr(universe_module.clickhouse_connect, "get_client", fake_get_client)

    rows = load_security_universe(
        session=session,
        settings=SimpleNamespace(
            ch_dsn="clickhouse://default@localhost/default",
            security_universe_table="data_quant.us_stock_universe",
        ),
    )

    assert [(row.cik, row.ticker) for row in rows] == [
        ("0000320193", "AAPL"),
        ("0000789019", "MSFT"),
    ]
    assert fake_client.closed is True


def test_load_security_universe_falls_back_when_clickhouse_query_fails(monkeypatch) -> None:
    session = _session()
    session.add(
        SecurityMaster(
            composite_figi="BBG000BPH459",
            ticker="MSFT",
            cik="0000789019",
            active=True,
            delisted_utc=None,
            last_updated_utc=datetime(2024, 5, 1, tzinfo=timezone.utc),
        )
    )
    session.commit()

    def fake_get_client(*, dsn: str):
        raise RuntimeError(f"cannot connect to {dsn}")

    monkeypatch.setattr(universe_module.clickhouse_connect, "get_client", fake_get_client)

    rows = load_security_universe(
        session=session,
        settings=SimpleNamespace(
            ch_dsn="clickhouse://default@localhost/default",
            security_universe_table="data_quant.us_stock_universe",
        ),
    )

    assert [(row.cik, row.ticker, row.composite_figi) for row in rows] == [
        ("0000789019", "MSFT", "BBG000BPH459"),
    ]
