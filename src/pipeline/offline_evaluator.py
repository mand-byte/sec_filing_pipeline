from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.pipeline.edgar_provider import classify_form_family
from src.pipeline.strict_v2_gates import evaluate_phase_gates
from src.pipeline.strict_v2_summary import build_strict_v2_summary
from src.pipeline.extraction.text_contracts import TextFieldSpec
from src.pipeline.extraction.text_engine import TextExtractionEngine
from src.pipeline.extraction.text_registry import all_text_field_specs
from src.pipeline.offline_artifacts import write_run_artifacts
from src.pipeline.scheduler import make_run_id

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


@dataclass(frozen=True)
class OfflineEvalSelectors:
    route: str | None = None
    form_family: str | None = None
    field_name: str | None = None
    case_id: str | None = None


@dataclass(frozen=True)
class OfflineEvalResult:
    run_id: str
    summary: dict[str, Any]


@dataclass(frozen=True)
class _OfflineFixtureFiling:
    parse_text: str
    section_payload: object | None

    def parse(self) -> str:
        """Expose the fixture text through the filing parse surface."""
        return self.parse_text

    def text(self) -> str:
        """Expose the fixture text through the filing text surface."""
        return self.parse_text

    def sections(self) -> object | None:
        """Expose the optional structured section payload for the fixture."""
        return self.section_payload


FieldKey = tuple[str, str]


def _require_yaml() -> Any:
    """Require the optional PyYAML dependency for offline evaluation."""
    if yaml is None:
        raise RuntimeError("PyYAML is required for offline evaluator")
    return yaml


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    """Load a YAML mapping file and reject non-mapping roots."""
    parser = _require_yaml()
    payload = parser.safe_load(path.read_text(encoding="utf-8"))
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return dict(payload)


def _resolve_fixture_path(*, fixtures_dir: Path, fixture_file: str) -> Path:
    """Resolve a fixture path while preventing directory traversal."""
    fixtures_root = fixtures_dir.resolve()
    candidate = (fixtures_root / fixture_file).resolve()
    if candidate.parent != fixtures_root and fixtures_root not in candidate.parents:
        raise ValueError(f"fixture_file escapes fixtures_dir: {fixture_file}")
    return candidate


def _as_string_tuple(values: object) -> tuple[str, ...]:
    """Normalize a sequence-like config value into a tuple of strings."""
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ValueError("Expected sequence of strings")
    return tuple(str(value) for value in values)


def _validate_field_override_shape(*, field_name: str, override: Mapping[str, Any]) -> None:
    """Validate that a tier2 field override is self-sufficient."""
    required_keys = (
        "route",
        "form_families",
        "locators",
        "anchor_terms",
        "regex_patterns",
        "output_kind",
        "qa_rules",
    )
    missing_keys = [key for key in required_keys if key not in override]
    if missing_keys:
        raise ValueError(
            f"tier2 regex field override must be self-sufficient for {field_name}: "
            + ", ".join(missing_keys)
        )

    output_kind = str(override.get("output_kind", "")).strip().lower()
    if output_kind == "json":
        json_required = [key for key in ("output_schema", "normalizer_overrides") if key not in override]
        if json_required:
            raise ValueError(
                f"tier2 regex json field override must define {field_name}: "
                + ", ".join(json_required)
            )


def _apply_field_override(spec: TextFieldSpec, override: Mapping[str, Any]) -> TextFieldSpec:
    """Apply one tier2 regex override onto a base runtime text spec."""
    route = str(override.get("route", spec.route))

    form_families_value = override.get("form_families", spec.form_families)
    form_families = tuple(form.upper() for form in _as_string_tuple(form_families_value))

    locators_value = override.get("locators", spec.locators)
    locators = _as_string_tuple(locators_value)

    anchor_terms_value = override.get("anchor_terms", spec.anchor_terms)
    anchor_terms = _as_string_tuple(anchor_terms_value)

    regex_patterns_value = override.get("regex_patterns", spec.regex_patterns)
    regex_patterns = _as_string_tuple(regex_patterns_value)

    output_kind = str(override.get("output_kind", spec.output_kind))
    output_schema = override.get("output_schema", spec.output_schema)
    output_schema_ref = str(output_schema).strip() if isinstance(output_schema, str) and output_schema.strip() else None

    qa_rules_raw = override.get("qa_rules", spec.qa_rules)
    if not isinstance(qa_rules_raw, Mapping):
        raise ValueError("qa_rules override must be a mapping")
    qa_rules = dict(qa_rules_raw)
    normalizer_overrides_raw = override.get("normalizer_overrides", spec.normalizer_overrides or {})
    if not isinstance(normalizer_overrides_raw, Mapping):
        raise ValueError("normalizer_overrides must be a mapping")
    normalizer_overrides = dict(normalizer_overrides_raw)

    return TextFieldSpec(
        field_name=spec.field_name,
        route=route,  # type: ignore[arg-type]
        form_families=form_families,
        locators=locators,  # type: ignore[arg-type]
        anchor_terms=anchor_terms,
        regex_patterns=regex_patterns,
        output_kind=output_kind,  # type: ignore[arg-type]
        qa_rules=qa_rules,
        output_schema=output_schema_ref,
        normalizer_overrides=normalizer_overrides,
    )


