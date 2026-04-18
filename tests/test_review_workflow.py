from __future__ import annotations

import json
from datetime import datetime, timezone

from typer.testing import CliRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import src.cli as cli_module
from src.db.base import Base
from src.db.models import (
    GoldenCase,
    GoldenEvalRun,
    GoldenReviewPacket,
    GoldenSubject,
    GoldenTruth,
    ReviewDecision,
    ReviewTask,
)
from src.pipeline.result_store import load_parsed_value
from src.pipeline.review.workflow import ReviewWorkflowService
from src.pipeline.review.error_codes import normalize_review_error_code
from src.pipeline.services import EvidenceInput, FactInput, PersistenceService
from src.pipeline.types import FilingRecord


runner = CliRunner()


def _session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False)


def _filing() -> FilingRecord:
    return FilingRecord(
        accession_no="0000000000-24-000020",
        cik="0000789019",
        ticker="MSFT",
        form_type="4",
        filed_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
        accepted_at=datetime(2024, 5, 2, tzinfo=timezone.utc),
        period_end=datetime(2024, 3, 31, tzinfo=timezone.utc),
        is_amendment=False,
        amendment_no=None,
    )


def _seed_review_task(session: Session) -> None:
    service = PersistenceService(session)
    service.persist_filing_bundle(
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


def _issuer_security_line_filing() -> FilingRecord:
    return FilingRecord(
        accession_no="0000000000-24-000021",
        cik="0000789019",
        ticker="MSFT",
        form_type="S-1",
        filed_at=datetime(2024, 5, 3, tzinfo=timezone.utc),
        accepted_at=datetime(2024, 5, 4, tzinfo=timezone.utc),
        period_end=datetime(2024, 3, 31, tzinfo=timezone.utc),
        is_amendment=False,
        amendment_no=None,
    )


def _seed_security_line_review_tasks(session: Session) -> None:
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


def test_review_workflow_service_lists_and_shows_task_detail() -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_review_task(session)

    with factory() as session:
        service = ReviewWorkflowService(session)
        tasks = service.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].subject_key == "txn:1"

        detail = service.get_task_detail(task_id=tasks[0].task_id)
        assert detail.fact is not None
        assert detail.primary_evidence is not None
        assert detail.primary_evidence["source_span"] == "transactions[0].shares"
        assert detail.primary_evidence["source_locator_json"] == '{"kind":"obj","path":"transactions[0].shares"}'
        assert detail.primary_evidence["source_heading_path_json"] == '["Ownership Table"]'
        assert detail.primary_evidence["source_block_offsets_json"] == '{"source_start":12,"source_end":17}'
        assert detail.primary_evidence["adequacy_signals_json"] == '{"window_found":true,"span_policy_applied":false}'
        assert detail.primary_evidence["retry_history_json"] == "[]"


def test_review_workflow_service_assigns_task_and_persists_trimmed_assignee() -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_review_task(session)

    with factory() as session:
        service = ReviewWorkflowService(session)
        task = service.list_tasks()[0]
        summary = service.assign_task(task_id=task.task_id, assignee="  alice  ")
        assert summary.assignee == "alice"

    with factory() as session:
        detail = ReviewWorkflowService(session).get_task_detail(task_id=task.task_id)
        assert detail.task.assignee == "alice"


def test_review_workflow_service_corrected_updates_fact_and_persists_decision() -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_review_task(session)

    with factory() as session:
        service = ReviewWorkflowService(session)
        task = service.list_tasks()[0]
        service.assign_task(task_id=task.task_id, assignee="alice")
        updated = service.resolve_task(
            task_id=task.task_id,
            decision="corrected",
            reviewer="  alice  ",
            error_code="unit_scaling",
            corrected_json=json.dumps({"value_numeric": 125.5, "value_unit": "shares"}),
            comment="corrected transaction size",
        )
        assert updated.status == "corrected"

    with factory() as session:
        fact = load_parsed_value(
            session=session,
            accession_no="0000000000-24-000020",
            route="owner",
            field_name="shares_acquired_or_disposed",
            subject_key="txn:1",
        )
        decision = session.query(ReviewDecision).one()
        task = session.query(ReviewTask).one()
        golden_case = session.query(GoldenCase).one()
        golden_subject = session.query(GoldenSubject).one()
        golden_truth = session.query(GoldenTruth).one()
        golden_run = session.query(GoldenEvalRun).one()
        golden_packet = session.query(GoldenReviewPacket).one()
        assert fact is not None
        assert fact.value_numeric == 125.5
        assert fact.value_unit is None
        assert fact.confidence is None
        assert decision.decision == "CORRECTED"
        assert decision.reviewer == "alice"
        assert decision.error_code == "unit_scaling"
        assert task.status == "corrected"
        assert task.assignee == "alice"
        assert golden_case.case_id == "manual-review::0000000000-24-000020"
        assert golden_subject.subject_key == "txn:1"
        assert golden_subject.subject_type == "transaction_row"
        assert golden_truth.field_name == "shares_acquired_or_disposed"
        assert float(golden_truth.value_numeric) == 125.5
        assert golden_truth.truth_source == "manual_review"
        assert golden_run.run_id == f"review-capture::{task.task_id}"
        assert "unit_scaling" in golden_packet.packet_json
        assert '"source_heading_path_json": "[\\"Ownership Table\\"]"' in golden_packet.packet_json
        assert '"adequacy_signals_json": "{\\"window_found\\":true,\\"span_policy_applied\\":false}"' in golden_packet.packet_json
        assert '"selection_trace_json": "{\\"selected_value\\":\\"100\\"}"' in golden_packet.packet_json


