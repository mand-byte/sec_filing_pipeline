from __future__ import annotations

from datetime import date
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from typer.testing import CliRunner

import src.cli as cli_module
from src.db.base import Base
from src.db.models import FilingAttempt, PipelineLog, RouteWatermark
from src.pipeline.route_runtime import FilingBundle
from src.pipeline.services import EvidenceInput, FactInput
from src.pipeline.types import FilingRecord


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False)()


def _session_factory(db_path: Path):
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False)


def _filing(accession_no: str, accepted_at: datetime) -> FilingRecord:
    return FilingRecord(
        accession_no=accession_no,
        cik="0000789019",
        ticker="MSFT",
        form_type="4",
        filed_at=None,
        accepted_at=accepted_at,
        period_end=None,
        is_amendment=False,
        amendment_no=None,
    )


runner = CliRunner()


def test_build_run_artifact_payloads_includes_structured_filing_attempt_coverage() -> None:
    session = _session()
    now = datetime(2024, 5, 1, tzinfo=timezone.utc)

    session.add_all(
        [
            PipelineLog(
                run_id="run-001",
                route="issuer",
                cik="0000789019",
                accession_no="0000000000-24-000001",
                stage="persist",
                level="INFO",
                message="filing persisted",
                error_type=None,
                error_detail=None,
                created_at=now,
            ),
            PipelineLog(
                run_id="run-001",
                route="owner",
                cik="0000789019",
                accession_no="0000000000-24-000002",
                stage="persist",
                level="ERROR",
                message="filing persistence failed",
                error_type="RuntimeError",
                error_detail="boom",
                created_at=now,
            ),
            FilingAttempt(
                run_id="run-001",
                route="issuer",
                accession_no="0000000000-24-000001",
                cik="0000789019",
                accepted_at=now,
                status="completed",
                error_type=None,
                error_detail=None,
                started_at=now,
                updated_at=now,
            ),
            FilingAttempt(
                run_id="run-001",
                route="owner",
                accession_no="0000000000-24-000002",
                cik="0000789019",
                accepted_at=now,
                status="failed",
                error_type="RuntimeError",
                error_detail="boom",
                started_at=now,
                updated_at=now,
            ),
        ]
    )
    session.commit()

    summary, samples, diff_markdown = cli_module.build_run_artifact_payloads(session=session, run_id="run-001")

    assert summary["coverage"]["routes"] == {"issuer": 1}
    assert summary["coverage"]["filing_attempts"]["total"] == 2
    assert summary["coverage"]["filing_attempts"]["by_status"] == {"completed": 1, "failed": 1}
    assert summary["coverage"]["filing_attempts"]["by_route"] == {
        "issuer": {"completed": 1},
        "owner": {"failed": 1},
    }
    assert summary["errors"]["distribution"] == {"RuntimeError": 1}
    assert summary["metrics"]["total_logs"] == 2
    assert summary["metrics"]["total_filing_attempts"] == 2
    assert len(samples) == 2
    assert diff_markdown.startswith("# Diff")