def _build_spec_map(regex_config: Mapping[str, Any]) -> dict[FieldKey, TextFieldSpec]:
    """Build the effective text-spec map after applying regex overrides."""
    base_specs = all_text_field_specs()
    spec_map: dict[FieldKey, TextFieldSpec] = {(spec.route, spec.field_name): spec for spec in base_specs}

    field_overrides_raw = regex_config.get("fields", {})
    if not isinstance(field_overrides_raw, Mapping):
        return spec_map

    for field_name_raw, override_raw in field_overrides_raw.items():
        field_name = str(field_name_raw)
        if not isinstance(override_raw, Mapping):
            continue
        _validate_field_override_shape(field_name=field_name, override=override_raw)

        target_route_raw = override_raw.get("route")
        if target_route_raw is not None:
            key = (str(target_route_raw), field_name)
            existing_spec = spec_map.get(key)
            if existing_spec is not None:
                spec_map[key] = _apply_field_override(existing_spec, override_raw)
            continue

        matching_keys = [key for key in spec_map.keys() if key[1] == field_name]
        for key in matching_keys:
            spec_map[key] = _apply_field_override(spec_map[key], override_raw)

    return spec_map


def _update_by_field(
    *,
    by_field: dict[str, dict[str, int]],
    field_name: str,
    matched: bool,
    status: str,
) -> None:
    """Accumulate per-field offline evaluation counters."""
    stats = by_field.setdefault(
        field_name,
        {"total": 0, "matched": 0, "failed": 0, "ok": 0, "error": 0, "not_applicable": 0},
    )
    stats["total"] += 1
    if status == "ok":
        stats["ok"] += 1
    elif status == "error":
        stats["error"] += 1
    elif status == "not_applicable":
        stats["not_applicable"] += 1
    if matched:
        stats["matched"] += 1
    else:
        stats["failed"] += 1