def test_review_workflow_service_reject_removes_fact() -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_review_task(session)

    with factory() as session:
        service = ReviewWorkflowService(session)
        task = service.list_tasks()[0]
        updated = service.resolve_task(
            task_id=task.task_id,
            decision="reject",
            reviewer="bob",
            error_code="locator_miss",
            comment="bad parse",
        )
        assert updated.status == "reject"

    with factory() as session:
        assert load_parsed_value(
            session=session,
            accession_no="0000000000-24-000020",
            route="owner",
            field_name="shares_acquired_or_disposed",
            subject_key="txn:1",
        ) is None
        decision = session.query(ReviewDecision).one()
        golden_case = session.query(GoldenCase).one()
        golden_subject = session.query(GoldenSubject).one()
        golden_packet = session.query(GoldenReviewPacket).one()
        assert decision.decision == "REJECT"
        assert decision.error_code == "locator_miss"
        assert golden_case.case_id == "manual-review::0000000000-24-000020"
        assert golden_subject.subject_key == "txn:1"
        assert "locator_miss" in golden_packet.packet_json
        assert '"source_heading_path_json": "[\\"Ownership Table\\"]"' in golden_packet.packet_json
        assert '"selection_trace_json": "{\\"selected_value\\":\\"100\\"}"' in golden_packet.packet_json
        assert session.query(GoldenTruth).all() == []


def test_review_workflow_service_not_applicable_captures_fix_once_regression_seed() -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_review_task(session)

    with factory() as session:
        service = ReviewWorkflowService(session)
        task = service.list_tasks()[0]
        updated = service.resolve_task(
            task_id=task.task_id,
            decision="not_applicable",
            reviewer="bob",
            error_code="field_not_found",
            comment="field does not apply to this filing",
        )
        assert updated.status == "not_applicable"

    with factory() as session:
        assert load_parsed_value(
            session=session,
            accession_no="0000000000-24-000020",
            route="owner",
            field_name="shares_acquired_or_disposed",
            subject_key="txn:1",
        ) is None
        decision = session.query(ReviewDecision).one()
        golden_truth = session.query(GoldenTruth).one()
        golden_packet = session.query(GoldenReviewPacket).one()
        assert decision.decision == "NOT_APPLICABLE"
        assert decision.error_code == "field_not_found"
        assert golden_truth.is_applicable is False
        assert golden_truth.value_numeric is None
        assert golden_truth.value_text is None
        assert '"decision": "not_applicable"' in golden_packet.packet_json
        assert '"error_code": "field_not_found"' in golden_packet.packet_json
        assert '"source_heading_path_json": "[\\"Ownership Table\\"]"' in golden_packet.packet_json
        assert '"selection_trace_json": "{\\"selected_value\\":\\"100\\"}"' in golden_packet.packet_json


def test_review_workflow_service_rejects_non_accept_without_error_code() -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_review_task(session)

    with factory() as session:
        service = ReviewWorkflowService(session)
        task = service.list_tasks()[0]
        try:
            service.resolve_task(
                task_id=task.task_id,
                decision="reject",
                reviewer="bob",
            )
        except Exception as exc:
            assert "error-code" in str(exc)
        else:  # pragma: no cover - defensive branch
            raise AssertionError("expected missing error_code to fail")


def test_review_workflow_service_requires_non_blank_reviewer() -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_review_task(session)

    with factory() as session:
        service = ReviewWorkflowService(session)
        task = service.list_tasks()[0]
        try:
            service.resolve_task(
                task_id=task.task_id,
                decision="accept",
                reviewer="   ",
            )
        except Exception as exc:
            assert "reviewer is required" in str(exc)
        else:  # pragma: no cover - defensive branch
            raise AssertionError("expected blank reviewer to fail")

    with factory() as session:
        task = session.query(ReviewTask).one()
        assert task.status == "open"
        assert task.assignee is None
        assert session.query(ReviewDecision).count() == 0


def test_review_workflow_service_rejects_unknown_error_code() -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_review_task(session)

    with factory() as session:
        service = ReviewWorkflowService(session)
        task = service.list_tasks()[0]
        try:
            service.resolve_task(
                task_id=task.task_id,
                decision="reject",
                reviewer="bob",
                error_code="freeform typo code",
            )
        except Exception as exc:
            assert "error_code must be one of:" in str(exc)
        else:  # pragma: no cover - defensive branch
            raise AssertionError("expected invalid error_code to fail")


