from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.db.models import FilingAttempt, PipelineLog


def build_run_artifact_payloads(*, session: Session, run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """Rebuild runtime artifact payloads from the authoritative DB state."""
    route_rows = session.execute(
        select(PipelineLog.route, func.count())
        .where(PipelineLog.run_id == run_id, PipelineLog.stage == "persist", PipelineLog.level == "INFO")
        .group_by(PipelineLog.route)
    ).all()
    route_coverage = {route: int(count) for route, count in route_rows}

    error_rows = session.execute(
        select(PipelineLog.error_type, func.count())
        .where(PipelineLog.run_id == run_id, PipelineLog.level == "ERROR")
        .group_by(PipelineLog.error_type)
    ).all()
    error_distribution = {
        (error_type or "UNKNOWN"): int(count)
        for error_type, count in error_rows
    }

    filing_attempt_rows = session.scalars(
        select(FilingAttempt)
        .where(FilingAttempt.run_id == run_id)
        .order_by(FilingAttempt.route.asc(), FilingAttempt.accession_no.asc(), FilingAttempt.id.asc())
    ).all()
    filing_attempt_status_counts: dict[str, int] = {}
    filing_attempt_route_counts: dict[str, dict[str, int]] = {}
    for row in filing_attempt_rows:
        filing_attempt_status_counts[row.status] = filing_attempt_status_counts.get(row.status, 0) + 1
        route_status_counts = filing_attempt_route_counts.setdefault(row.route, {})
        route_status_counts[row.status] = route_status_counts.get(row.status, 0) + 1

    sample_logs = session.scalars(
        select(PipelineLog)
        .where(PipelineLog.run_id == run_id)
        .order_by(PipelineLog.id.asc())
    ).all()
    samples = [
        {
            "route": row.route,
            "stage": row.stage,
            "level": row.level,
            "message": row.message,
            "cik": row.cik,
            "accession_no": row.accession_no,
            "error_type": row.error_type,
            "error_detail": row.error_detail,
        }
        for row in sample_logs
    ]

    summary = {
        "run_id": run_id,
        "coverage": {
            "routes": route_coverage,
            "filing_attempts": {
                "total": len(filing_attempt_rows),
                "by_status": filing_attempt_status_counts,
                "by_route": filing_attempt_route_counts,
            },
        },
        "errors": {
            "distribution": error_distribution,
        },
        "metrics": {
            "total_logs": len(sample_logs),
            "total_filing_attempts": len(filing_attempt_rows),
        },
    }

    diff_markdown = "# Diff\n- baseline comparison unavailable for this run"
    return summary, samples, diff_markdown


def load_json_file(path: Path) -> dict[str, Any]:
    """Load one JSON object file and reject non-object payloads."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def load_ndjson_file(path: Path) -> list[dict[str, Any]]:
    """Load NDJSON records and reject any non-object row."""
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    records: list[dict[str, Any]] = []
    for line in lines:
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"expected NDJSON objects in {path}")
        records.append(payload)
    return records


@dataclass(frozen=True)
class RuntimeRunVerificationResult:
    run_id: str
    passed: bool
    artifact_dir: str
    mismatches: list[str]
    db_summary: dict[str, Any]


def load_backfill_cohort_manifest(path: Path) -> list[str]:
    """Extract the runtime run ids from one cohort manifest artifact."""
    payload = load_json_file(path)
    route_runs = payload.get("route_runs", [])
    if not isinstance(route_runs, Sequence) or isinstance(route_runs, (str, bytes)):
        raise ValueError(f"cohort manifest route_runs must be a list: {path}")

    run_ids: list[str] = []
    for row in route_runs:
        if not isinstance(row, Mapping):
            raise ValueError(f"cohort manifest route_runs entries must be objects: {path}")
        run_id = str(row.get("run_id", "")).strip()
        if not run_id:
            raise ValueError(f"cohort manifest route_runs entries must contain run_id: {path}")
        run_ids.append(run_id)
    return run_ids


def verify_runtime_run(
    *,
    session: Session,
    run_id: str,
    base_dir: Path,
) -> RuntimeRunVerificationResult:
    """Compare one runtime artifact directory against DB-derived truth."""
    run_dir = base_dir / run_id

    mismatches: list[str] = []
    artifact_summary_loaded = False
    artifact_candidates_loaded = False
    artifact_failures_loaded = False
    if not run_dir.exists():
        mismatches.append(f"artifact directory missing: {run_dir}")
        artifact_summary: dict[str, Any] = {}
        artifact_candidates: list[dict[str, Any]] = []
        artifact_failures: list[dict[str, Any]] = []
    else:
        artifact_summary = load_json_file(run_dir / "summary.json")
        artifact_candidates = load_ndjson_file(run_dir / "candidates.ndjson")
        artifact_failures = load_ndjson_file(run_dir / "failures.ndjson")
        artifact_summary_loaded = True
        artifact_candidates_loaded = True
        artifact_failures_loaded = True

    db_summary, db_samples, _ = build_run_artifact_payloads(session=session, run_id=run_id)
    db_failures = [sample for sample in db_samples if sample.get("level") == "ERROR"]

    if artifact_summary_loaded and artifact_summary != db_summary:
        mismatches.append("summary.json does not match DB-derived summary")
    if artifact_candidates_loaded and artifact_candidates != db_samples:
        mismatches.append("candidates.ndjson does not match DB pipeline_log rows")
    if artifact_failures_loaded and artifact_failures != db_failures:
        mismatches.append("failures.ndjson does not match DB error rows")

    return RuntimeRunVerificationResult(
        run_id=run_id,
        passed=not mismatches,
        artifact_dir=str(run_dir),
        mismatches=mismatches,
        db_summary=db_summary,
    )
