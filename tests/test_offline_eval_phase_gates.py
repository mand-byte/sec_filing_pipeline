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
        "total_cases": 15,
        "total_candidates": 15,
        "gold_applicable_rows": 15,
        "silver_applicable_rows": 0,
        "invariant_rows": 0,
    }
    assert result.summary["metrics"]["pass_rate"] == 1.0
    assert result.summary["metrics"]["gold_strict_accuracy"] == 1.0

    by_field = json.loads((tmp_path / "phase-gate-default" / "by_field.json").read_text(encoding="utf-8"))
    assert by_field["mdna_outlook_quant"]["matched"] == 1
    assert by_field["risk_factor_quant"]["matched"] == 1
    assert by_field["current_event_quant"]["matched"] == 1
    assert by_field["delay_reason_quant"]["matched"] == 1
    assert by_field["use_of_proceeds_quant"]["matched"] == 1
    assert by_field["proxy_proposal_quant"]["matched"] == 1
    assert by_field["comp_policy_quant"]["matched"] == 1
    assert by_field["tender_going_private_quant"]["matched"] == 1
    assert by_field["beneficial_ownership_intent_quant"]["matched"] == 1
    assert by_field["insider_transaction_quant"]["matched"] == 1
    assert by_field["insider_role_ownership_structure_quant"]["matched"] == 1
    assert by_field["source_of_funds_quant"]["matched"] == 1
    assert by_field["rule144_sale_plan_quant"]["matched"] == 1
    assert by_field["manager_structure_quant"]["matched"] == 1
    assert by_field["amendment_scope_quant"]["matched"] == 1


def test_default_tier2_assets_support_route_filtered_phase_gates(tmp_path: Path) -> None:
    expectations = {
        "issuer": {
            "mdna_outlook_quant",
            "risk_factor_quant",
            "current_event_quant",
            "delay_reason_quant",
            "use_of_proceeds_quant",
            "proxy_proposal_quant",
            "comp_policy_quant",
            "tender_going_private_quant",
        },
        "owner": {
            "beneficial_ownership_intent_quant",
            "insider_transaction_quant",
            "insider_role_ownership_structure_quant",
            "source_of_funds_quant",
            "rule144_sale_plan_quant",
        },
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
        assert result.summary["coverage"]["total_cases"] == len(field_names)
        assert result.summary["coverage"]["total_candidates"] == len(field_names)
        assert result.summary["metrics"]["pass_rate"] == 1.0

        by_field = json.loads((tmp_path / f"phase-gate-{route}" / "by_field.json").read_text(encoding="utf-8"))
        assert set(by_field.keys()) == field_names