def test_run_once_pipeline_writes_runtime_artifacts_from_db_backed_route_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    factory = _session_factory(tmp_path / "run_artifacts.db")
    first_accepted_at = datetime(2024, 5, 1, tzinfo=timezone.utc)
    second_accepted_at = datetime(2024, 5, 2, tzinfo=timezone.utc)
    valid_bundle = FilingBundle(
        filing=_filing("0000000000-24-000100", first_accepted_at),
        facts=[
            FactInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                value_numeric=100.0,
                confidence=0.99,
            )
        ],
        evidences=[
            EvidenceInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                locator_kind="obj",
                source_span="transactions[0].shares",
                raw_value="100",
                normalized_value="100.0",
            )
        ],
    )
    failing_bundle = FilingBundle(
        filing=_filing("0000000000-24-000101", second_accepted_at),
        facts=[
            FactInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                value_numeric=200.0,
                confidence=0.99,
            )
        ],
        evidences=[],
    )
    security = SimpleNamespace(
        cik="0000789019",
        ticker="MSFT",
        active=True,
        composite_figi="FIGI1",
        delisted_utc=None,
        filing_bundles_by_route={"issuer": [valid_bundle, failing_bundle]},
    )

    monkeypatch.setattr(
        cli_module,
        "Settings",
        lambda: SimpleNamespace(
            start_date=date(2024, 1, 1),
            write_offline_artifacts=True,
            offline_artifacts_dir=tmp_path / "artifacts",
        ),
    )
    monkeypatch.setattr(cli_module, "get_session_factory", lambda settings: factory)
    monkeypatch.setattr(cli_module, "_load_run_once_securities", lambda session, settings: [security])
    monkeypatch.setattr(cli_module, "make_run_id", lambda: "run-artifacts-db-backed")

    cli_module._run_once_pipeline(route="issuer")

    run_dir = tmp_path / "artifacts" / "run-artifacts-db-backed"
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    failures = (run_dir / "failures.ndjson").read_text(encoding="utf-8").strip().splitlines()

    assert summary["coverage"]["routes"] == {"issuer": 1}
    assert summary["coverage"]["filing_attempts"]["total"] == 2
    assert summary["coverage"]["filing_attempts"]["by_status"] == {"completed": 1, "failed": 1}
    assert summary["errors"]["distribution"] == {"ValueError": 1}
    assert len(failures) == 1

    with factory() as session:
        attempts = session.query(FilingAttempt).order_by(FilingAttempt.id.asc()).all()
        logs = session.query(PipelineLog).order_by(PipelineLog.id.asc()).all()
        watermark = session.query(RouteWatermark).one()

    assert [attempt.status for attempt in attempts] == ["completed", "failed"]
    assert [log.message for log in logs] == [
        "filing persisted",
        "filing persistence failed",
        "route processed: eligible=2 persisted=1 failed=1 skipped_before_watermark=0 skipped_ineligible=0",
    ]
    assert watermark.last_accepted_at == first_accepted_at.replace(tzinfo=None)


def test_cli_run_once_persists_db_state_and_artifacts_end_to_end(tmp_path: Path, monkeypatch) -> None:
    factory = _session_factory(tmp_path / "run_once_cli.db")
    accepted_at = datetime(2024, 5, 8, tzinfo=timezone.utc)
    bundle = FilingBundle(
        filing=_filing("0000000000-24-000102", accepted_at),
        facts=[
            FactInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                value_numeric=150.0,
                confidence=0.99,
            )
        ],
        evidences=[
            EvidenceInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                locator_kind="obj",
                source_span="transactions[0].shares",
                raw_value="150",
                normalized_value="150.0",
            )
        ],
    )
    security = SimpleNamespace(
        cik="0000789019",
        ticker="MSFT",
        active=True,
        composite_figi="FIGI1",
        delisted_utc=None,
        filing_bundles_by_route={"issuer": [bundle]},
    )

    monkeypatch.setattr(
        cli_module,
        "Settings",
        lambda: SimpleNamespace(
            start_date=date(2024, 1, 1),
            write_offline_artifacts=True,
            offline_artifacts_dir=tmp_path / "artifacts",
        ),
    )
    monkeypatch.setattr(cli_module, "get_session_factory", lambda settings: factory)
    monkeypatch.setattr(cli_module, "_load_run_once_securities", lambda session, settings: [security])
    monkeypatch.setattr(cli_module, "make_run_id", lambda: "run-once-cli-db-backed")

    result = runner.invoke(cli_module.app, ["run-once", "--route", "issuer"])

    assert result.exit_code == 0
    assert "runtime run_id: run-once-cli-db-backed" in result.stdout
    assert "route order: issuer" in result.stdout

    run_dir = tmp_path / "artifacts" / "run-once-cli-db-backed"
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

    with factory() as session:
        attempts = session.query(FilingAttempt).order_by(FilingAttempt.id.asc()).all()
        logs = session.query(PipelineLog).order_by(PipelineLog.id.asc()).all()
        watermark = session.query(RouteWatermark).one()

    assert summary["coverage"]["filing_attempts"]["by_status"] == {"completed": 1}
    assert [attempt.status for attempt in attempts] == ["completed"]
    assert [log.message for log in logs] == [
        "filing persisted",
        "route processed: eligible=1 persisted=1 failed=0 skipped_before_watermark=0 skipped_ineligible=0",
    ]
    assert watermark.last_accepted_at == accepted_at.replace(tzinfo=None)


