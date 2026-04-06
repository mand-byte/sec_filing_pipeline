import json

import pytest

from src.pipeline.offline_evaluator import OfflineEvalSelectors, run_offline_tier2_evaluation


def test_offline_evaluator_writes_expected_artifacts(tmp_path):
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    (fixtures_dir / "owner_case_001.txt").write_text(
        "Cover Page\nPurpose of Transaction: The reporting person is activist and seeks board seat representation.\n",
        encoding="utf-8",
    )
    (fixtures_dir / "owner_case_002.txt").write_text(
        "Cover Page\nPurpose of Transaction: The filing discusses only generic narrative without stance keywords.\n",
        encoding="utf-8",
    )

    regex_config = tmp_path / "regex.yaml"
    regex_config.write_text(
        "\n".join(
            [
                "fields:",
                "  beneficial_ownership_intent_quant:",
                "    route: owner",
                "    form_families:",
                "      - 13D",
                "      - 13G",
                "    locators:",
                "      - section_window",
                "      - parse_text_window",
                "    anchor_terms:",
                "      - item 4",
                "      - purpose of transaction",
                "      - cover page",
                "    regex_patterns:",
                "      - '(?i)\\b(passive|engaged|activist|control)\\b'",
                "      - '(?i)\\b(board\\s+seat|proxy\\s+fight|group\\s+formed|strategic\\s+alternatives|merger)\\b'",
                "    output_kind: text",
                "    qa_rules:",
                "      allow_short: true",
                "      allow_medium: true",
                "      allow_long: true",
                "      allow_unclear: true",
            ]
        ),
        encoding="utf-8",
    )

    golden_set = tmp_path / "golden.yaml"
    golden_set.write_text(
        "\n".join(
            [
                "cases:",
                "  - case_id: owner_case_001",
                "    route: owner",
                "    form_type: 13D",
                "    fixture_file: owner_case_001.txt",
                "    sections:",
                "      Purpose of Transaction: The reporting person is activist and seeks board seat representation.",
                "    expected:",
                "      beneficial_ownership_intent_quant:",
                "        status: ok",
                "        value_text: activist",
                "  - case_id: owner_case_002",
                "    route: owner",
                "    form_type: 13D",
                "    fixture_file: owner_case_002.txt",
                "    sections:",
                "      Purpose of Transaction: The filing discusses only generic narrative without stance keywords.",
                "    expected:",
                "      beneficial_ownership_intent_quant:",
                "        status: error",
                "        error_code: PATTERN_NOT_MATCHED",
            ]
        ),
        encoding="utf-8",
    )

    artifacts_dir = tmp_path / "artifacts"
    result = run_offline_tier2_evaluation(
        regex_config_path=regex_config,
        golden_set_path=golden_set,
        fixtures_dir=fixtures_dir,
        artifacts_dir=artifacts_dir,
        selectors=OfflineEvalSelectors(),
        run_id="offline-run-001",
        min_pass_rate=0.95,
    )

    run_dir = artifacts_dir / "offline-run-001"
    assert run_dir.exists()
    assert (run_dir / "summary.json").exists()
    assert (run_dir / "by_field.json").exists()
    assert (run_dir / "failures.ndjson").exists()
    assert (run_dir / "candidates.ndjson").exists()
    assert (run_dir / "diff.md").exists()

    summary_payload = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary_payload["run_id"] == "offline-run-001"
    assert summary_payload["metrics"]["failed"] == 0
    assert result.run_id == "offline-run-001"


