from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.pipeline.offline_evaluator import OfflineEvalSelectors, run_offline_tier2_evaluation


def test_run_offline_tier2_evaluation_writes_strict_v2_artifacts(tmp_path: Path) -> None:
    regex_config_path = tmp_path / "regex.yaml"
    golden_set_path = tmp_path / "golden.yaml"
    fixtures_dir = tmp_path / "fixtures"
    artifacts_dir = tmp_path / "artifacts"
    fixtures_dir.mkdir()

    regex_config_path.write_text(
        """
fields:
  current_event_quant:
    route: issuer
    form_families: [8-K]
    locators: [parse_text_window]
    anchor_terms: [item]
    regex_patterns: ['(?i)event']
    output_kind: text
    qa_rules: {}
""".strip(),
        encoding="utf-8",
    )

    golden_set_path.write_text(
        """
cases:
  - case_id: case-001
    route: issuer
    form_type: 8-K
    fixture_file: case-001.txt
    expected:
      current_event_quant:
        status: ok
        value_text: event
        truth_tier: gold
  - case_id: case-002
    route: issuer
    form_type: 8-K
    fixture_file: case-002.txt
    expected:
      current_event_quant:
        status: ok
        value_text: event
        truth_tier: silver
invariants:
  - case_id: case-001
    name: cash_nonnegative
    status: pass
""".strip(),
        encoding="utf-8",
    )

    (fixtures_dir / "case-001.txt").write_text("Item 1. Event details", encoding="utf-8")
    (fixtures_dir / "case-002.txt").write_text("Item 2. Event update", encoding="utf-8")

    result = run_offline_tier2_evaluation(
        regex_config_path=regex_config_path,
        golden_set_path=golden_set_path,
        fixtures_dir=fixtures_dir,
        artifacts_dir=artifacts_dir,
        selectors=OfflineEvalSelectors(route="issuer"),
        run_id="strict-run-001",
        min_pass_rate=1.0,
    )

    assert result.run_id == "strict-run-001"
    assert result.summary["coverage"]["gold_applicable_rows"] == 1
    assert result.summary["coverage"]["silver_applicable_rows"] == 1
    assert result.summary["coverage"]["invariant_rows"] == 1
    assert result.summary["metrics"]["gold_strict_accuracy"] == 1.0
    assert result.summary["metrics"]["silver_alignment"] == 1.0
    assert result.summary["metrics"]["invariant_pass_rate"] == 1.0

    run_dir = artifacts_dir / "strict-run-001"
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["config_paths"]["regex_config"] == str(regex_config_path)
    assert manifest["applied_filters"]["route"] == "issuer"

    coverage = json.loads((run_dir / "coverage.json").read_text(encoding="utf-8"))
    assert coverage["total_candidates"] == 2

    silver_alignment_rows = (run_dir / "silver_alignment.ndjson").read_text(encoding="utf-8").strip().splitlines()
    assert len(silver_alignment_rows) == 1

    invariant_rows = (run_dir / "invariants.ndjson").read_text(encoding="utf-8").strip().splitlines()
    assert len(invariant_rows) == 1

    review_packets_dir = run_dir / "review_packets"
    assert review_packets_dir.exists()
    assert list(review_packets_dir.iterdir()) == []


def test_run_offline_tier2_evaluation_rejects_fixture_path_escape(tmp_path: Path) -> None:
    regex_config_path = tmp_path / "regex.yaml"
    golden_set_path = tmp_path / "golden.yaml"
    fixtures_dir = tmp_path / "fixtures"
    artifacts_dir = tmp_path / "artifacts"
    fixtures_dir.mkdir()

    regex_config_path.write_text(
        """
fields:
  current_event_quant:
    route: issuer
    form_families: [8-K]
    locators: [parse_text_window]
    anchor_terms: [item]
    regex_patterns: ['(?i)event']
    output_kind: text
    qa_rules: {}
""".strip(),
        encoding="utf-8",
    )

    golden_set_path.write_text(
        """
cases:
  - case_id: case-001
    route: issuer
    form_type: 8-K
    fixture_file: ../escape.txt
    expected:
      current_event_quant:
        status: error
        error_code: FIXTURE_NOT_FOUND
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="fixture_file escapes fixtures_dir"):
        run_offline_tier2_evaluation(
            regex_config_path=regex_config_path,
            golden_set_path=golden_set_path,
            fixtures_dir=fixtures_dir,
            artifacts_dir=artifacts_dir,
            run_id="strict-run-escape",
        )


def test_run_offline_tier2_evaluation_treats_empty_fixture_as_existing(tmp_path: Path) -> None:
    regex_config_path = tmp_path / "regex.yaml"
    golden_set_path = tmp_path / "golden.yaml"
    fixtures_dir = tmp_path / "fixtures"
    artifacts_dir = tmp_path / "artifacts"
    fixtures_dir.mkdir()

    regex_config_path.write_text(
        """
fields:
  current_event_quant:
    route: issuer
    form_families: [8-K]
    locators: [parse_text_window]
    anchor_terms: [item]
    regex_patterns: ['(?i)event']
    output_kind: text
    qa_rules: {}
""".strip(),
        encoding="utf-8",
    )

    golden_set_path.write_text(
        """
cases:
  - case_id: case-001
    route: issuer
    form_type: 8-K
    fixture_file: empty.txt
    expected:
      current_event_quant:
        status: error
        error_code: WINDOW_NOT_FOUND
        truth_tier: gold
""".strip(),
        encoding="utf-8",
    )

    (fixtures_dir / "empty.txt").write_text("", encoding="utf-8")

    result = run_offline_tier2_evaluation(
        regex_config_path=regex_config_path,
        golden_set_path=golden_set_path,
        fixtures_dir=fixtures_dir,
        artifacts_dir=artifacts_dir,
        run_id="strict-run-empty",
        min_pass_rate=1.0,
    )

    assert result.summary["metrics"]["pass_rate"] == 1.0


def test_run_offline_tier2_evaluation_tracks_not_applicable_separately(tmp_path: Path) -> None:
    regex_config_path = tmp_path / "regex.yaml"
    golden_set_path = tmp_path / "golden.yaml"
    fixtures_dir = tmp_path / "fixtures"
    artifacts_dir = tmp_path / "artifacts"
    fixtures_dir.mkdir()

    regex_config_path.write_text(
        """
fields:
  current_event_quant:
    route: issuer
    form_families: [8-K]
    locators: [parse_text_window]
    anchor_terms: [item]
    regex_patterns: ['(?i)event']
    output_kind: text
    qa_rules: {}
""".strip(),
        encoding="utf-8",
    )

    golden_set_path.write_text(
        """
cases:
  - case_id: case-na
    route: issuer
    form_type: 8-K
    fixture_file: case-na.txt
    expected:
      current_event_quant:
        is_applicable: false
        truth_tier: gold
""".strip(),
        encoding="utf-8",
    )

    (fixtures_dir / "case-na.txt").write_text("Item 1. Event details", encoding="utf-8")

    run_offline_tier2_evaluation(
        regex_config_path=regex_config_path,
        golden_set_path=golden_set_path,
        fixtures_dir=fixtures_dir,
        artifacts_dir=artifacts_dir,
        run_id="strict-run-na",
        min_pass_rate=1.0,
    )

    by_field = json.loads((artifacts_dir / "strict-run-na" / "by_field.json").read_text(encoding="utf-8"))
    assert by_field["current_event_quant"]["not_applicable"] == 1
    assert by_field["current_event_quant"]["error"] == 0
