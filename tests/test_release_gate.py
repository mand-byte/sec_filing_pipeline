from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import src.cli as cli_module
from src.db.base import Base
from src.db.models import FilingAttempt, GoldenReviewPacket, PipelineLog, ReviewTask
from src.pipeline.offline_artifacts import write_run_artifacts
from src.pipeline.release_gates import evaluate_fix_once_release_gate
from src.pipeline.review.workflow import ReviewWorkflowService
from src.pipeline.runtime_verification import build_run_artifact_payloads
from src.pipeline.services import EvidenceInput, FactInput, PersistenceService
from src.pipeline.types import FilingRecord


runner = CliRunner()


def _session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False)


def _filing() -> FilingRecord:
    return FilingRecord(
        accession_no="0000000000-24-000050",
        cik="0000789019",
        ticker="MSFT",
        form_type="4",
        filed_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
        accepted_at=datetime(2024, 5, 2, tzinfo=timezone.utc),
        period_end=datetime(2024, 3, 31, tzinfo=timezone.utc),
        is_amendment=False,
        amendment_no=None,
    )


def _seed_open_review_task(session: Session) -> None:
    PersistenceService(session).persist_filing_bundle(
        filing=_filing(),
        route="owner",
        facts=[
            FactInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                value_numeric=100.0,
                confidence=0.49,
                review_reason="first_seen_template",
            )
        ],
        evidences=[
            EvidenceInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                locator_kind="obj",
                source_span="transactions[0].shares",
                source_locator_json='{"kind":"obj","path":"transactions[0].shares"}',
                source_heading_path_json='["Ownership Table"]',
                source_block_offsets_json='{"source_start":12,"source_end":17}',
                adequacy_signals_json='{"window_found":true,"span_policy_applied":false}',
                retry_history_json="[]",
                selection_trace_json='{"selected_value":"100"}',
                raw_value="100",
                normalized_value="100.0",
            )
        ],
    )


def _seed_closed_fix_once_task(session: Session) -> None:
    _seed_open_review_task(session)
    service = ReviewWorkflowService(session)
    task = service.list_tasks()[0]
    service.resolve_task(
        task_id=task.task_id,
        decision="corrected",
        reviewer="alice",
        error_code="unit_scaling",
        corrected_json=json.dumps({"value_numeric": 125.5, "value_unit": "shares"}),
    )


def _issuer_security_line_filing() -> FilingRecord:
    return FilingRecord(
        accession_no="0000000000-24-000051",
        cik="0000789019",
        ticker="MSFT",
        form_type="S-1",
        filed_at=datetime(2024, 5, 3, tzinfo=timezone.utc),
        accepted_at=datetime(2024, 5, 4, tzinfo=timezone.utc),
        period_end=datetime(2024, 3, 31, tzinfo=timezone.utc),
        is_amendment=False,
        amendment_no=None,
    )


def _seed_closed_security_line_fix_once_tasks(session: Session) -> None:
    PersistenceService(session).persist_filing_bundle(
        filing=_issuer_security_line_filing(),
        route="issuer",
        facts=[
            FactInput(
                field_name="offering_price_per_share",
                subject_key="security:1",
                value_numeric=10.0,
                confidence=0.49,
                review_reason="first_seen_template",
            ),
            FactInput(
                field_name="offering_price_per_share",
                subject_key="security:2",
                value_numeric=12.0,
                confidence=0.49,
                review_reason="first_seen_template",
            ),
        ],
        evidences=[
            EvidenceInput(
                field_name="offering_price_per_share",
                subject_key="security:1",
                locator_kind="section",
                source_span="Use of Proceeds:0:4",
                source_section="Use of Proceeds",
                raw_value="10.00",
                normalized_value="10.0",
            ),
            EvidenceInput(
                field_name="offering_price_per_share",
                subject_key="security:2",
                locator_kind="section",
                source_span="Use of Proceeds:10:14",
                source_section="Use of Proceeds",
                raw_value="12.00",
                normalized_value="12.0",
            ),
        ],
    )
    service = ReviewWorkflowService(session)
    tasks = sorted(service.list_tasks(route="issuer"), key=lambda task: task.subject_key)
    for task in tasks:
        service.resolve_task(
            task_id=task.task_id,
            decision="corrected",
            reviewer="alice",
            error_code="row_match_error",
            corrected_json=json.dumps({"value_numeric": 11.0}),
        )


