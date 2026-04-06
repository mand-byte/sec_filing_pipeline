from datetime import datetime, timezone
from types import SimpleNamespace


from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from typer.testing import CliRunner

import src.cli as cli
from src.cli import app
from src.db.base import Base
from src.db.models import ExtractedFact, ExtractionEvidence, FilingDocument, PipelineLog, ReviewTask
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


class _OwnerTextFiling:
    def obj(self):
        return None

    def xbrl(self):
        return None

    def sections(self):
        return {
            "Purpose of Transaction": "The reporting person seeks Board Seat.",
        }

    def parse(self):
        return "Purpose of Transaction: the reporting person seeks Board Seat."


class _OwnerTextNoWindowFiling:
    def obj(self):
        return None

    def xbrl(self):
        return None

    def sections(self):
        return {
            "Purpose of Transaction": "The filing discusses only generic narrative without stance keywords.",
        }

    def parse(self):
        return "Purpose of Transaction: generic narrative only."


class _OwnerTextActivistFiling:
    def __init__(self, phrase: str):
        self._phrase = phrase

    def obj(self):
        return None

    def xbrl(self):
        return None

    def sections(self):
        return {
            "Purpose of Transaction": f"The reporting person is {self._phrase}.",
        }

    def parse(self):
        return f"Purpose of Transaction: The reporting person is {self._phrase}."


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


def test_phase3_text_pipeline_persists_text_fact_evidence_and_review_task(monkeypatch):
    session_factory = _build_session_factory()

    security = SimpleNamespace(
        cik="0000123456",
        composite_figi="BBG000000123",
        ticker="TXT",
        active=True,
        delisted_utc=None,
    )

    accepted_at = datetime(2025, 1, 18, 10, 0, tzinfo=timezone.utc)

    def _fake_fetch_filings_for_security(*, security, route, start_accepted_at):
        del security, start_accepted_at
        if route != "owner":
            return []

        return [
            FilingEnvelope(
                accession_no="0000123456-25-000401",
                cik="0000123456",
                form_type="13D",
                accepted_at=accepted_at,
                filing=_OwnerTextFiling(),
            )
        ]

    _patch_runtime(monkeypatch, session_factory, [security])
    monkeypatch.setattr(cli, "fetch_filings_for_security", _fake_fetch_filings_for_security, raising=False)

    result = runner.invoke(app, ["run-once"])

    assert result.exit_code == 0

    with session_factory() as session:
        fact = session.scalar(
            select(ExtractedFact).where(
                ExtractedFact.accession_no == "0000123456-25-000401",
                ExtractedFact.route == "owner",
                ExtractedFact.field_name == "beneficial_ownership_intent_quant",
            )
        )
        evidence = session.scalar(
            select(ExtractionEvidence).where(
                ExtractionEvidence.accession_no == "0000123456-25-000401",
                ExtractionEvidence.route == "owner",
                ExtractionEvidence.field_name == "beneficial_ownership_intent_quant",
            )
        )
        review_task = session.scalar(
            select(ReviewTask).where(
                ReviewTask.accession_no == "0000123456-25-000401",
                ReviewTask.route == "owner",
                ReviewTask.field_name == "beneficial_ownership_intent_quant",
                ReviewTask.status == "open",
            )
        )

        assert fact is not None
        assert fact.value_text is not None
        assert "board seat" in fact.value_text.lower()
        assert evidence is not None
        assert evidence.locator_kind in {"section_window", "parse_text_window"}
        assert review_task is not None
        assert review_task.priority == "high"
        assert review_task.reason == "first_seen_for_issuer"


