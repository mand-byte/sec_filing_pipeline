from __future__ import annotations

from types import SimpleNamespace

import src.db.session as session_module


def test_build_engine_uses_postgres_hardening_options(monkeypatch) -> None:
    session_module._engine_for_dsn.cache_clear()
    captured: dict[str, object] = {}

    def fake_create_engine(dsn: str, **kwargs: object) -> object:
        captured["dsn"] = dsn
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(session_module, "create_engine", fake_create_engine)

    session_module.build_engine(SimpleNamespace(pg_dsn="postgresql+psycopg://user:pass@db/sec_filing"))

    assert captured["dsn"] == "postgresql+psycopg://user:pass@db/sec_filing"
    kwargs = captured["kwargs"]
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_recycle"] == 1800
    assert "idle_in_transaction_session_timeout=300000" in kwargs["connect_args"]["options"]
    assert "lock_timeout=60000" in kwargs["connect_args"]["options"]


def test_build_engine_leaves_non_postgres_without_special_options(monkeypatch) -> None:
    session_module._engine_for_dsn.cache_clear()
    captured: dict[str, object] = {}

    def fake_create_engine(dsn: str, **kwargs: object) -> object:
        captured["dsn"] = dsn
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(session_module, "create_engine", fake_create_engine)

    session_module.build_engine(SimpleNamespace(pg_dsn="sqlite+pysqlite:///:memory:"))

    assert captured["dsn"] == "sqlite+pysqlite:///:memory:"
    assert captured["kwargs"] == {}