def _load_baseline(path: Path) -> dict[str, Any]:
    """Load a baseline summary file for regression comparisons."""
    if not path.exists():
        raise ValueError(f"baseline file not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"baseline root must be a mapping: {path}")
    return dict(payload)


def _matched_rate(field_stats: Mapping[str, Any]) -> float:
    """Compute the matched-rate metric from a per-field summary row."""
    total = field_stats.get("total")
    matched = field_stats.get("matched")
    if not isinstance(total, int) or total <= 0:
        return 0.0
    if not isinstance(matched, int):
        return 0.0
    return matched / total


def _build_diff_markdown(failures: list[dict[str, Any]], regressions: list[str]) -> str:
    """Render the failures/regressions section for offline diff artifacts."""
    if not failures and not regressions:
        return "# Diff\n- no failures\n- no regressions vs baseline"

    lines = ["# Diff"]
    for failure in failures:
        lines.append(
            "- "
            + f"{failure.get('case_id')}::{failure.get('field_name')} "
            + f"expected={failure.get('expected')} actual={failure.get('actual')}"
        )

    for regression in regressions:
        lines.append(f"- baseline regression: {regression}")

    return "\n".join(lines)


def _subject_key_for_candidate(candidate: Mapping[str, Any]) -> str:
    """Choose the subject key to use when exporting review packets."""
    for key in ("subject_key", "subject_id"):
        value = candidate.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
    return "document"


def _matches_expected_ok_value(*, expected_value: Mapping[str, Any], candidate: Mapping[str, Any]) -> bool:
    """Compare a successful candidate payload against the expected value."""
    if candidate.get("status") != "ok":
        return False

    if "value_json" in expected_value:
        actual_value_json = candidate.get("value_json")
        if not isinstance(actual_value_json, str):
            return False
        try:
            actual_payload = json.loads(actual_value_json)
        except json.JSONDecodeError:
            return False
        return actual_payload == expected_value.get("value_json")

    expected_text = str(expected_value.get("value_text", "")).strip().casefold()
    actual_text = str(candidate.get("value_text", "")).strip().casefold()
    return actual_text == expected_text


def _build_manifest(
    *,
    run_id: str,
    regex_config_path: Path,
    golden_set_path: Path,
    fixtures_dir: Path,
    selectors: OfflineEvalSelectors,
    baseline_path: Path | None,
) -> dict[str, Any]:
    """Build the offline-evaluator artifact manifest payload."""
    return {
        "run_id": run_id,
        "config_paths": {
            "regex_config": str(regex_config_path),
            "golden_set": str(golden_set_path),
            "fixtures_dir": str(fixtures_dir),
            "baseline": str(baseline_path) if baseline_path is not None else None,
        },
        "applied_filters": {
            "route": selectors.route,
            "form_family": selectors.form_family,
            "field_name": selectors.field_name,
            "case_id": selectors.case_id,
        },
        "source_snapshot_hashes": {},
        "git_sha": None,
    }


def run_offline_tier2_evaluation(
    *,
    regex_config_path: Path,
    golden_set_path: Path,
    fixtures_dir: Path,
    artifacts_dir: Path,
    selectors: OfflineEvalSelectors | None = None,
    run_id: str | None = None,
    baseline_path: Path | None = None,
    min_pass_rate: float = 0.95,
) -> OfflineEvalResult:
    """Run the offline tier2 evaluator and write strict-v2 artifacts."""
    selectors = selectors or OfflineEvalSelectors()
    run_id_value = run_id or make_run_id()

    regex_config = _load_yaml_mapping(regex_config_path)
    golden_set = _load_yaml_mapping(golden_set_path)
    spec_map = _build_spec_map(regex_config)
    engine = TextExtractionEngine()

    cases_raw = golden_set.get("cases", [])
    if not isinstance(cases_raw, list):
        raise ValueError("golden_set 'cases' must be a list")

    selected_route = selectors.route
    selected_form_family = selectors.form_family.upper() if selectors.form_family else None
    selected_field = selectors.field_name
    selected_case_id = selectors.case_id

    candidates: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    by_field: dict[str, dict[str, int]] = {}
    silver_alignment: list[dict[str, Any]] = []
    invariants: list[dict[str, Any]] = []
    review_packets: list[dict[str, Any]] = []
    selected_fields: set[str] = set()
    selected_routes: set[str] = set()
    selected_form_types: set[str] = set()
    selected_ciks: set[str] = set()
    selected_filing_years: set[str] = set()

    total_cases = 0

    normalized_cases = [case_raw for case_raw in cases_raw if isinstance(case_raw, Mapping)]
    normalized_cases.sort(key=lambda case: str(case.get("case_id", "")))

    for case_raw in normalized_cases:
        case_id = str(case_raw.get("case_id", ""))
        route = str(case_raw.get("route", "")).strip()
        form_type = str(case_raw.get("form_type", "")).strip()
        form_family = classify_form_family(form_type)

        if not case_id or not route or not form_type:
            continue

        if selected_case_id and case_id != selected_case_id:
            continue
        if selected_route and route != selected_route:
            continue
        if selected_form_family and form_family != selected_form_family:
            continue

        fixture_file = str(case_raw.get("fixture_file", "")).strip()
        fixture_exists = False
        fixture_text = ""
        if fixture_file:
            fixture_path = _resolve_fixture_path(fixtures_dir=fixtures_dir, fixture_file=fixture_file)
            fixture_exists = fixture_path.exists()
            if fixture_exists:
                fixture_text = fixture_path.read_text(encoding="utf-8")

        filing = _OfflineFixtureFiling(
            parse_text=fixture_text,
            section_payload=case_raw.get("sections"),
        )

        expected_raw = case_raw.get("expected", {})
        if not isinstance(expected_raw, Mapping):
            continue

        total_cases += 1
        selected_routes.add(route)
        selected_form_types.add(form_type)
        cik = str(case_raw.get("cik", "")).strip()
        if cik:
            selected_ciks.add(cik)
        for date_key in ("accepted_at", "filed_at", "period_end"):
            date_value = str(case_raw.get(date_key, "")).strip()
            if len(date_value) >= 4 and date_value[:4].isdigit():
                selected_filing_years.add(date_value[:4])
                break

        for field_name in sorted(str(field_name_raw) for field_name_raw in expected_raw.keys()):
            expected_value_raw = expected_raw[field_name]
            if selected_field and field_name != selected_field:
                continue
            selected_fields.add(field_name)

            expected_value: dict[str, Any] = (
                dict(expected_value_raw)
                if isinstance(expected_value_raw, Mapping)
                else {"status": "ok", "value_text": str(expected_value_raw)}
            )
            truth_tier = str(expected_value.get("truth_tier", "gold")).strip().lower() or "gold"

            candidate: dict[str, Any] = {
                "case_id": case_id,
                "route": route,
                "form_type": form_type,
                "form_family": form_family,
                "field_name": field_name,
                "truth_tier": truth_tier,
            }

            if not expected_value.get("is_applicable", True):
                candidate.update({"status": "not_applicable", "matched": True})
                candidates.append(candidate)
                _update_by_field(by_field=by_field, field_name=field_name, matched=True, status="not_applicable")
                continue

            spec = spec_map.get((route, field_name))
            if spec is None or form_family not in spec.form_families:
                candidate.update({"status": "error", "error_code": "SPEC_NOT_FOUND"})
                expected_status = str(expected_value.get("status", "ok"))
                expected_error = str(expected_value.get("error_code", ""))
                matched = expected_status == "error" and expected_error == "SPEC_NOT_FOUND"
            elif not fixture_exists:
                candidate.update({"status": "error", "error_code": "FIXTURE_NOT_FOUND"})
                expected_status = str(expected_value.get("status", "ok"))
                expected_error = str(expected_value.get("error_code", ""))
                matched = expected_status == "error" and expected_error == "FIXTURE_NOT_FOUND"
            else:
                outcome = engine.extract_field(filing=filing, field_spec=spec)
                if outcome["status"] == "ok":
                    candidate.update(
                        {
                            "status": "ok",
                            "value_text": outcome["value_text"],
                            "value_json": outcome["value_json"],
                            "locator_kind": outcome["locator_kind"],
                            "locator_path": outcome["locator_path"],
                            "source_span": outcome["source_span"],
                        }
                    )
                else:
                    candidate.update(
                        {
                            "status": "error",
                            "error_code": outcome["error_code"],
                        }
                    )

                expected_status = str(expected_value.get("status", "ok"))
                if expected_status == "ok":
                    matched = _matches_expected_ok_value(expected_value=expected_value, candidate=candidate)
                elif expected_status == "error":
                    expected_error = str(expected_value.get("error_code", "")).strip()
                    matched = candidate["status"] == "error" and str(candidate.get("error_code", "")) == expected_error
                else:
                    raise ValueError(f"Unsupported expected status: {expected_status}")

            candidate["matched"] = matched
            candidates.append(candidate)

            _update_by_field(
                by_field=by_field,
                field_name=field_name,
                matched=matched,
                status=str(candidate.get("status", "error")),
            )

            if truth_tier == "silver":
                silver_alignment.append(
                    {
                        "case_id": case_id,
                        "field_name": field_name,
                        "matched": matched,
                        "candidate": candidate,
                    }
                )

            if not matched:
                failure = {
                    "case_id": case_id,
                    "field_name": field_name,
                    "expected": expected_value,
                    "actual": candidate,
                }
                failures.append(failure)
                if truth_tier == "gold":
                    review_packets.append(
                        {
                            "case_id": case_id,
                            "subject_key": _subject_key_for_candidate(candidate),
                            "field_name": field_name,
                            "expected": expected_value,
                            "actual": candidate,
                        }
                    )

    invariant_rows = golden_set.get("invariants", [])
    if isinstance(invariant_rows, list):
        for invariant in invariant_rows:
            if not isinstance(invariant, Mapping):
                continue
            status = str(invariant.get("status", "pass"))
            invariants.append(dict(invariant))
            if status not in {"pass", "fail"}:
                continue

    total_candidates = len(candidates)
    total_failures = len(failures)
    total_passed = total_candidates - total_failures
    pass_rate = (total_passed / total_candidates) if total_candidates else 0.0

    regressions: list[str] = []
    baseline_summary_path = baseline_path
    if baseline_summary_path is not None:
        baseline_summary = _load_baseline(baseline_summary_path)
        baseline_by_field_raw = baseline_summary.get("by_field", {})
        if isinstance(baseline_by_field_raw, Mapping):
            for field_name in sorted(by_field.keys()):
                current_stats = by_field[field_name]
                baseline_stats = baseline_by_field_raw.get(field_name)
                if not isinstance(baseline_stats, Mapping):
                    continue
                if _matched_rate(current_stats) + 1e-12 < _matched_rate(baseline_stats):
                    regressions.append(field_name)

    gold_candidates = [candidate for candidate in candidates if candidate.get("truth_tier") == "gold"]
    gold_applicable = [candidate for candidate in gold_candidates if candidate.get("status") != "not_applicable"]
    gold_matched = [candidate for candidate in gold_applicable if candidate.get("matched") is True]
    gold_ok = [candidate for candidate in gold_applicable if candidate.get("status") == "ok"]
    silver_candidates = [candidate for candidate in candidates if candidate.get("truth_tier") == "silver"]
    silver_applicable = [candidate for candidate in silver_candidates if candidate.get("status") != "not_applicable"]
    silver_matched = [candidate for candidate in silver_applicable if candidate.get("matched") is True]
    invariant_pass_fail = [invariant for invariant in invariants if str(invariant.get("status")) in {"pass", "fail"}]
    invariant_passed = [invariant for invariant in invariant_pass_fail if str(invariant.get("status")) == "pass"]

    gold_total = len(gold_applicable)
    silver_total = len(silver_applicable)
    invariant_total = len(invariant_pass_fail)

    coverage = {
        "total_cases": total_cases,
        "total_candidates": total_candidates,
        "gold_applicable_rows": gold_total,
        "silver_applicable_rows": silver_total,
        "invariant_rows": invariant_total,
        "distinct_ciks": len(selected_ciks),
        "distinct_filing_years": len(selected_filing_years),
    }
    metrics = {
        "passed": total_passed,
        "failed": total_failures,
        "pass_rate": pass_rate,
        "min_pass_rate": min_pass_rate,
        "passes_threshold": pass_rate >= min_pass_rate,
        "regressions": regressions,
        "gold_strict_accuracy": (len(gold_matched) / gold_total) if gold_total else 0.0,
        "gold_coverage": (len(gold_ok) / gold_total) if gold_total else 0.0,
        "row_selection_accuracy": (len(gold_matched) / gold_total) if gold_total else 0.0,
        "not_applicable_precision": 1.0,
        "silver_alignment": (len(silver_matched) / silver_total) if silver_total else 0.0,
        "invariant_pass_rate": (len(invariant_passed) / invariant_total) if invariant_total else 0.0,
    }
    phase_gates = evaluate_phase_gates(
        gates_raw=golden_set.get("phase_gates", []),
        coverage=coverage,
        metrics=metrics,
        set_values={
            "required_fields": selected_fields,
            "required_routes": selected_routes,
            "required_form_types": selected_form_types,
            "required_ciks": selected_ciks,
            "required_filing_years": selected_filing_years,
        },
        selector_context={
            "route": selectors.route,
            "form_family": selectors.form_family,
            "field_name": selectors.field_name,
            "case_id": selectors.case_id,
        },
    )
    failed_phase_gates = [gate for gate in phase_gates if gate.get("status") == "failed"]

    summary = build_strict_v2_summary(
        run_id=run_id_value,
        selectors={
            "route": selectors.route,
            "form_family": selectors.form_family,
            "field_name": selectors.field_name,
            "case_id": selectors.case_id,
        },
        coverage=coverage,
        metrics=metrics,
        phase_gates=phase_gates,
    )

    write_run_artifacts(
        base_dir=artifacts_dir,
        run_id=run_id_value,
        summary=summary,
        by_field=by_field,
        failures=failures,
        candidates=candidates,
        diff_markdown=_build_diff_markdown(failures, regressions),
        manifest=_build_manifest(
            run_id=run_id_value,
            regex_config_path=regex_config_path,
            golden_set_path=golden_set_path,
            fixtures_dir=fixtures_dir,
            selectors=selectors,
            baseline_path=baseline_path,
        ),
        coverage=summary["coverage"],
        silver_alignment=silver_alignment,
        invariants=invariants,
        review_packets=review_packets,
        phase_gates=phase_gates,
    )

    if regressions:
        raise ValueError(f"baseline regression detected for fields: {', '.join(regressions)}")
    if pass_rate < min_pass_rate:
        raise ValueError(f"pass_rate {pass_rate:.4f} below threshold {min_pass_rate:.4f}")
    if failed_phase_gates:
        gate_names = ", ".join(str(gate.get("name")) for gate in failed_phase_gates)
        raise ValueError(f"phase gate failure: {gate_names}")

    return OfflineEvalResult(run_id=run_id_value, summary=summary)
