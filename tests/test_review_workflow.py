from __future__ import annotations

import json
from datetime import datetime, timezone

from typer.testing import CliRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import src.cli as cli_module
from src.db.base import Base
from src.db.models import (
    ExtractedFact,
    GoldenCase,
    GoldenEvalRun,
    GoldenReviewPacket,
    GoldenSubject,
    GoldenTruth,
    ReviewDecision,
    ReviewTask,
)
from src.pipeline.review.workflow import ReviewWorkflowService
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
                raw_value="100",
                normalized_value="100.0",
            )
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
            reviewer="alice",
            error_code="unit_scaling",
            corrected_json=json.dumps({"value_numeric": 125.5, "value_unit": "shares"}),
            comment="corrected transaction size",
        )
        assert updated.status == "corrected"

    with factory() as session:
        fact = session.query(ExtractedFact).one()
        decision = session.query(ReviewDecision).one()
        task = session.query(ReviewTask).one()
        golden_case = session.query(GoldenCase).one()
        golden_subject = session.query(GoldenSubject).one()
        golden_truth = session.query(GoldenTruth).one()
        golden_run = session.query(GoldenEvalRun).one()
        golden_packet = session.query(GoldenReviewPacket).one()
        assert fact.value_numeric == 125.5
        assert fact.value_unit == "shares"
        assert fact.confidence == 1.0
        assert decision.decision == "CORRECTED"
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
        assert session.query(ExtractedFact).all() == []
        decision = session.query(ReviewDecision).one()
        golden_case = session.query(GoldenCase).one()
        golden_subject = session.query(GoldenSubject).one()
        golden_packet = session.query(GoldenReviewPacket).one()
        assert decision.decision == "REJECT"
        assert decision.error_code == "locator_miss"
        assert golden_case.case_id == "manual-review::0000000000-24-000020"
        assert golden_subject.subject_key == "txn:1"
        assert "locator_miss" in golden_packet.packet_json
        assert session.query(GoldenTruth).all() == []


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
        fact = session.query(ExtractedFact).one()
        decision = session.query(ReviewDecision).one()
        golden_truth = session.query(GoldenTruth).one()
        assert fact.value_numeric == 130.0
        assert decision.error_code == "row_match_error"
        assert float(golden_truth.value_numeric) == 130.0


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
