from __future__ import annotations

import json
from pathlib import Path

from src.pipeline.extraction._config import tier2_path
from src.pipeline.offline_evaluator import OfflineEvalSelectors, run_offline_tier2_evaluation


def test_default_tier2_assets_cover_current_vertical_slice(tmp_path: Path) -> None:
    result = run_offline_tier2_evaluation(
        regex_config_path=tier2_path("regex", "default.yaml"),
        golden_set_path=tier2_path("golden_set", "default.yaml"),
        fixtures_dir=tier2_path("fixtures"),
        artifacts_dir=tmp_path,
        run_id="phase-gate-default",
        min_pass_rate=1.0,
    )

    assert result.summary["coverage"] == {
        "total_cases": 6,
        "total_candidates": 6,
        "gold_applicable_rows": 6,
        "silver_applicable_rows": 0,
        "invariant_rows": 0,
    }
    assert result.summary["metrics"]["pass_rate"] == 1.0
    assert result.summary["metrics"]["gold_strict_accuracy"] == 1.0

    by_field = json.loads((tmp_path / "phase-gate-default" / "by_field.json").read_text(encoding="utf-8"))
    assert by_field["current_event_quant"]["matched"] == 1
    assert by_field["delay_reason_quant"]["matched"] == 1
    assert by_field["beneficial_ownership_intent_quant"]["matched"] == 1
    assert by_field["source_of_funds_quant"]["matched"] == 1
    assert by_field["manager_structure_quant"]["matched"] == 1
    assert by_field["amendment_scope_quant"]["matched"] == 1


def test_default_tier2_assets_support_route_filtered_phase_gates(tmp_path: Path) -> None:
    expectations = {
        "issuer": {"current_event_quant", "delay_reason_quant"},
        "owner": {"beneficial_ownership_intent_quant", "source_of_funds_quant"},
        "holding": {"manager_structure_quant", "amendment_scope_quant"},
    }

    for route, field_names in expectations.items():
        result = run_offline_tier2_evaluation(
            regex_config_path=tier2_path("regex", "default.yaml"),
            golden_set_path=tier2_path("golden_set", "default.yaml"),
            fixtures_dir=tier2_path("fixtures"),
            artifacts_dir=tmp_path,
            selectors=OfflineEvalSelectors(route=route),
            run_id=f"phase-gate-{route}",
            min_pass_rate=1.0,
        )

        assert result.summary["selectors"]["route"] == route
        assert result.summary["coverage"]["total_cases"] == 2
        assert result.summary["coverage"]["total_candidates"] == 2
        assert result.summary["metrics"]["pass_rate"] == 1.0

        by_field = json.loads((tmp_path / f"phase-gate-{route}" / "by_field.json").read_text(encoding="utf-8"))
        assert set(by_field.keys()) == field_names