def _seed_runtime_run(session: Session, *, base_dir: Path, run_id: str) -> None:
    now = datetime(2024, 5, 10, tzinfo=timezone.utc)
    session.add_all(
        [
            PipelineLog(
                run_id=run_id,
                route="issuer",
                cik="0000789019",
                accession_no="0000000000-24-000060",
                stage="persist",
                level="INFO",
                message="filing persisted",
                error_type=None,
                error_detail=None,
                created_at=now,
            ),
            FilingAttempt(
                run_id=run_id,
                route="issuer",
                accession_no="0000000000-24-000060",
                cik="0000789019",
                accepted_at=now,
                status="completed",
                error_type=None,
                error_detail=None,
                started_at=now,
                updated_at=now,
            ),
        ]
    )
    session.commit()
    summary, samples, diff_markdown = build_run_artifact_payloads(session=session, run_id=run_id)
    write_run_artifacts(
        base_dir=base_dir,
        run_id=run_id,
        summary=summary,
        by_field={},
        failures=[],
        candidates=samples,
        diff_markdown=diff_markdown,
    )


def test_release_gate_fails_when_open_review_tasks_exist(tmp_path: Path) -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_open_review_task(session)
        result = evaluate_fix_once_release_gate(session=session, output_dir=tmp_path)

    assert result.passed is False
    assert result.open_review_tasks == 1


def test_release_gate_exports_review_packets_and_passes_when_fix_once_chain_complete(tmp_path: Path) -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_closed_fix_once_task(session)
        result = evaluate_fix_once_release_gate(session=session, output_dir=tmp_path)

    assert result.passed is True
    assert result.open_review_tasks == 0
    assert result.resolved_fix_once_tasks == 1
    assert result.golden_review_packets == 1
    assert result.missing_review_packets == 0
    packet_dir = tmp_path / "review_regressions"
    assert packet_dir.exists()
    packet_files = list(packet_dir.iterdir())
    assert len(packet_files) == 1
    packet_payload = json.loads(packet_files[0].read_text(encoding="utf-8"))
    assert packet_payload["primary_evidence"]["source_heading_path_json"] == '["Ownership Table"]'
    assert packet_payload["primary_evidence"]["adequacy_signals_json"] == '{"window_found":true,"span_policy_applied":false}'
    assert packet_payload["primary_evidence"]["selection_trace_json"] == '{"selected_value":"100"}'
    assert (tmp_path / "summary.json").exists()


def test_release_gate_fails_when_fix_once_task_has_no_review_packet(tmp_path: Path) -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_closed_fix_once_task(session)
        session.query(GoldenReviewPacket).delete()
        session.commit()
        result = evaluate_fix_once_release_gate(session=session, output_dir=tmp_path)

    assert result.passed is False
    assert result.missing_review_packets == 1


