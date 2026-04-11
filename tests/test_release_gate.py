from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from typer.testing import CliRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import src.cli as cli_module
from src.db.base import Base
from src.db.models import GoldenReviewPacket, ReviewTask
from src.pipeline.release_gates import evaluate_fix_once_release_gate
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