def test_phase3_text_pipeline_logs_text_extraction_error_code(monkeypatch):
    session_factory = _build_session_factory()

    security = SimpleNamespace(
        cik="0000654321",
        composite_figi="BBG000000321",
        ticker="TXTE",
        active=True,
        delisted_utc=None,
    )

    accepted_at = datetime(2025, 1, 19, 10, 0, tzinfo=timezone.utc)

    def _fake_fetch_filings_for_security(*, security, route, start_accepted_at):
        del security, start_accepted_at
        if route != "owner":
            return []

        return [
            FilingEnvelope(
                accession_no="0000654321-25-000501",
                cik="0000654321",
                form_type="13D",
                accepted_at=accepted_at,
                filing=_OwnerTextNoWindowFiling(),
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
                PipelineLog.accession_no == "0000654321-25-000501",
                PipelineLog.stage == "extract",
                PipelineLog.level == "ERROR",
                PipelineLog.message == "text field extraction failed",
                PipelineLog.error_type == "PATTERN_NOT_MATCHED",
            )
        )
        text_fact_count = session.scalar(
            select(func.count())
            .select_from(ExtractedFact)
            .where(
                ExtractedFact.accession_no == "0000654321-25-000501",
                ExtractedFact.route == "owner",
                ExtractedFact.field_name == "beneficial_ownership_intent_quant",
            )
        )

        assert error_log_count == 1
        assert text_fact_count == 0


def test_phase3_text_pipeline_review_gate_is_sequential_across_same_run(monkeypatch):
    session_factory = _build_session_factory()

    security = SimpleNamespace(
        cik="0000777777",
        composite_figi="BBG000000777",
        ticker="TXTSEQ",
        active=True,
        delisted_utc=None,
    )

    accepted_first = datetime(2025, 1, 20, 10, 0, tzinfo=timezone.utc)
    accepted_second = datetime(2025, 1, 20, 11, 0, tzinfo=timezone.utc)

    class _OwnerTextSecondTemplateFiling(_OwnerTextFiling):
        def sections(self):
            return [
                "Cover Page text only.",
                "Purpose of Transaction: The reporting person seeks Board Seat.",
            ]

    def _fake_fetch_filings_for_security(*, security, route, start_accepted_at):
        del security, start_accepted_at
        if route != "owner":
            return []

        return [
            FilingEnvelope(
                accession_no="0000777777-25-000601",
                cik="0000777777",
                form_type="13D",
                accepted_at=accepted_first,
                filing=_OwnerTextFiling(),
            ),
            FilingEnvelope(
                accession_no="0000777777-25-000602",
                cik="0000777777",
                form_type="13D",
                accepted_at=accepted_second,
                filing=_OwnerTextSecondTemplateFiling(),
            ),
        ]

    _patch_runtime(monkeypatch, session_factory, [security])
    monkeypatch.setattr(cli, "fetch_filings_for_security", _fake_fetch_filings_for_security, raising=False)

    result = runner.invoke(app, ["run-once"])

    assert result.exit_code == 0

    with session_factory() as session:
        first_task = session.scalar(
            select(ReviewTask).where(
                ReviewTask.accession_no == "0000777777-25-000601",
                ReviewTask.route == "owner",
                ReviewTask.field_name == "beneficial_ownership_intent_quant",
                ReviewTask.status == "open",
            )
        )
        second_task = session.scalar(
            select(ReviewTask).where(
                ReviewTask.accession_no == "0000777777-25-000602",
                ReviewTask.route == "owner",
                ReviewTask.field_name == "beneficial_ownership_intent_quant",
                ReviewTask.status == "open",
            )
        )

        assert first_task is not None
        assert first_task.reason == "first_seen_for_issuer"
        assert second_task is not None
        assert second_task.reason == "first_seen_template"


def test_phase3_text_pipeline_review_gate_deterministic_tie_break_with_same_timestamp(monkeypatch):
    session_factory = _build_session_factory()

    security = SimpleNamespace(
        cik="0000888888",
        composite_figi="BBG000000888",
        ticker="TXTTIE",
        active=True,
        delisted_utc=None,
    )

    accepted_at = datetime(2025, 1, 21, 10, 0, tzinfo=timezone.utc)

    class _OwnerTextSecondTemplateFiling(_OwnerTextFiling):
        def sections(self):
            return [
                "Cover Page text only.",
                "Purpose of Transaction: The reporting person seeks Board Seat.",
            ]

    def _fake_fetch_filings_for_security(*, security, route, start_accepted_at):
        del security, start_accepted_at
        if route != "owner":
            return []

        return [
            FilingEnvelope(
                accession_no="0000888888-25-000702",
                cik="0000888888",
                form_type="13D",
                accepted_at=accepted_at,
                filing=_OwnerTextSecondTemplateFiling(),
            ),
            FilingEnvelope(
                accession_no="0000888888-25-000701",
                cik="0000888888",
                form_type="13D",
                accepted_at=accepted_at,
                filing=_OwnerTextFiling(),
            ),
        ]

    _patch_runtime(monkeypatch, session_factory, [security])
    monkeypatch.setattr(cli, "fetch_filings_for_security", _fake_fetch_filings_for_security, raising=False)

    result = runner.invoke(app, ["run-once"])

    assert result.exit_code == 0

    with session_factory() as session:
        first_task = session.scalar(
            select(ReviewTask).where(
                ReviewTask.accession_no == "0000888888-25-000701",
                ReviewTask.route == "owner",
                ReviewTask.field_name == "beneficial_ownership_intent_quant",
                ReviewTask.status == "open",
            )
        )
        second_task = session.scalar(
            select(ReviewTask).where(
                ReviewTask.accession_no == "0000888888-25-000702",
                ReviewTask.route == "owner",
                ReviewTask.field_name == "beneficial_ownership_intent_quant",
                ReviewTask.status == "open",
            )
        )

        assert first_task is not None
        assert first_task.reason == "first_seen_for_issuer"
        assert second_task is not None
        assert second_task.reason == "first_seen_template"