def test_release_gate_fails_when_strict_summary_fails_threshold(tmp_path: Path) -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_closed_fix_once_task(session)

        strict_summary = tmp_path / "strict-summary.json"
        strict_summary.write_text(
            json.dumps(
                {
                    "run_id": "strict-run-001",
                    "selectors": {
                        "route": None,
                        "form_family": None,
                        "field_name": None,
                        "case_id": None,
                        "mode": None,
                    },
                    "metrics": {"passes_threshold": False},
                    "phase_gates": {"failed": 0},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        result = evaluate_fix_once_release_gate(
            session=session,
            output_dir=tmp_path / "gate-output",
            strict_summary_path=strict_summary,
        )

    assert result.passed is False
    assert result.evaluator_passes_threshold is False
    assert result.evaluator_failed_phase_gates == 0


def test_release_gate_fails_when_strict_summary_has_failed_phase_gates(tmp_path: Path) -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_closed_fix_once_task(session)

        strict_summary = tmp_path / "strict-summary.json"
        strict_summary.write_text(
            json.dumps(
                {
                    "run_id": "strict-run-002",
                    "selectors": {
                        "route": None,
                        "form_family": None,
                        "field_name": None,
                        "case_id": None,
                        "mode": None,
                    },
                    "metrics": {"passes_threshold": True},
                    "phase_gates": {"failed": 2},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        result = evaluate_fix_once_release_gate(
            session=session,
            output_dir=tmp_path / "gate-output",
            strict_summary_path=strict_summary,
        )

    assert result.passed is False
    assert result.evaluator_passes_threshold is True
    assert result.evaluator_failed_phase_gates == 2


def test_release_gate_preserves_security_line_subject_keys_in_exported_packets(tmp_path: Path) -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_closed_security_line_fix_once_tasks(session)
        result = evaluate_fix_once_release_gate(session=session, output_dir=tmp_path)

    assert result.passed is True
    assert result.resolved_fix_once_tasks == 2
    packet_dir = tmp_path / "review_regressions"
    packet_files = sorted(packet_dir.iterdir())
    assert len(packet_files) == 2
    assert [packet_file.name for packet_file in packet_files] == [
        "review-capture_1__manual-review_0000000000-24-000051__offering_price_per_share.json",
        "review-capture_2__manual-review_0000000000-24-000051__offering_price_per_share.json",
    ]
    payloads = [json.loads(packet_file.read_text(encoding="utf-8")) for packet_file in packet_files]
    assert sorted(payload["task"]["subject_key"] for payload in payloads) == ["security:1", "security:2"]


def test_cli_release_gate_reports_and_exits_nonzero_when_blocked(monkeypatch, tmp_path: Path) -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_open_review_task(session)

    monkeypatch.setattr(cli_module, "Settings", lambda: object())
    monkeypatch.setattr(cli_module, "get_session_factory", lambda settings: factory)

    result = runner.invoke(
        cli_module.app,
        ["release-gate", "--output-dir", str(tmp_path)],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert payload["open_review_tasks"] == 1


def test_cli_release_gate_reports_success_when_fix_once_chain_complete(monkeypatch, tmp_path: Path) -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_closed_fix_once_task(session)

    monkeypatch.setattr(cli_module, "Settings", lambda: object())
    monkeypatch.setattr(cli_module, "get_session_factory", lambda settings: factory)

    result = runner.invoke(
        cli_module.app,
        ["release-gate", "--output-dir", str(tmp_path)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["open_review_tasks"] == 0
    assert payload["golden_review_packets"] == 1
    assert (tmp_path / "review_regressions").exists()


def test_cli_release_gate_reports_strict_summary_failure(monkeypatch, tmp_path: Path) -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_closed_fix_once_task(session)

    strict_summary = tmp_path / "strict-summary.json"
    strict_summary.write_text(
        json.dumps(
            {
                "run_id": "strict-run-cli",
                "selectors": {
                    "route": None,
                    "form_family": None,
                    "field_name": None,
                    "case_id": None,
                    "mode": None,
                },
                "metrics": {"passes_threshold": False},
                "phase_gates": {"failed": 1},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli_module, "Settings", lambda: object())
    monkeypatch.setattr(cli_module, "get_session_factory", lambda settings: factory)

    result = runner.invoke(
        cli_module.app,
        ["release-gate", "--output-dir", str(tmp_path / "gate-output"), "--strict-summary", str(strict_summary)],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert payload["evaluator_passes_threshold"] is False
    assert payload["evaluator_failed_phase_gates"] == 1


def test_release_gate_rejects_filtered_strict_summary(tmp_path: Path) -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_closed_fix_once_task(session)

        strict_summary = tmp_path / "strict-summary.json"
        strict_summary.write_text(
            json.dumps(
                {
                    "run_id": "strict-run-filtered",
                    "selectors": {
                        "route": "issuer",
                        "form_family": None,
                        "field_name": None,
                        "case_id": None,
                        "mode": None,
                    },
                    "metrics": {"passes_threshold": True},
                    "phase_gates": {"failed": 0},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="strict summary must be unfiltered"):
            evaluate_fix_once_release_gate(
                session=session,
                output_dir=tmp_path / "gate-output",
                strict_summary_path=strict_summary,
            )


def test_release_gate_fails_when_any_of_multiple_strict_summaries_fail(tmp_path: Path) -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_closed_fix_once_task(session)

        passing_summary = tmp_path / "strict-summary-pass.json"
        passing_summary.write_text(
            json.dumps(
                {
                    "run_id": "strict-run-pass",
                    "selectors": {
                        "route": None,
                        "form_family": None,
                        "field_name": None,
                        "case_id": None,
                        "mode": None,
                    },
                    "metrics": {"passes_threshold": True},
                    "phase_gates": {"failed": 0},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        failing_summary = tmp_path / "strict-summary-fail.json"
        failing_summary.write_text(
            json.dumps(
                {
                    "run_id": "strict-run-fail",
                    "selectors": {
                        "route": None,
                        "form_family": None,
                        "field_name": None,
                        "case_id": None,
                        "mode": None,
                    },
                    "metrics": {"passes_threshold": False},
                    "phase_gates": {"failed": 1},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        result = evaluate_fix_once_release_gate(
            session=session,
            output_dir=tmp_path / "gate-output",
            strict_summary_paths=[passing_summary, failing_summary],
        )

    assert result.passed is False
    assert result.evaluator_passes_threshold is False
    assert result.evaluator_failed_phase_gates == 1
    assert result.evaluator_summary_path is None
    assert len(result.evaluator_summary_paths) == 2


def test_cli_release_gate_accepts_multiple_strict_summaries(monkeypatch, tmp_path: Path) -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_closed_fix_once_task(session)

    passing_summary = tmp_path / "strict-summary-pass.json"
    passing_summary.write_text(
        json.dumps(
            {
                "run_id": "strict-run-pass",
                "selectors": {
                    "route": None,
                    "form_family": None,
                    "field_name": None,
                    "case_id": None,
                    "mode": None,
                },
                "metrics": {"passes_threshold": True},
                "phase_gates": {"failed": 0},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    second_passing_summary = tmp_path / "strict-summary-pass-2.json"
    second_passing_summary.write_text(
        json.dumps(
            {
                "run_id": "strict-run-pass-2",
                "selectors": {
                    "route": None,
                    "form_family": None,
                    "field_name": None,
                    "case_id": None,
                    "mode": None,
                },
                "metrics": {"passes_threshold": True},
                "phase_gates": {"failed": 0},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli_module, "Settings", lambda: object())
    monkeypatch.setattr(cli_module, "get_session_factory", lambda settings: factory)

    result = runner.invoke(
        cli_module.app,
        [
            "release-gate",
            "--output-dir",
            str(tmp_path / "gate-output"),
            "--strict-summary",
            str(passing_summary),
            "--strict-summary",
            str(second_passing_summary),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["evaluator_summary_path"] is None
    assert len(payload["evaluator_summary_paths"]) == 2


def test_release_gate_fails_when_runtime_run_verification_fails(tmp_path: Path) -> None:
    factory = _session_factory()
    runtime_artifacts_dir = tmp_path / "runtime-artifacts"
    with factory() as session:
        _seed_closed_fix_once_task(session)
        _seed_runtime_run(session, base_dir=runtime_artifacts_dir, run_id="runtime-run-001")

        summary_path = runtime_artifacts_dir / "runtime-run-001" / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["metrics"]["total_logs"] = 999
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

        result = evaluate_fix_once_release_gate(
            session=session,
            output_dir=tmp_path / "gate-output",
            runtime_run_ids=["runtime-run-001"],
            runtime_artifacts_dir=runtime_artifacts_dir,
        )

    assert result.passed is False
    assert result.runtime_verified_runs == 1
    assert result.runtime_failed_runs == 1
    assert result.runtime_failure_details[0]["run_id"] == "runtime-run-001"


def test_release_gate_fails_when_runtime_run_has_error_logs_even_if_artifacts_match(tmp_path: Path) -> None:
    factory = _session_factory()
    runtime_artifacts_dir = tmp_path / "runtime-artifacts"
    with factory() as session:
        _seed_closed_fix_once_task(session)
        _seed_runtime_run(session, base_dir=runtime_artifacts_dir, run_id="runtime-run-errors")
        session.add(
            PipelineLog(
                run_id="runtime-run-errors",
                route="issuer",
                cik="0000789019",
                accession_no=None,
                stage="extract",
                level="ERROR",
                message="provider bundle build failed",
                error_type="RuntimeError",
                error_detail="boom",
                created_at=datetime(2024, 5, 10, tzinfo=timezone.utc),
            )
        )
        session.commit()
        summary, samples, diff_markdown = build_run_artifact_payloads(session=session, run_id="runtime-run-errors")
        write_run_artifacts(
            base_dir=runtime_artifacts_dir,
            run_id="runtime-run-errors",
            summary=summary,
            by_field={},
            failures=[sample for sample in samples if sample.get("level") == "ERROR"],
            candidates=samples,
            diff_markdown=diff_markdown,
        )
        result = evaluate_fix_once_release_gate(
            session=session,
            output_dir=tmp_path / "gate-output",
            runtime_run_ids=["runtime-run-errors"],
            runtime_artifacts_dir=runtime_artifacts_dir,
        )

    assert result.passed is False
    assert result.runtime_verified_runs == 1
    assert result.runtime_failed_runs == 1
    assert result.runtime_error_logs == 1
    assert result.runtime_blocking_error_logs == 1
    assert result.runtime_failure_details[0]["run_id"] == "runtime-run-errors"
    assert result.runtime_failure_details[0]["error_logs"] == 1


def test_release_gate_ignores_non_blocking_text_field_extraction_error_logs(tmp_path: Path) -> None:
    factory = _session_factory()
    runtime_artifacts_dir = tmp_path / "runtime-artifacts"
    with factory() as session:
        _seed_closed_fix_once_task(session)
        _seed_runtime_run(session, base_dir=runtime_artifacts_dir, run_id="runtime-run-text-errors")
        session.add(
            PipelineLog(
                run_id="runtime-run-text-errors",
                route="issuer",
                cik="0000789019",
                accession_no="0000000000-24-000060",
                stage="extract",
                level="ERROR",
                message="text field extraction failed",
                error_type="SPAN_POLICY_FAILED",
                error_detail=None,
                created_at=datetime(2024, 5, 10, tzinfo=timezone.utc),
            )
        )
        session.commit()
        summary, samples, diff_markdown = build_run_artifact_payloads(session=session, run_id="runtime-run-text-errors")
        write_run_artifacts(
            base_dir=runtime_artifacts_dir,
            run_id="runtime-run-text-errors",
            summary=summary,
            by_field={},
            failures=[sample for sample in samples if sample.get("level") == "ERROR"],
            candidates=samples,
            diff_markdown=diff_markdown,
        )
        result = evaluate_fix_once_release_gate(
            session=session,
            output_dir=tmp_path / "gate-output",
            runtime_run_ids=["runtime-run-text-errors"],
            runtime_artifacts_dir=runtime_artifacts_dir,
        )

    assert result.passed is True
    assert result.runtime_verified_runs == 1
    assert result.runtime_failed_runs == 0
    assert result.runtime_error_logs == 1
    assert result.runtime_blocking_error_logs == 0


def test_release_gate_ignores_non_blocking_owner_no_rows_errors(tmp_path: Path) -> None:
    factory = _session_factory()
    runtime_artifacts_dir = tmp_path / "runtime-artifacts"
    with factory() as session:
        _seed_closed_fix_once_task(session)
        _seed_runtime_run(session, base_dir=runtime_artifacts_dir, run_id="runtime-run-owner-no-rows")
        session.add(
            PipelineLog(
                run_id="runtime-run-owner-no-rows",
                route="owner",
                cik="0000789019",
                accession_no="0000000000-24-000060",
                stage="extract",
                level="ERROR",
                message="owner ownership extracted no rows",
                error_type="NO_OWNER_ROWS_EXTRACTED",
                error_detail=None,
                created_at=datetime(2024, 5, 10, tzinfo=timezone.utc),
            )
        )
        session.commit()
        summary, samples, diff_markdown = build_run_artifact_payloads(session=session, run_id="runtime-run-owner-no-rows")
        write_run_artifacts(
            base_dir=runtime_artifacts_dir,
            run_id="runtime-run-owner-no-rows",
            summary=summary,
            by_field={},
            failures=[sample for sample in samples if sample.get("level") == "ERROR"],
            candidates=samples,
            diff_markdown=diff_markdown,
        )
        result = evaluate_fix_once_release_gate(
            session=session,
            output_dir=tmp_path / "gate-output",
            runtime_run_ids=["runtime-run-owner-no-rows"],
            runtime_artifacts_dir=runtime_artifacts_dir,
        )

    assert result.passed is True
    assert result.runtime_error_logs == 1
    assert result.runtime_blocking_error_logs == 0


def test_cli_release_gate_accepts_runtime_run_ids(monkeypatch, tmp_path: Path) -> None:
    factory = _session_factory()
    runtime_artifacts_dir = tmp_path / "runtime-artifacts"
    with factory() as session:
        _seed_closed_fix_once_task(session)
        _seed_runtime_run(session, base_dir=runtime_artifacts_dir, run_id="runtime-run-002")

    monkeypatch.setattr(cli_module, "Settings", lambda: object())
    monkeypatch.setattr(cli_module, "get_session_factory", lambda settings: factory)

    result = runner.invoke(
        cli_module.app,
        [
            "release-gate",
            "--output-dir",
            str(tmp_path / "gate-output"),
            "--runtime-run-id",
            "runtime-run-002",
            "--runtime-artifacts-dir",
            str(runtime_artifacts_dir),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["runtime_verified_runs"] == 1
    assert payload["runtime_failed_runs"] == 0


def test_release_gate_accepts_runtime_cohort_manifest(tmp_path: Path) -> None:
    factory = _session_factory()
    runtime_artifacts_dir = tmp_path / "runtime-artifacts"
    cohort_manifest = runtime_artifacts_dir / "cohorts" / "phase1__manifest.json"
    cohort_manifest.parent.mkdir(parents=True, exist_ok=True)
    with factory() as session:
        _seed_closed_fix_once_task(session)
        _seed_runtime_run(session, base_dir=runtime_artifacts_dir, run_id="runtime-run-003")
        cohort_manifest.write_text(
            json.dumps(
                {
                    "cohort_name": "phase1_deterministic",
                    "route_runs": [{"route": "issuer", "run_id": "runtime-run-003"}],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        result = evaluate_fix_once_release_gate(
            session=session,
            output_dir=tmp_path / "gate-output",
            runtime_cohort_manifests=[cohort_manifest],
            runtime_artifacts_dir=runtime_artifacts_dir,
        )

    assert result.passed is True
    assert result.runtime_verified_runs == 1
    assert result.runtime_failed_runs == 0


def test_cli_release_gate_accepts_runtime_cohort_manifest(monkeypatch, tmp_path: Path) -> None:
    factory = _session_factory()
    runtime_artifacts_dir = tmp_path / "runtime-artifacts"
    cohort_manifest = runtime_artifacts_dir / "cohorts" / "phase1__manifest.json"
    cohort_manifest.parent.mkdir(parents=True, exist_ok=True)
    with factory() as session:
        _seed_closed_fix_once_task(session)
        _seed_runtime_run(session, base_dir=runtime_artifacts_dir, run_id="runtime-run-004")
        cohort_manifest.write_text(
            json.dumps(
                {
                    "cohort_name": "phase1_deterministic",
                    "route_runs": [{"route": "issuer", "run_id": "runtime-run-004"}],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(cli_module, "Settings", lambda: object())
    monkeypatch.setattr(cli_module, "get_session_factory", lambda settings: factory)

    result = runner.invoke(
        cli_module.app,
        [
            "release-gate",
            "--output-dir",
            str(tmp_path / "gate-output"),
            "--runtime-cohort-manifest",
            str(cohort_manifest),
            "--runtime-artifacts-dir",
            str(runtime_artifacts_dir),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["runtime_verified_runs"] == 1