def test_review_workflow_preserves_security_line_subject_keys_for_filing_subject_type() -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_security_line_review_tasks(session)

    with factory() as session:
        service = ReviewWorkflowService(session)
        tasks = sorted(service.list_tasks(route="issuer"), key=lambda task: task.subject_key)
        assert [task.subject_key for task in tasks] == ["security:1", "security:2"]
        for task in tasks:
            service.resolve_task(
                task_id=task.task_id,
                decision="corrected",
                reviewer="alice",
                error_code="row_match_error",
                corrected_json=json.dumps({"value_numeric": 11.0}),
            )

    with factory() as session:
        subjects = session.query(GoldenSubject).order_by(GoldenSubject.subject_key.asc()).all()
        truths = session.query(GoldenTruth).order_by(GoldenTruth.subject_id.asc()).all()

        assert [subject.subject_key for subject in subjects] == ["security:1", "security:2"]
        assert {subject.subject_type for subject in subjects} == {"filing"}
        assert len(truths) == 2


def test_normalize_review_error_code_accepts_runtime_text_failures() -> None:
    assert normalize_review_error_code("window-not-found") == "window_not_found"
    assert normalize_review_error_code("multiple_candidates") == "multiple_candidates"
    assert normalize_review_error_code("QA_FAILED") == "qa_failed"
    assert normalize_review_error_code("span-policy-failed") == "span_policy_failed"
    assert normalize_review_error_code("field_not_found") == "field_not_found"


def test_cli_review_commands_operate_on_seeded_queue(monkeypatch) -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_review_task(session)

    monkeypatch.setattr(cli_module, "Settings", lambda: object())
    monkeypatch.setattr(cli_module, "get_session_factory", lambda settings: factory)

    list_result = runner.invoke(cli_module.app, ["review-list"])
    assert list_result.exit_code == 0
    payload = json.loads(list_result.stdout)
    assert len(payload) == 1
    task_id = payload[0]["task_id"]

    show_result = runner.invoke(cli_module.app, ["review-show", str(task_id)])
    assert show_result.exit_code == 0
    detail = json.loads(show_result.stdout)
    assert detail["task"]["subject_key"] == "txn:1"
    assert detail["primary_evidence"]["source_span"] == "transactions[0].shares"

    resolve_result = runner.invoke(
        cli_module.app,
        [
            "review-resolve",
            str(task_id),
            "--decision",
            "corrected",
            "--reviewer",
            "carol",
            "--error-code",
            "row_match_error",
            "--corrected-json",
            json.dumps({"value_numeric": 130.0}),
        ],
    )
    assert resolve_result.exit_code == 0

    with factory() as session:
        fact = load_parsed_value(
            session=session,
            accession_no="0000000000-24-000020",
            route="owner",
            field_name="shares_acquired_or_disposed",
            subject_key="txn:1",
        )
        decision = session.query(ReviewDecision).one()
        golden_truth = session.query(GoldenTruth).one()
        assert fact is not None
        assert fact.value_numeric == 130.0
        assert decision.error_code == "row_match_error"
        assert float(golden_truth.value_numeric) == 130.0


def test_cli_review_assign_updates_assignee(monkeypatch) -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_review_task(session)

    monkeypatch.setattr(cli_module, "Settings", lambda: object())
    monkeypatch.setattr(cli_module, "get_session_factory", lambda settings: factory)

    list_result = runner.invoke(cli_module.app, ["review-list"])
    task_id = json.loads(list_result.stdout)[0]["task_id"]

    assign_result = runner.invoke(
        cli_module.app,
        ["review-assign", str(task_id), "  carol  "],
    )
    assert assign_result.exit_code == 0
    payload = json.loads(assign_result.stdout)
    assert payload == {"task_id": task_id, "status": "open", "assignee": "carol"}

    with factory() as session:
        task = session.query(ReviewTask).one()
        assert task.assignee == "carol"


def test_cli_review_resolve_requires_error_code_for_reject(monkeypatch) -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_review_task(session)

    monkeypatch.setattr(cli_module, "Settings", lambda: object())
    monkeypatch.setattr(cli_module, "get_session_factory", lambda settings: factory)

    list_result = runner.invoke(cli_module.app, ["review-list"])
    task_id = json.loads(list_result.stdout)[0]["task_id"]

    reject_result = runner.invoke(
        cli_module.app,
        [
            "review-resolve",
            str(task_id),
            "--decision",
            "reject",
            "--reviewer",
            "carol",
        ],
    )
    assert reject_result.exit_code != 0
    assert "error-code" in reject_result.output


def test_cli_review_resolve_rejects_unknown_error_code(monkeypatch) -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_review_task(session)

    monkeypatch.setattr(cli_module, "Settings", lambda: object())
    monkeypatch.setattr(cli_module, "get_session_factory", lambda settings: factory)

    list_result = runner.invoke(cli_module.app, ["review-list"])
    task_id = json.loads(list_result.stdout)[0]["task_id"]

    reject_result = runner.invoke(
        cli_module.app,
        [
            "review-resolve",
            str(task_id),
            "--decision",
            "reject",
            "--reviewer",
            "carol",
            "--error-code",
            "freeform typo code",
        ],
    )
    assert reject_result.exit_code != 0
    assert "error_code must be one of:" in reject_result.output
