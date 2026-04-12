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
phase_gates:
  - name: issuer_smoke_gate
    applies_when:
      route: issuer
    coverage:
      total_cases: 2
      total_candidates: 2
      required_fields: [current_event_quant]
      required_routes: [issuer]
      required_form_types: [8-K]
    metrics:
      pass_rate: 1.0
      min_gold_strict_accuracy: 1.0
      min_silver_alignment: 1.0
      min_invariant_pass_rate: 1.0
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

    phase_gates = json.loads((run_dir / "phase_gates.json").read_text(encoding="utf-8"))
    assert phase_gates == [{"name": "issuer_smoke_gate", "status": "passed", "violations": []}]
    assert result.summary["phase_gates"] == {"total": 1, "passed": 1, "failed": 0, "skipped": 0}

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


def test_run_offline_tier2_evaluation_rejects_incomplete_tier2_override(tmp_path: Path) -> None:
    regex_config_path = tmp_path / "regex.yaml"
    golden_set_path = tmp_path / "golden.yaml"
    fixtures_dir = tmp_path / "fixtures"
    artifacts_dir = tmp_path / "artifacts"
    fixtures_dir.mkdir()

    regex_config_path.write_text(
        """
fields:
  delay_reason_quant:
    route: issuer
    form_families: [NT 10-Q]
    locators: [section_window]
""".strip(),
        encoding="utf-8",
    )
    golden_set_path.write_text("cases: []", encoding="utf-8")

    with pytest.raises(ValueError, match="tier2 regex field override must be self-sufficient"):
        run_offline_tier2_evaluation(
            regex_config_path=regex_config_path,
            golden_set_path=golden_set_path,
            fixtures_dir=fixtures_dir,
            artifacts_dir=artifacts_dir,
            run_id="strict-run-invalid-tier2",
        )


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


def test_run_offline_tier2_evaluation_matches_expected_value_json(monkeypatch, tmp_path: Path) -> None:
    regex_config_path = tmp_path / "regex.yaml"
    golden_set_path = tmp_path / "golden.yaml"
    fixtures_dir = tmp_path / "fixtures"
    artifacts_dir = tmp_path / "artifacts"
    fixtures_dir.mkdir()

    regex_config_path.write_text(
        """
fields:
  beneficial_ownership_intent_quant:
    route: owner
    form_families: [13D]
    locators: [section_window]
    anchor_terms: ["purpose of transaction"]
    regex_patterns: ['(?i)passive']
    output_kind: text
    qa_rules: {}
""".strip(),
        encoding="utf-8",
    )

    golden_set_path.write_text(
        """
cases:
  - case_id: case-001
    route: owner
    form_type: 13D
    fixture_file: case-001.txt
    expected:
      beneficial_ownership_intent_quant:
        status: ok
        value_json:
          stance: passive
          group_formed: false
          horizon: medium
        truth_tier: gold
""".strip(),
        encoding="utf-8",
    )
    (fixtures_dir / "case-001.txt").write_text("Purpose of Transaction\nPassive investor", encoding="utf-8")

    class FakeTextExtractionEngine:
        def extract_field(self, *, filing, field_spec):
            del filing, field_spec
            return {
                "status": "ok",
                "value_text": "Passive investor",
                "value_json": json.dumps(
                    {
                        "stance": "passive",
                        "group_formed": False,
                        "horizon": "medium",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "locator_kind": "section_window",
                "locator_path": "sections[Purpose of Transaction]",
                "source_span": "0:7",
            }

    monkeypatch.setattr("src.pipeline.offline_evaluator.TextExtractionEngine", FakeTextExtractionEngine)

    result = run_offline_tier2_evaluation(
        regex_config_path=regex_config_path,
        golden_set_path=golden_set_path,
        fixtures_dir=fixtures_dir,
        artifacts_dir=artifacts_dir,
        run_id="strict-run-json",
        min_pass_rate=1.0,
    )

    assert result.summary["metrics"]["pass_rate"] == 1.0
    candidates = (artifacts_dir / "strict-run-json" / "candidates.ndjson").read_text(encoding="utf-8").strip().splitlines()
    assert len(candidates) == 1
    payload = json.loads(candidates[0])
    assert json.loads(payload["value_json"])["stance"] == "passive"
    assert payload["matched"] is True


def test_run_offline_tier2_evaluation_rejects_phase_gate_failure(tmp_path: Path) -> None:
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
phase_gates:
  - name: impossible_seed_gate
    coverage:
      min_total_cases: 2
      required_routes: [issuer, owner]
    metrics:
      min_gold_strict_accuracy: 1.0
""".strip(),
        encoding="utf-8",
    )
    (fixtures_dir / "case-001.txt").write_text("Item 1. Event details", encoding="utf-8")

    with pytest.raises(ValueError, match="phase gate failure: impossible_seed_gate"):
        run_offline_tier2_evaluation(
            regex_config_path=regex_config_path,
            golden_set_path=golden_set_path,
            fixtures_dir=fixtures_dir,
            artifacts_dir=artifacts_dir,
            run_id="strict-run-gate-fail",
            min_pass_rate=1.0,
        )

    phase_gates = json.loads((artifacts_dir / "strict-run-gate-fail" / "phase_gates.json").read_text(encoding="utf-8"))
    assert phase_gates[0]["status"] == "failed"
    assert {violation["key"] for violation in phase_gates[0]["violations"]} == {
        "min_total_cases",
        "required_routes",
    }
