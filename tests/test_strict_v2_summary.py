from __future__ import annotations

from src.pipeline.strict_v2_summary import build_phase_gate_summary, build_strict_v2_summary


def test_build_phase_gate_summary_counts_statuses() -> None:
    summary = build_phase_gate_summary(
        [
            {"name": "gate-1", "status": "passed"},
            {"name": "gate-2", "status": "failed"},
            {"name": "gate-3", "status": "skipped"},
        ]
    )

    assert summary == {"total": 3, "passed": 1, "failed": 1, "skipped": 1}


def test_build_strict_v2_summary_uses_shared_shape() -> None:
    summary = build_strict_v2_summary(
        run_id="run-001",
        selectors={"route": "issuer", "mode": "numeric_batch"},
        coverage={"total_cases": 2},
        metrics={"passed": 1, "failed": 1},
        phase_gates=[{"name": "gate-1", "status": "passed"}],
    )

    assert summary == {
        "run_id": "run-001",
        "selectors": {"route": "issuer", "mode": "numeric_batch"},
        "coverage": {"total_cases": 2},
        "metrics": {"passed": 1, "failed": 1},
        "phase_gates": {"total": 1, "passed": 1, "failed": 0, "skipped": 0},
    }