def test_offline_evaluator_applies_baseline_and_threshold(tmp_path):
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    (fixtures_dir / "owner_case_001.txt").write_text(
        "Cover Page\nPurpose of Transaction: The reporting person is activist and seeks board seat representation.\n",
        encoding="utf-8",
    )

    regex_config = tmp_path / "regex.yaml"
    regex_config.write_text(
        "\n".join(
            [
                "fields:",
                "  beneficial_ownership_intent_quant:",
                "    route: owner",
                "    form_families:",
                "      - 13D",
                "    locators:",
                "      - section_window",
                "    anchor_terms:",
                "      - purpose of transaction",
                "    regex_patterns:",
                "      - '(?i)\\b(activist)\\b'",
                "    output_kind: text",
                "    qa_rules: {}",
            ]
        ),
        encoding="utf-8",
    )

    golden_set = tmp_path / "golden.yaml"
    golden_set.write_text(
        "\n".join(
            [
                "cases:",
                "  - case_id: owner_case_001",
                "    route: owner",
                "    form_type: 13D",
                "    fixture_file: owner_case_001.txt",
                "    sections:",
                "      Purpose of Transaction: The reporting person is activist and seeks board seat representation.",
                "    expected:",
                "      beneficial_ownership_intent_quant:",
                "        status: ok",
                "        value_text: activist",
            ]
        ),
        encoding="utf-8",
    )

    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "by_field": {
                    "beneficial_ownership_intent_quant": {
                        "total": 1,
                        "matched": 1,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    artifacts_dir = tmp_path / "artifacts"
    result = run_offline_tier2_evaluation(
        regex_config_path=regex_config,
        golden_set_path=golden_set,
        fixtures_dir=fixtures_dir,
        artifacts_dir=artifacts_dir,
        run_id="offline-run-baseline-ok",
        baseline_path=baseline,
        min_pass_rate=0.95,
    )

    assert result.summary["metrics"]["passes_threshold"] is True
    assert result.summary["metrics"]["regressions"] == []


def test_offline_evaluator_raises_on_threshold_violation(tmp_path):
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    (fixtures_dir / "owner_case_001.txt").write_text(
        "Cover Page\nPurpose of Transaction: no keyword here.\n",
        encoding="utf-8",
    )

    regex_config = tmp_path / "regex.yaml"
    regex_config.write_text(
        "\n".join(
            [
                "fields:",
                "  beneficial_ownership_intent_quant:",
                "    route: owner",
                "    form_families:",
                "      - 13D",
                "    locators:",
                "      - section_window",
                "    anchor_terms:",
                "      - purpose of transaction",
                "    regex_patterns:",
                "      - '(?i)\\b(activist)\\b'",
                "    output_kind: text",
                "    qa_rules: {}",
            ]
        ),
        encoding="utf-8",
    )

    golden_set = tmp_path / "golden.yaml"
    golden_set.write_text(
        "\n".join(
            [
                "cases:",
                "  - case_id: owner_case_001",
                "    route: owner",
                "    form_type: 13D",
                "    fixture_file: owner_case_001.txt",
                "    sections:",
                "      Purpose of Transaction: no keyword here.",
                "    expected:",
                "      beneficial_ownership_intent_quant:",
                "        status: ok",
                "        value_text: activist",
            ]
        ),
        encoding="utf-8",
    )

    artifacts_dir = tmp_path / "artifacts"

    with pytest.raises(ValueError, match="pass_rate"):
        run_offline_tier2_evaluation(
            regex_config_path=regex_config,
            golden_set_path=golden_set,
            fixtures_dir=fixtures_dir,
            artifacts_dir=artifacts_dir,
            run_id="offline-run-threshold-fail",
            min_pass_rate=0.95,
        )


def test_offline_evaluator_supports_selectors(tmp_path):
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    (fixtures_dir / "owner_case_001.txt").write_text(
        "Cover Page\nPurpose of Transaction: The reporting person is activist and seeks board seat representation.\n",
        encoding="utf-8",
    )

    regex_config = tmp_path / "regex.yaml"
    regex_config.write_text(
        "\n".join(
            [
                "fields:",
                "  beneficial_ownership_intent_quant:",
                "    route: owner",
                "    form_families:",
                "      - 13D",
                "      - 13G",
                "    locators:",
                "      - section_window",
                "      - parse_text_window",
                "    anchor_terms:",
                "      - item 4",
                "      - purpose of transaction",
                "      - cover page",
                "    regex_patterns:",
                "      - '(?i)\\b(passive|engaged|activist|control)\\b'",
                "      - '(?i)\\b(board\\s+seat|proxy\\s+fight|group\\s+formed|strategic\\s+alternatives|merger)\\b'",
                "    output_kind: text",
                "    qa_rules:",
                "      allow_short: true",
                "      allow_medium: true",
                "      allow_long: true",
                "      allow_unclear: true",
            ]
        ),
        encoding="utf-8",
    )

    golden_set = tmp_path / "golden.yaml"
    golden_set.write_text(
        "\n".join(
            [
                "cases:",
                "  - case_id: owner_case_001",
                "    route: owner",
                "    form_type: 13D",
                "    fixture_file: owner_case_001.txt",
                "    sections:",
                "      Purpose of Transaction: The reporting person is activist and seeks board seat representation.",
                "    expected:",
                "      beneficial_ownership_intent_quant:",
                "        status: ok",
                "        value_text: activist",
            ]
        ),
        encoding="utf-8",
    )

    artifacts_dir = tmp_path / "artifacts"
    result = run_offline_tier2_evaluation(
        regex_config_path=regex_config,
        golden_set_path=golden_set,
        fixtures_dir=fixtures_dir,
        artifacts_dir=artifacts_dir,
        selectors=OfflineEvalSelectors(route="owner", form_family="13D", field_name="beneficial_ownership_intent_quant", case_id="owner_case_001"),
        run_id="offline-run-002",
        min_pass_rate=0.95,
    )

    summary_payload = result.summary
    assert summary_payload["coverage"]["total_candidates"] == 1
    assert summary_payload["metrics"]["passed"] == 1


def test_offline_evaluator_writes_spec_not_found_when_field_missing(tmp_path):
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    (fixtures_dir / "owner_case_001.txt").write_text(
        "Cover Page\nPurpose of Transaction: activist\n",
        encoding="utf-8",
    )

    regex_config = tmp_path / "regex.yaml"
    regex_config.write_text("fields: {}\n", encoding="utf-8")

    golden_set = tmp_path / "golden.yaml"
    golden_set.write_text(
        "\n".join(
            [
                "cases:",
                "  - case_id: owner_case_001",
                "    route: owner",
                "    form_type: 13D",
                "    fixture_file: owner_case_001.txt",
                "    expected:",
                "      non_existent_field:",
                "        status: error",
                "        error_code: SPEC_NOT_FOUND",
            ]
        ),
        encoding="utf-8",
    )

    artifacts_dir = tmp_path / "artifacts"
    result = run_offline_tier2_evaluation(
        regex_config_path=regex_config,
        golden_set_path=golden_set,
        fixtures_dir=fixtures_dir,
        artifacts_dir=artifacts_dir,
        run_id="offline-run-spec-missing",
        min_pass_rate=0.95,
    )

    assert result.summary["metrics"]["failed"] == 0


def test_offline_evaluator_writes_fixture_not_found_when_file_missing(tmp_path):
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    regex_config = tmp_path / "regex.yaml"
    regex_config.write_text("fields: {}\n", encoding="utf-8")

    golden_set = tmp_path / "golden.yaml"
    golden_set.write_text(
        "\n".join(
            [
                "cases:",
                "  - case_id: owner_case_001",
                "    route: owner",
                "    form_type: 13D",
                "    fixture_file: missing.txt",
                "    expected:",
                "      beneficial_ownership_intent_quant:",
                "        status: error",
                "        error_code: FIXTURE_NOT_FOUND",
            ]
        ),
        encoding="utf-8",
    )

    artifacts_dir = tmp_path / "artifacts"
    result = run_offline_tier2_evaluation(
        regex_config_path=regex_config,
        golden_set_path=golden_set,
        fixtures_dir=fixtures_dir,
        artifacts_dir=artifacts_dir,
        run_id="offline-run-fixture-missing",
        min_pass_rate=0.95,
    )

    assert result.summary["metrics"]["failed"] == 0
