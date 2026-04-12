from __future__ import annotations

import json
from pathlib import Path

from src.pipeline.offline_artifacts import write_run_artifacts


def test_write_run_artifacts_emits_strict_v2_file_set(tmp_path: Path) -> None:
    write_run_artifacts(
        base_dir=tmp_path,
        run_id="run-001",
        summary={"run_id": "run-001", "coverage": {"total_cases": 1}},
        by_field={"current_event_quant": {"total": 1, "matched": 1, "failed": 0, "ok": 1, "error": 0}},
        failures=[{"case_id": "case-001", "field_name": "current_event_quant"}],
        candidates=[{"case_id": "case-001", "field_name": "current_event_quant", "matched": True}],
        diff_markdown="# Diff\n- ok",
        manifest={"run_id": "run-001", "config_paths": {"regex_config": "cfg.yaml"}},
        coverage={"total_cases": 1, "total_candidates": 1},
        silver_alignment=[{"case_id": "case-002", "field_name": "current_event_quant", "matched": True}],
        invariants=[{"case_id": "case-003", "name": "cash_nonnegative", "status": "pass"}],
        phase_gates=[{"name": "phase-1", "status": "passed", "violations": []}],
        review_packets=[
            {
                "case_id": "case-001",
                "subject_key": "document",
                "field_name": "current_event_quant",
                "payload": {"expected": "event"},
            }
        ],
    )

    run_dir = tmp_path / "run-001"
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "summary.json").exists()
    assert (run_dir / "by_field.json").exists()
    assert (run_dir / "coverage.json").exists()
    assert (run_dir / "phase_gates.json").exists()
    assert (run_dir / "mismatches.ndjson").exists()
    assert (run_dir / "silver_alignment.ndjson").exists()
    assert (run_dir / "invariants.ndjson").exists()
    assert (run_dir / "review_packets" / "case-001__document__current_event_quant.json").exists()

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["config_paths"]["regex_config"] == "cfg.yaml"

    coverage = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))
    assert coverage["total_candidates"] == 1
    phase_gates = json.loads((run_dir / "phase_gates.json").read_text(encoding="utf-8"))
    assert phase_gates == [{"name": "phase-1", "status": "passed", "violations": []}]

    mismatches = (run_dir / "mismatches.ndjson").read_text(encoding="utf-8").strip().splitlines()
    assert len(mismatches) == 1

    aliases = (run_dir / "failures.ndjson").read_text(encoding="utf-8")
    assert aliases == (run_dir / "mismatches.ndjson").read_text(encoding="utf-8")


def test_write_run_artifacts_sanitizes_run_id(tmp_path: Path) -> None:
    write_run_artifacts(
        base_dir=tmp_path,
        run_id="../../escape",
        summary={"run_id": "escape"},
        by_field={},
        failures=[],
        candidates=[],
        diff_markdown="# Diff",
    )

    assert (tmp_path / "escape").exists()
    assert not (tmp_path.parent / "escape").exists()


def test_write_run_artifacts_avoids_review_packet_name_collisions(tmp_path: Path) -> None:
    write_run_artifacts(
        base_dir=tmp_path,
        run_id="run-002",
        summary={"run_id": "run-002"},
        by_field={},
        failures=[],
        candidates=[],
        diff_markdown="# Diff",
        review_packets=[
            {"case_id": "case/001", "subject_key": "doc", "field_name": "field?1"},
            {"case_id": "case?001", "subject_key": "doc", "field_name": "field/1"},
        ],
    )

    packet_files = sorted(path.name for path in (tmp_path / "run-002" / "review_packets").iterdir())
    assert packet_files == [
        "case_001__doc__field_1.json",
        "case_001__doc__field_1__1.json",
    ]