def test_phase3_text_pipeline_review_gate_marks_outlier_vs_history_for_text_metric(monkeypatch):
    session_factory = _build_session_factory()

    security = SimpleNamespace(
        cik="0000999999",
        composite_figi="BBG000000999",
        ticker="TXTOUT",
        active=True,
        delisted_utc=None,
    )

    with session_factory() as session:
        seeded_created_at = datetime(2025, 1, 21, 8, 0, tzinfo=timezone.utc)
        seeded_payloads = [
            ("0000999999-25-000801", "activist"),
            ("0000999999-25-000802", "engaged"),
            ("0000999999-25-000803", "control"),
        ]
        for index, (accession, seeded_text) in enumerate(seeded_payloads):
            session.add(
                FilingDocument(
                    accession_no=accession,
                    cik="0000999999",
                    ticker="TXTOUT",
                    form_type="13D",
                    filed_at=None,
                    accepted_at=datetime(2025, 1, 21, 8, index, tzinfo=timezone.utc),
                    period_end=None,
                    is_amendment=False,
                    amendment_no=None,
                    created_at=seeded_created_at,
                )
            )
            session.add(
                ExtractedFact(
                    accession_no=accession,
                    route="owner",
                    field_name="beneficial_ownership_intent_quant",
                    value_numeric=None,
                    value_text=seeded_text,
                    value_json=None,
                    value_unit=None,
                    confidence=0.99,
                    extracted_at=seeded_created_at,
                )
            )
            session.add(
                ExtractionEvidence(
                    accession_no=accession,
                    route="owner",
                    field_name="beneficial_ownership_intent_quant",
                    locator_kind="section_window",
                    source_section="Purpose of Transaction",
                    source_item_no=None,
                    source_xpath="sections[Purpose of Transaction]",
                    xbrl_concept=None,
                    source_span="0:8",
                    raw_value=seeded_text,
                    normalized_value=seeded_text,
                    created_at=seeded_created_at,
                )
            )
        session.commit()

    accepted_at = datetime(2025, 1, 21, 10, 0, tzinfo=timezone.utc)

    def _fake_fetch_filings_for_security(*, security, route, start_accepted_at):
        del security, start_accepted_at
        if route != "owner":
            return []

        return [
            FilingEnvelope(
                accession_no="0000999999-25-000901",
                cik="0000999999",
                form_type="13D",
                accepted_at=accepted_at,
                filing=_OwnerTextActivistFiling("strategic alternatives"),
            )
        ]

    _patch_runtime(monkeypatch, session_factory, [security])
    monkeypatch.setattr(cli, "fetch_filings_for_security", _fake_fetch_filings_for_security, raising=False)

    result = runner.invoke(app, ["run-once"])

    assert result.exit_code == 0

    with session_factory() as session:
        outlier_task = session.scalar(
            select(ReviewTask).where(
                ReviewTask.accession_no == "0000999999-25-000901",
                ReviewTask.route == "owner",
                ReviewTask.field_name == "beneficial_ownership_intent_quant",
                ReviewTask.status == "open",
            )
        )

        assert outlier_task is not None
        assert outlier_task.reason == "outlier_vs_history"
