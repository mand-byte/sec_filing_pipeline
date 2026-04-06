from datetime import datetime, timezone
from types import SimpleNamespace


from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from typer.testing import CliRunner

import src.cli as cli
from src.cli import app
from src.db.base import Base
from src.db.models import ExtractedFact, ExtractionEvidence, PipelineLog
from src.pipeline.edgar_provider import FilingEnvelope
from src.pipeline.extraction.registry import all_numeric_field_specs


runner = CliRunner()


def _as_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _build_session_factory() -> sessionmaker:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _patch_runtime(monkeypatch, session_factory: sessionmaker, securities: list[SimpleNamespace]) -> None:
    monkeypatch.setenv("PG_DSN", "sqlite+pysqlite:///:memory:")
    monkeypatch.setattr(cli, "get_session_factory", lambda settings: session_factory, raising=False)
    monkeypatch.setattr(cli, "_load_run_once_securities", lambda session: securities, raising=False)


class _EdgarFiling:
    def obj(self):
        return {"value": 321.0}

    def xbrl(self):
        return None

    def sections(self):
        return []

    def parse(self):
        return None


class _BadEdgarFiling:
    def obj(self):
        return {"value": "not-a-number"}

    def xbrl(self):
        return None

    def sections(self):
        return []

    def parse(self):
        return None


def test_phase2_numeric_pipeline_persists_numeric_fact_with_evidence(monkeypatch):
    session_factory = _build_session_factory()

    security = SimpleNamespace(
        cik="0000320193",
        composite_figi="BBG000000001",
        ticker="ABC",
        active=True,
        delisted_utc=None,
    )

    accepted_at = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    calls: list[str] = []

    def _fake_fetch_filings_for_security(*, security, route, start_accepted_at):
        del security, start_accepted_at
        calls.append(route)
        if route != "issuer":
            return []

        return [
            FilingEnvelope(
                accession_no="0000320193-25-000101",
                cik="0000320193",
                form_type="10-K",
                accepted_at=accepted_at,
                filing=_EdgarFiling(),
            )
        ]

    _patch_runtime(monkeypatch, session_factory, [security])
    monkeypatch.setattr(cli, "fetch_filings_for_security", _fake_fetch_filings_for_security, raising=False)

    result = runner.invoke(app, ["run-once"])

    assert result.exit_code == 0
    assert calls == ["issuer", "owner", "holding"]

    with session_factory() as session:
        fact_count = session.scalar(
            select(func.count())
            .select_from(ExtractedFact)
            .where(ExtractedFact.accession_no == "0000320193-25-000101")
        )
        evidence_count = session.scalar(
            select(func.count())
            .select_from(ExtractionEvidence)
            .where(ExtractionEvidence.accession_no == "0000320193-25-000101")
        )
        log_count = session.scalar(
            select(func.count())
            .select_from(PipelineLog)
            .where(
                PipelineLog.accession_no == "0000320193-25-000101",
                PipelineLog.stage == "persist",
                PipelineLog.level == "INFO",
            )
        )

        total_revenue_fact = session.scalar(
            select(ExtractedFact).where(
                ExtractedFact.accession_no == "0000320193-25-000101",
                ExtractedFact.route == "issuer",
                ExtractedFact.field_name == "total_revenue",
            )
        )
        total_revenue_evidence = session.scalar(
            select(ExtractionEvidence).where(
                ExtractionEvidence.accession_no == "0000320193-25-000101",
                ExtractionEvidence.route == "issuer",
                ExtractionEvidence.field_name == "total_revenue",
            )
        )

        assert fact_count is not None
        assert evidence_count is not None
        assert log_count == 1
        assert total_revenue_fact is not None
        assert total_revenue_fact.value_numeric == 321.0
        assert total_revenue_evidence is not None
        assert total_revenue_evidence.normalized_value == "321.0"

        issuer_spec_count = len(
            [
                spec
                for spec in all_numeric_field_specs()
                if spec.route == "issuer" and "10-K" in spec.form_families
            ]
        )
        assert fact_count == issuer_spec_count
        assert evidence_count == issuer_spec_count


def test_phase2_numeric_pipeline_logs_extraction_error_code(monkeypatch):
    session_factory = _build_session_factory()

    security = SimpleNamespace(
        cik="0000789019",
        composite_figi="BBG000000002",
        ticker="XYZ",
        active=True,
        delisted_utc=None,
    )

    accepted_at = datetime(2025, 1, 16, 10, 0, tzinfo=timezone.utc)

    def _fake_fetch_filings_for_security(*, security, route, start_accepted_at):
        del security, start_accepted_at
        if route != "issuer":
            return []

        return [
            FilingEnvelope(
                accession_no="0000789019-25-000201",
                cik="0000789019",
                form_type="10-K",
                accepted_at=accepted_at,
                filing=_BadEdgarFiling(),
            )
        ]

    _patch_runtime(monkeypatch, session_factory, [security])
    monkeypatch.setattr(cli, "fetch_filings_for_security", _fake_fetch_filings_for_security, raising=False)

    result = runner.invoke(app, ["run-once"])

    assert result.exit_code == 0

    with session_factory() as session:
        error_log_count = session.scalar(
            select(func.count())
            .select_from(PipelineLog)
            .where(
                PipelineLog.accession_no == "0000789019-25-000201",
                PipelineLog.stage == "extract",
                PipelineLog.level == "ERROR",
                PipelineLog.error_type == "TYPE_MISMATCH",
            )
        )
        fact_count = session.scalar(
            select(func.count())
            .select_from(ExtractedFact)
            .where(ExtractedFact.accession_no == "0000789019-25-000201")
        )

        expected_error_count = len(
            [
                spec
                for spec in all_numeric_field_specs()
                if spec.route == "issuer" and "10-K" in spec.form_families
            ]
        )

        assert error_log_count == expected_error_count
        assert fact_count == 0


def test_phase2_numeric_pipeline_advances_watermark_on_all_error_filing(monkeypatch):
    from src.db.models import RouteWatermark

    session_factory = _build_session_factory()

    security = SimpleNamespace(
        cik="0000555555",
        composite_figi="BBG000000555",
        ticker="ERR",
        active=True,
        delisted_utc=None,
    )

    accepted_at = datetime(2025, 1, 17, 9, 0, tzinfo=timezone.utc)

    def _fake_fetch_filings_for_security(*, security, route, start_accepted_at):
        del security, start_accepted_at
        if route != "issuer":
            return []

        return [
            FilingEnvelope(
                accession_no="0000555555-25-000301",
                cik="0000555555",
                form_type="10-K",
                accepted_at=accepted_at,
                filing=_BadEdgarFiling(),
            )
        ]

    _patch_runtime(monkeypatch, session_factory, [security])
    monkeypatch.setattr(cli, "fetch_filings_for_security", _fake_fetch_filings_for_security, raising=False)

    result = runner.invoke(app, ["run-once"])

    assert result.exit_code == 0

    with session_factory() as session:
        watermark = session.scalar(
            select(RouteWatermark).where(
                RouteWatermark.cik == "0000555555",
                RouteWatermark.route == "issuer",
            )
        )

        assert watermark is not None
        assert _as_naive_utc(watermark.last_accepted_at) == _as_naive_utc(accepted_at)