def test_verify_runtime_run_confirms_artifacts_match_db(tmp_path: Path, monkeypatch) -> None:
    factory = _session_factory(tmp_path / "verify_run_cli.db")
    accepted_at = datetime(2024, 5, 8, tzinfo=timezone.utc)
    bundle = FilingBundle(
        filing=_filing("0000000000-24-000103", accepted_at),
        facts=[
            FactInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                value_numeric=175.0,
                confidence=0.99,
            )
        ],
        evidences=[
            EvidenceInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                locator_kind="obj",
                source_span="transactions[0].shares",
                raw_value="175",
                normalized_value="175.0",
            )
        ],
    )
    security = SimpleNamespace(
        cik="0000789019",
        ticker="MSFT",
        active=True,
        composite_figi="FIGI1",
        delisted_utc=None,
        filing_bundles_by_route={"issuer": [bundle]},
    )

    monkeypatch.setattr(
        cli_module,
        "Settings",
        lambda: SimpleNamespace(
            start_date=date(2024, 1, 1),
            write_offline_artifacts=True,
            offline_artifacts_dir=tmp_path / "artifacts",
        ),
    )
    monkeypatch.setattr(cli_module, "get_session_factory", lambda settings: factory)
    monkeypatch.setattr(cli_module, "_load_run_once_securities", lambda session, settings: [security])
    monkeypatch.setattr(cli_module, "make_run_id", lambda: "verify-runtime-run-ok")

    run_result = runner.invoke(cli_module.app, ["run-once", "--route", "issuer"])
    assert run_result.exit_code == 0

    verify_result = runner.invoke(
        cli_module.app,
        ["verify-runtime-run", "--run-id", "verify-runtime-run-ok"],
    )

    assert verify_result.exit_code == 0
    payload = json.loads(verify_result.stdout)
    assert payload["passed"] is True
    assert payload["mismatches"] == []
    assert payload["db_summary"]["coverage"]["filing_attempts"]["by_status"] == {"completed": 1}


def test_verify_runtime_run_reports_artifact_summary_drift(tmp_path: Path, monkeypatch) -> None:
    factory = _session_factory(tmp_path / "verify_run_cli_drift.db")
    accepted_at = datetime(2024, 5, 8, tzinfo=timezone.utc)
    bundle = FilingBundle(
        filing=_filing("0000000000-24-000104", accepted_at),
        facts=[
            FactInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                value_numeric=180.0,
                confidence=0.99,
            )
        ],
        evidences=[
            EvidenceInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                locator_kind="obj",
                source_span="transactions[0].shares",
                raw_value="180",
                normalized_value="180.0",
            )
        ],
    )
    security = SimpleNamespace(
        cik="0000789019",
        ticker="MSFT",
        active=True,
        composite_figi="FIGI1",
        delisted_utc=None,
        filing_bundles_by_route={"issuer": [bundle]},
    )

    monkeypatch.setattr(
        cli_module,
        "Settings",
        lambda: SimpleNamespace(
            start_date=date(2024, 1, 1),
            write_offline_artifacts=True,
            offline_artifacts_dir=tmp_path / "artifacts",
        ),
    )
    monkeypatch.setattr(cli_module, "get_session_factory", lambda settings: factory)
    monkeypatch.setattr(cli_module, "_load_run_once_securities", lambda session, settings: [security])
    monkeypatch.setattr(cli_module, "make_run_id", lambda: "verify-runtime-run-drift")

    run_result = runner.invoke(cli_module.app, ["run-once", "--route", "issuer"])
    assert run_result.exit_code == 0

    run_dir = tmp_path / "artifacts" / "verify-runtime-run-drift"
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    summary["metrics"]["total_logs"] = 999
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    verify_result = runner.invoke(
        cli_module.app,
        ["verify-runtime-run", "--run-id", "verify-runtime-run-drift"],
    )

    assert verify_result.exit_code == 1
    payload = json.loads(verify_result.stdout)
    assert payload["passed"] is False
    assert "summary.json does not match DB-derived summary" in payload["mismatches"]
