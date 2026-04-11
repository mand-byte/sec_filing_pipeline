from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.db.models import GoldenReviewPacket, ReviewTask


_SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_FIX_ONCE_STATUSES = ("corrected", "reject", "not_applicable")


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
    exported_packets: int
    output_dir: str | None


def evaluate_fix_once_release_gate(
    *,
    session: Session,
    output_dir: Path | None = None,
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
                        passed=(open_review_tasks == 0 and missing_review_packets == 0),
                        open_review_tasks=open_review_tasks,
                        resolved_fix_once_tasks=len(fix_once_tasks),
                        golden_review_packets=len(packets),
                        missing_review_packets=missing_review_packets,
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
        passed=(open_review_tasks == 0 and missing_review_packets == 0),
        open_review_tasks=open_review_tasks,
        resolved_fix_once_tasks=len(fix_once_tasks),
        golden_review_packets=len(packets),
        missing_review_packets=missing_review_packets,
        exported_packets=exported_packets,
        output_dir=str(resolved_output_dir) if resolved_output_dir is not None else None,
    )
