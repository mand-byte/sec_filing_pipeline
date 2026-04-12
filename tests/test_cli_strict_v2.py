from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path

from typer.testing import CliRunner

import src.cli as cli_module


runner = CliRunner()


def test_strict_v2_eval_command_invokes_evaluator_and_prints_summary(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakeResult:
        run_id = "strict-run-001"
        summary = {
            "metrics": {
                "passed": 5,
                "failed": 1,
                "gold_strict_accuracy": 0.9,
                "silver_alignment": 1.0,
            },
            "phase_gates": {
                "total": 2,
                "passed": 1,
                "failed": 1,
                "skipped": 0,
            },
        }

    def fake_run_offline_tier2_evaluation(**kwargs: object) -> FakeResult:
        captured.update(kwargs)
        return FakeResult()

    monkeypatch.setattr(cli_module, "run_offline_tier2_evaluation", fake_run_offline_tier2_evaluation)

    result = runner.invoke(
        cli_module.app,
        [
            "strict-v2-eval",
            "--regex-config",
            str(tmp_path / "regex.yaml"),
            "--golden-set",
            str(tmp_path / "golden.yaml"),
            "--fixtures-dir",
            str(tmp_path / "fixtures"),
            "--artifacts-dir",
            str(tmp_path / "artifacts"),
            "--route",
            "issuer",
            "--form-family",
            "8-K",
            "--field",
            "current_event_quant",
            "--case-id",
            "case-001",
            "--baseline",
            str(tmp_path / "baseline.json"),
            "--min-pass-rate",
            "0.99",
        ],
    )

    assert result.exit_code == 0
    assert "strict-v2 run_id: strict-run-001" in result.stdout
    assert "strict-v2 metrics: passed=5 failed=1 gold_strict_accuracy=0.9000 silver_alignment=1.0000" in result.stdout
    assert "strict-v2 phase-gates: total=2 passed=1 failed=1 skipped=0" in result.stdout
    assert captured["regex_config_path"] == tmp_path / "regex.yaml"
    assert captured["golden_set_path"] == tmp_path / "golden.yaml"
    assert captured["fixtures_dir"] == tmp_path / "fixtures"
    assert captured["artifacts_dir"] == tmp_path / "artifacts"
    assert captured["baseline_path"] == tmp_path / "baseline.json"
    assert captured["min_pass_rate"] == 0.99

    selectors = captured["selectors"]
    assert isinstance(selectors, cli_module.OfflineEvalSelectors)
    assert selectors.route == "issuer"
    assert selectors.form_family == "8-K"
    assert selectors.field_name == "current_event_quant"
    assert selectors.case_id == "case-001"


def test_strict_v2_eval_rejects_out_of_range_min_pass_rate(tmp_path: Path) -> None:
    result = runner.invoke(
        cli_module.app,
        [
            "strict-v2-eval",
            "--regex-config",
            str(tmp_path / "regex.yaml"),
            "--golden-set",
            str(tmp_path / "golden.yaml"),
            "--fixtures-dir",
            str(tmp_path / "fixtures"),
            "--artifacts-dir",
            str(tmp_path / "artifacts"),
            "--min-pass-rate",
            "1.5",
        ],
    )

    assert result.exit_code != 0
    assert "1.5 is not in the range 0.0<=x<=1.0" in result.output


def test_strict_v2_eval_rejects_partial_numeric_batch_args(tmp_path: Path) -> None:
    result = runner.invoke(
        cli_module.app,
        [
            "strict-v2-eval",
            "--numeric-batch-golden-path",
            str(tmp_path / "golden.yaml"),
        ],
    )

    assert result.exit_code != 0
    assert "--numeric-batch-snapshot-dir" in result.output


def test_strict_v2_eval_numeric_batch_mode_invokes_batch_evaluator(monkeypatch, tmp_path: Path) -> None:
    class FakeResult:
        summary = {
            "metrics": {
                "total_batches": 2,
                "total_field_checks": 4,
                "passed": 3,
                "failed": 1,
                "candidate_recall": 1.0,
                "top1_accuracy": 0.75,
                "batch_all_match_rate": 0.5,
            },
            "phase_gates": {
                "total": 1,
                "passed": 1,
                "failed": 0,
                "skipped": 0,
            },
        }
        by_field = {
            "total_revenue": {
                "total": 2,
                "candidate_recall": 1.0,
                "top1_accuracy": 0.5,
            }
        }
        failures = [{"case_id": "case-001", "field_name": "total_revenue", "expected": "fact-1", "actual": "fact-2"}]
        phase_gates = [{"name": "numeric_batch_smoke", "status": "passed", "violations": []}]
        review_packets = [
            {
                "case_id": "case-001",
                "subject_key": "document",
                "field_name": "total_revenue",
                "expected": {"selected_candidate_key": "fact-1"},
                "actual": {"selected_candidate_key": "fact-2", "candidate_keys": ["fact-1", "fact-2"]},
            }
        ]

    captured: dict[str, object] = {}

    def fake_evaluate_10q_numeric_batch(*, golden_path: Path, snapshot_dir: Path):
        captured["golden_path"] = golden_path
        captured["snapshot_dir"] = snapshot_dir
        return FakeResult()

    monkeypatch.setattr(cli_module, "evaluate_10q_numeric_batch", fake_evaluate_10q_numeric_batch)
    monkeypatch.setattr(cli_module, "make_run_id", lambda: "numeric-batch-run-001")

    result = runner.invoke(
        cli_module.app,
        [
            "strict-v2-eval",
            "--numeric-batch-golden-path",
            str(tmp_path / "batch_golden.yaml"),
            "--numeric-batch-snapshot-dir",
            str(tmp_path / "snapshots"),
            "--artifacts-dir",
            str(tmp_path / "artifacts"),
            "--min-pass-rate",
            "0.7",
        ],
    )

    assert result.exit_code == 0
    assert captured["golden_path"] == tmp_path / "batch_golden.yaml"
    assert captured["snapshot_dir"] == tmp_path / "snapshots"
    assert "strict-v2 run_id: numeric-batch-run-001" in result.stdout
    assert "strict-v2 metrics: passed=3 failed=1 gold_strict_accuracy=0.7500 silver_alignment=0.0000" in result.stdout
    assert "strict-v2 phase-gates: total=1 passed=1 failed=0 skipped=0" in result.stdout

    summary = json.loads((tmp_path / "artifacts" / "numeric-batch-run-001" / "summary.json").read_text(encoding="utf-8"))
    assert summary["selectors"]["mode"] == "numeric_batch"
    assert summary["metrics"]["batch_all_match_rate"] == 0.5
    assert summary["metrics"]["passes_threshold"] is True
    phase_gates = json.loads((tmp_path / "artifacts" / "numeric-batch-run-001" / "phase_gates.json").read_text(encoding="utf-8"))
    assert phase_gates == [{"name": "numeric_batch_smoke", "status": "passed", "violations": []}]
    review_packets = sorted((tmp_path / "artifacts" / "numeric-batch-run-001" / "review_packets").iterdir())
    assert len(review_packets) == 1


def test_golden_10q_numeric_batch_command_routes_through_strict_v2_numeric_helper(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_run_strict_v2_numeric_batch_eval(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(cli_module, "_run_strict_v2_numeric_batch_eval", fake_run_strict_v2_numeric_batch_eval)

    result = runner.invoke(
        cli_module.app,
        [
            "golden-10q-numeric-batch",
            "--golden-path",
            str(tmp_path / "golden.yaml"),
            "--snapshot-dir",
            str(tmp_path / "snapshots"),
            "--artifacts-dir",
            str(tmp_path / "artifacts"),
            "--min-pass-rate",
            "0.8",
        ],
    )

    assert result.exit_code == 0
    assert captured["golden_path"] == str(tmp_path / "golden.yaml")
    assert captured["snapshot_dir"] == str(tmp_path / "snapshots")
    assert captured["artifacts_dir"] == str(tmp_path / "artifacts")
    assert captured["min_pass_rate"] == 0.8


def test_coerce_numeric_value_rejects_non_finite_numbers() -> None:
    assert cli_module._coerce_numeric_value(float("nan")) is None
    assert cli_module._coerce_numeric_value(float("inf")) is None
    assert cli_module._coerce_numeric_value("NaN") is None
    assert cli_module._coerce_numeric_value("Infinity") is None
    assert cli_module._coerce_numeric_value(Decimal("42.5")) == 42.5
