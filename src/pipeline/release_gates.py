from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
from pathlib import Path
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.db.models import GoldenReviewPacket, PipelineLog, ReviewTask
from src.pipeline.runtime_verification import load_backfill_cohort_manifest, verify_runtime_run


_SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_FIX_ONCE_STATUSES = ("corrected", "reject", "not_applicable")
_NON_BLOCKING_RUNTIME_EXTRACT_ERROR_TYPES = {
    "MULTIPLE_CANDIDATES",
    "PATTERN_NOT_MATCHED",
    "SPAN_POLICY_FAILED",
    "NO_OWNER_ROWS_EXTRACTED",
    "NO_HOLDING_ROWS_EXTRACTED",
    "NO_VOTE_ROWS_EXTRACTED",
    "NO_TARGET_FIELDS_EXTRACTED",
}


def _safe_name(value: object, *, fallback: str) -> str:
    text = str(value).strip()
    if not text:
        return fallback
    sanitized = _SAFE_NAME_PATTERN.sub("_", text).strip("._")
    return sanitized or fallback


@dataclass(frozen=True)
class ReleaseGateResult:
    passed: bool
    open_review_tasks: int
    resolved_fix_once_tasks: int
    golden_review_packets: int
    missing_review_packets: int
    evaluator_summary_path: str | None
    evaluator_summary_paths: list[str]
    evaluator_passes_threshold: bool | None
    evaluator_failed_phase_gates: int | None
    runtime_verified_runs: int
    runtime_failed_runs: int
    runtime_failed_attempts: int
    runtime_error_logs: int
    runtime_blocking_error_logs: int
    runtime_failure_details: list[dict[str, object]]
    exported_packets: int
    output_dir: str | None


def _strict_summary_has_active_selectors(selectors: dict[str, object]) -> bool:
    return any(value not in (None, "", [], {}) for value in selectors.values())


def _evaluate_strict_summary(path: Path | None) -> tuple[bool | None, int | None]:
    if path is None:
        return None, None

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"strict summary must be a JSON object: {path}")

    metrics = payload.get("metrics", {})
    if not isinstance(metrics, dict):
        raise ValueError(f"strict summary metrics must be an object: {path}")
    phase_gates = payload.get("phase_gates", {})
    if not isinstance(phase_gates, dict):
        raise ValueError(f"strict summary phase_gates must be an object: {path}")
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError(f"strict summary run_id must be a non-empty string: {path}")
    selectors = payload.get("selectors", {})
    if not isinstance(selectors, dict):
        raise ValueError(f"strict summary selectors must be an object: {path}")
    if _strict_summary_has_active_selectors(selectors):
        raise ValueError(f"strict summary must be unfiltered for release-gate: {path}")

    passes_threshold = metrics.get("passes_threshold")
    if not isinstance(passes_threshold, bool):
        raise ValueError(f"strict summary metrics.passes_threshold must be boolean: {path}")
    failed_phase_gates = phase_gates.get("failed")
    if not isinstance(failed_phase_gates, int):
        raise ValueError(f"strict summary phase_gates.failed must be integer: {path}")

    return passes_threshold, failed_phase_gates


def _normalize_strict_summary_paths(
    *,
    strict_summary_path: Path | None,
    strict_summary_paths: Sequence[Path] | None,
) -> list[Path]:
    normalized_paths: list[Path] = []
    if strict_summary_path is not None:
        normalized_paths.append(strict_summary_path)
    if strict_summary_paths is not None:
        normalized_paths.extend(strict_summary_paths)
    return normalized_paths


def _evaluate_strict_summaries(paths: Sequence[Path]) -> tuple[bool | None, int | None]:
    if not paths:
        return None, None

    all_pass = True
    failed_phase_gate_count = 0
    for path in paths:
        passes_threshold, failed_phase_gates = _evaluate_strict_summary(path)
        all_pass = all_pass and passes_threshold is True
        failed_phase_gate_count += int(failed_phase_gates or 0)

    return all_pass, failed_phase_gate_count


