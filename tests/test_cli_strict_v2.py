from __future__ import annotations

from decimal import Decimal
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
            }
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


def test_coerce_numeric_value_rejects_non_finite_numbers() -> None:
    assert cli_module._coerce_numeric_value(float("nan")) is None
    assert cli_module._coerce_numeric_value(float("inf")) is None
    assert cli_module._coerce_numeric_value("NaN") is None
    assert cli_module._coerce_numeric_value("Infinity") is None
    assert cli_module._coerce_numeric_value(Decimal("42.5")) == 42.5
