from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from typer.testing import CliRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import src.cli as cli_module
from src.db.base import Base
from src.db.models import ExtractedFact
from src.pipeline.review.server import ReviewApi, ReviewServerConfig, build_review_server_html, create_review_http_handler, run_review_server
from src.pipeline.services import EvidenceInput, FactInput, PersistenceService
from src.pipeline.types import FilingRecord


runner = CliRunner()


def _session_factory(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'review_server.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False)


def _filing() -> FilingRecord:
    return FilingRecord(
        accession_no="0000000000-24-000040",
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
                selection_trace_json='{"selected_value":"100"}',
                raw_value="100",
                normalized_value="100.0",
            )
        ],
    )


def test_build_review_server_html_contains_interactive_surface() -> None:
    html = build_review_server_html(initial_status="open", initial_route=None, initial_limit=100)

    assert "Review Workbench" in html
    assert "/api/tasks" in html
    assert "Resolve Task" in html
    assert "Evidence Pane" in html
    assert "Extracted Result" in html
    assert "Locator JSON" in html
    assert "Heading Path" in html
    assert "Adequacy Signals" in html
    assert "Selection Trace" in html


def test_review_server_http_flow_lists_and_resolves_tasks(tmp_path: Path) -> None:
    factory = _session_factory(tmp_path)
    with factory() as session:
        _seed_review_task(session)

    api = ReviewApi(session_factory=factory, status="open", route=None, limit=100)
    handler = create_review_http_handler(api=api)

    from http.server import ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        with urlopen(f"{base_url}/") as response:
            html = response.read().decode("utf-8")
        assert "Review Workbench" in html

        with urlopen(f"{base_url}/api/tasks") as response:
            tasks = json.loads(response.read().decode("utf-8"))
        assert len(tasks) == 1
        task_id = tasks[0]["task_id"]

        with urlopen(f"{base_url}/api/tasks/{task_id}") as response:
            detail = json.loads(response.read().decode("utf-8"))
        assert detail["task"]["subject_key"] == "txn:1"
        assert detail["primary_evidence"]["source_locator_json"] is not None
        assert detail["primary_evidence"]["source_heading_path_json"] == '["Ownership Table"]'
        assert detail["primary_evidence"]["adequacy_signals_json"] == '{"window_found":true,"span_policy_applied":false}'
        assert detail["primary_evidence"]["selection_trace_json"] == '{"selected_value":"100"}'

        bad_request = Request(
            f"{base_url}/api/tasks/{task_id}/resolve",
            data=json.dumps({"decision": "reject", "reviewer": "alice"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urlopen(bad_request)
        except HTTPError as exc:
            assert exc.code == 400
            payload = json.loads(exc.read().decode("utf-8"))
            assert "error-code" in payload["error"]
        else:  # pragma: no cover - defensive branch
            raise AssertionError("expected missing error_code request to fail")

        resolve_request = Request(
            f"{base_url}/api/tasks/{task_id}/resolve",
            data=json.dumps(
                {
                    "decision": "corrected",
                    "reviewer": "alice",
                    "error_code": "row_match_error",
                    "corrected_json": {"value_numeric": 140.0},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(resolve_request) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["status"] == "corrected"

        with factory() as session:
            fact = session.query(ExtractedFact).one()
            assert fact.value_numeric == 140.0
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_cli_review_serve_wires_server_configuration(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_review_server(*, session_factory, config) -> None:
        captured["session_factory"] = session_factory
        captured["config"] = config

    monkeypatch.setattr(cli_module, "Settings", lambda: object())
    monkeypatch.setattr(cli_module, "get_session_factory", lambda settings: "session-factory")
    monkeypatch.setattr(cli_module, "run_review_server", fake_run_review_server)

    result = runner.invoke(
        cli_module.app,
        [
            "review-serve",
            "--status",
            "open",
            "--route",
            "owner",
            "--limit",
            "25",
            "--host",
            "127.0.0.1",
            "--port",
            "8766",
        ],
    )

    assert result.exit_code == 0
    assert "http://127.0.0.1:8766" in result.stdout
    assert captured["session_factory"] == "session-factory"
    config = captured["config"]
    assert isinstance(config, ReviewServerConfig)
    assert config.status == "open"
    assert config.route == "owner"
    assert config.limit == 25
    assert config.host == "127.0.0.1"
    assert config.port == 8766