def evaluate_fix_once_release_gate(
    *,
    session: Session,
    output_dir: Path | None = None,
    strict_summary_path: Path | None = None,
    strict_summary_paths: Sequence[Path] | None = None,
    runtime_run_ids: Sequence[str] | None = None,
    runtime_artifacts_dir: Path | None = None,
    runtime_cohort_manifests: Sequence[Path] | None = None,
) -> ReleaseGateResult:
    open_review_tasks = session.scalar(
        select(func.count()).select_from(ReviewTask).where(ReviewTask.status == "open")
    )
    if open_review_tasks is None:
        open_review_tasks = 0

    fix_once_tasks = session.scalars(
        select(ReviewTask).where(ReviewTask.status.in_(_FIX_ONCE_STATUSES))
    ).all()

    packets = session.scalars(
        select(GoldenReviewPacket).order_by(
            GoldenReviewPacket.run_id.asc(),
            GoldenReviewPacket.case_id.asc(),
            GoldenReviewPacket.field_name.asc(),
            GoldenReviewPacket.id.asc(),
        )
    ).all()
    packet_by_run: dict[str, list[GoldenReviewPacket]] = {}
    for packet in packets:
        packet_by_run.setdefault(packet.run_id, []).append(packet)

    missing_review_packets = 0
    for task in fix_once_tasks:
        expected_run_id = f"review-capture::{task.task_id}"
        if not packet_by_run.get(expected_run_id):
            missing_review_packets += 1

    effective_strict_summary_paths = _normalize_strict_summary_paths(
        strict_summary_path=strict_summary_path,
        strict_summary_paths=strict_summary_paths,
    )
    evaluator_passes_threshold, evaluator_failed_phase_gates = _evaluate_strict_summaries(effective_strict_summary_paths)
    strict_gate_failed = (
        evaluator_passes_threshold is False
        or (isinstance(evaluator_failed_phase_gates, int) and evaluator_failed_phase_gates > 0)
    )
    effective_runtime_run_ids = [str(run_id).strip() for run_id in (runtime_run_ids or ()) if str(run_id).strip()]
    for manifest_path in runtime_cohort_manifests or ():
        effective_runtime_run_ids.extend(load_backfill_cohort_manifest(manifest_path))
    effective_runtime_run_ids = list(dict.fromkeys(effective_runtime_run_ids))
    runtime_failure_details: list[dict[str, object]] = []
    runtime_failed_attempts = 0
    runtime_error_logs = 0
    runtime_blocking_error_logs = 0
    if runtime_artifacts_dir is not None:
        for run_id in effective_runtime_run_ids:
            result = verify_runtime_run(session=session, run_id=run_id, base_dir=runtime_artifacts_dir)
            filing_attempts = result.db_summary.get("coverage", {}).get("filing_attempts", {})
            by_status = filing_attempts.get("by_status", {}) if isinstance(filing_attempts, dict) else {}
            run_failed_attempts = int(by_status.get("failed", 0)) if isinstance(by_status, dict) else 0
            error_distribution = result.db_summary.get("errors", {}).get("distribution", {})
            run_error_logs = sum(int(count) for count in error_distribution.values()) if isinstance(error_distribution, dict) else 0
            blocking_error_logs = 0
            error_rows = session.query(PipelineLog.stage, PipelineLog.message, PipelineLog.error_type).filter(
                PipelineLog.run_id == run_id,
                PipelineLog.level == "ERROR",
            ).all()
            for stage, message, error_type in error_rows:
                if stage == "extract" and (
                    message == "text field extraction failed"
                    or (isinstance(error_type, str) and error_type in _NON_BLOCKING_RUNTIME_EXTRACT_ERROR_TYPES)
                ):
                    continue
                blocking_error_logs += 1
            runtime_failed_attempts += run_failed_attempts
            runtime_error_logs += run_error_logs
            runtime_blocking_error_logs += blocking_error_logs
            if not result.passed:
                runtime_failure_details.append(
                    {
                        "run_id": run_id,
                        "artifact_dir": result.artifact_dir,
                        "mismatches": result.mismatches,
                    }
                )
            elif run_failed_attempts > 0 or blocking_error_logs > 0:
                runtime_failure_details.append(
                    {
                        "run_id": run_id,
                        "artifact_dir": result.artifact_dir,
                        "mismatches": [],
                        "failed_attempts": run_failed_attempts,
                        "error_logs": run_error_logs,
                        "blocking_error_logs": blocking_error_logs,
                    }
                )
    runtime_failed_runs = len(runtime_failure_details)
    runtime_verified_runs = len(effective_runtime_run_ids)

    exported_packets = 0
    resolved_output_dir = None
    if output_dir is not None:
        resolved_output_dir = output_dir.resolve()
        regressions_dir = resolved_output_dir / "review_regressions"
        regressions_dir.mkdir(parents=True, exist_ok=True)
        for packet in packets:
            payload = json.loads(packet.packet_json)
            run_id = _safe_name(packet.run_id, fallback="run")
            case_id = _safe_name(packet.case_id, fallback="case")
            field_name = _safe_name(packet.field_name, fallback="field")
            packet_path = regressions_dir / f"{run_id}__{case_id}__{field_name}.json"
            if packet_path.exists():
                packet_path = regressions_dir / f"{run_id}__{case_id}__{field_name}__{packet.id}.json"
            packet_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            exported_packets += 1

        summary_path = resolved_output_dir / "summary.json"
        summary_path.write_text(
            json.dumps(
                asdict(
                    ReleaseGateResult(
                        passed=(open_review_tasks == 0 and missing_review_packets == 0 and not strict_gate_failed and runtime_failed_runs == 0),
                        open_review_tasks=open_review_tasks,
                        resolved_fix_once_tasks=len(fix_once_tasks),
                        golden_review_packets=len(packets),
                        missing_review_packets=missing_review_packets,
                        evaluator_summary_path=str(effective_strict_summary_paths[0].resolve()) if len(effective_strict_summary_paths) == 1 else None,
                        evaluator_summary_paths=[str(path.resolve()) for path in effective_strict_summary_paths],
                        evaluator_passes_threshold=evaluator_passes_threshold,
                        evaluator_failed_phase_gates=evaluator_failed_phase_gates,
                        runtime_verified_runs=runtime_verified_runs,
                        runtime_failed_runs=runtime_failed_runs,
                        runtime_failed_attempts=runtime_failed_attempts,
                        runtime_error_logs=runtime_error_logs,
                        runtime_blocking_error_logs=runtime_blocking_error_logs,
                        runtime_failure_details=runtime_failure_details,
                        exported_packets=exported_packets,
                        output_dir=str(resolved_output_dir),
                    )
                ),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    return ReleaseGateResult(
        passed=(open_review_tasks == 0 and missing_review_packets == 0 and not strict_gate_failed and runtime_failed_runs == 0),
        open_review_tasks=open_review_tasks,
        resolved_fix_once_tasks=len(fix_once_tasks),
        golden_review_packets=len(packets),
        missing_review_packets=missing_review_packets,
        evaluator_summary_path=str(effective_strict_summary_paths[0].resolve()) if len(effective_strict_summary_paths) == 1 else None,
        evaluator_summary_paths=[str(path.resolve()) for path in effective_strict_summary_paths],
        evaluator_passes_threshold=evaluator_passes_threshold,
        evaluator_failed_phase_gates=evaluator_failed_phase_gates,
        runtime_verified_runs=runtime_verified_runs,
        runtime_failed_runs=runtime_failed_runs,
        runtime_failed_attempts=runtime_failed_attempts,
        runtime_error_logs=runtime_error_logs,
        runtime_blocking_error_logs=runtime_blocking_error_logs,
        runtime_failure_details=runtime_failure_details,
        exported_packets=exported_packets,
        output_dir=str(resolved_output_dir) if resolved_output_dir is not None else None,
    )
