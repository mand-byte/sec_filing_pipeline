from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_ARTIFACT_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


def _write_ndjson(path: Path, records: list[dict[str, Any]]) -> None:
    """Write JSON records as newline-delimited JSON."""
    with path.open("w", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")



def _safe_artifact_name(value: object, *, fallback: str) -> str:
    """Sanitize arbitrary values into safe artifact path components."""
    text = str(value).strip()
    if not text:
        return fallback

    sanitized = _ARTIFACT_NAME_PATTERN.sub("_", text)
    sanitized = sanitized.strip("._")
    return sanitized or fallback



def _resolve_run_dir(*, base_dir: Path, run_id: str) -> Path:
    """Resolve one run directory while preventing path traversal."""
    base_dir_resolved = base_dir.resolve()
    run_dir = (base_dir_resolved / _safe_artifact_name(run_id, fallback="run")).resolve()
    if run_dir.parent != base_dir_resolved:
        raise ValueError(f"invalid run_id path: {run_id!r}")
    return run_dir



def write_run_artifacts(
    *,
    base_dir: Path,
    run_id: str,
    summary: dict[str, Any],
    by_field: dict[str, Any],
    failures: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    diff_markdown: str,
    manifest: dict[str, Any] | None = None,
    coverage: dict[str, Any] | None = None,
    silver_alignment: list[dict[str, Any]] | None = None,
    invariants: list[dict[str, Any]] | None = None,
    review_packets: list[dict[str, Any]] | None = None,
    phase_gates: list[dict[str, Any]] | None = None,
) -> None:
    """Write the standard artifact bundle for one evaluation or runtime run."""
    run_dir = _resolve_run_dir(base_dir=base_dir, run_id=run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest_payload = manifest or {"run_id": run_id}
    coverage_payload = coverage or dict(summary.get("coverage", {}))
    silver_alignment_payload = silver_alignment or []
    invariant_payload = invariants or []
    review_packet_payload = review_packets or []
    phase_gate_payload = phase_gates or []

    (run_dir / "manifest.json").write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_dir / "by_field.json").write_text(
        json.dumps(by_field, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_dir / "coverage.json").write_text(
        json.dumps(coverage_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_dir / "phase_gates.json").write_text(
        json.dumps(phase_gate_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    _write_ndjson(run_dir / "mismatches.ndjson", failures)
    _write_ndjson(run_dir / "silver_alignment.ndjson", silver_alignment_payload)
    _write_ndjson(run_dir / "invariants.ndjson", invariant_payload)

    review_packets_dir = run_dir / "review_packets"
    review_packets_dir.mkdir(exist_ok=True)
    for index, packet in enumerate(review_packet_payload):
        case_id = _safe_artifact_name(packet.get("case_id"), fallback="unknown_case")
        subject_key = _safe_artifact_name(packet.get("subject_key"), fallback="document")
        field_name = _safe_artifact_name(packet.get("field_name"), fallback="unknown_field")
        stem = f"{case_id}__{subject_key}__{field_name}"
        packet_path = review_packets_dir / f"{stem}.json"
        if packet_path.exists():
            packet_path = review_packets_dir / f"{stem}__{index}.json"
        packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")

    mismatches_payload = (run_dir / "mismatches.ndjson").read_text(encoding="utf-8")
    (run_dir / "failures.ndjson").write_text(mismatches_payload, encoding="utf-8")
    _write_ndjson(run_dir / "candidates.ndjson", candidates)
    (run_dir / "diff.md").write_text(diff_markdown, encoding="utf-8")
