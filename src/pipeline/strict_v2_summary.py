from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def build_phase_gate_summary(phase_gates: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(phase_gates),
        "passed": len([gate for gate in phase_gates if gate.get("status") == "passed"]),
        "failed": len([gate for gate in phase_gates if gate.get("status") == "failed"]),
        "skipped": len([gate for gate in phase_gates if gate.get("status") == "skipped"]),
    }


def build_strict_v2_summary(
    *,
    run_id: str,
    selectors: Mapping[str, Any],
    coverage: Mapping[str, Any],
    metrics: Mapping[str, Any],
    phase_gates: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "selectors": dict(selectors),
        "coverage": dict(coverage),
        "metrics": dict(metrics),
        "phase_gates": build_phase_gate_summary(phase_gates),
    }
