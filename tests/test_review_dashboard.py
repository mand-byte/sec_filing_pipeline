from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from typer.testing import CliRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import src.cli as cli_module
from src.db.base import Base
from src.pipeline.services import EvidenceInput, FactInput, PersistenceService
from src.pipeline.review.dashboard import build_review_dashboard_packets, write_review_dashboard
from src.pipeline.review.workflow import ReviewWorkflowService
from src.pipeline.types import FilingRecord


runner = CliRunner()


def _session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False)


def _filing() -> FilingRecord:
    return FilingRecord(
        accession_no="0000000000-24-000030",
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


def test_write_review_dashboard_creates_html_and_packets(tmp_path: Path) -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_review_task(session)

    with factory() as session:
        service = ReviewWorkflowService(session)
        packets = build_review_dashboard_packets(service=service)

    output_dir = write_review_dashboard(output_dir=tmp_path / "dashboard", packets=packets)

    assert (output_dir / "index.html").exists()
    assert (output_dir / "packets.json").exists()

    html = (output_dir / "index.html").read_text(encoding="utf-8")
    packet_payload = json.loads((output_dir / "packets.json").read_text(encoding="utf-8"))

    assert "Review Desk" in html
    assert "Evidence Pane" in html
    assert "Extracted Result" in html
    assert "shares_acquired_or_disposed" in html
    assert "Heading Path" in html
    assert "Adequacy Signals" in html
    assert packet_payload[0]["primary_evidence"]["source_heading_path_json"] == '["Ownership Table"]'
    assert packet_payload[0]["task"]["subject_key"] == "txn:1"


def test_cli_review_dashboard_exports_dashboard(monkeypatch, tmp_path: Path) -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_review_task(session)

    monkeypatch.setattr(cli_module, "Settings", lambda: object())
    monkeypatch.setattr(cli_module, "get_session_factory", lambda settings: factory)

    output_dir = tmp_path / "review-output"
    result = runner.invoke(
        cli_module.app,
        ["review-dashboard", "--output-dir", str(output_dir)],
    )

    assert result.exit_code == 0
    assert str(output_dir.resolve()) in result.stdout
    assert (output_dir / "index.html").exists()
    assert (output_dir / "packets.json").exists()
