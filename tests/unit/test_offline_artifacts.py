import json
from pathlib import Path

from src.pipeline.offline_artifacts import write_run_artifacts


def test_write_run_artifacts_creates_summary_samples_and_diff(tmp_path: Path) -> None:
    write_run_artifacts(
        base_dir=tmp_path,
        run_id="run-001",
        summary={"coverage": {"issuer": 1.0}},
        by_field={"total_revenue": {"ok": 1, "error": 0}},
        failures=[{"field_name": "diluted_eps", "error_code": "WINDOW_NOT_FOUND"}],
        candidates=[{"field_name": "total_revenue", "status": "ok"}],
        diff_markdown="# Diff\n- none",
    )

    run_dir = tmp_path / "run-001"
    assert (run_dir / "summary.json").exists()
    assert (run_dir / "by_field.json").exists()
    assert (run_dir / "failures.ndjson").exists()
    assert (run_dir / "candidates.ndjson").exists()
    assert (run_dir / "diff.md").exists()

    summary_payload = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary_payload == {"coverage": {"issuer": 1.0}}

    by_field_payload = json.loads((run_dir / "by_field.json").read_text(encoding="utf-8"))
    assert by_field_payload == {"total_revenue": {"ok": 1, "error": 0}}

    failures_lines = (run_dir / "failures.ndjson").read_text(encoding="utf-8").strip().splitlines()
    assert len(failures_lines) == 1
    assert json.loads(failures_lines[0]) == {"field_name": "diluted_eps", "error_code": "WINDOW_NOT_FOUND"}

    candidates_lines = (run_dir / "candidates.ndjson").read_text(encoding="utf-8").strip().splitlines()
    assert len(candidates_lines) == 1
    assert json.loads(candidates_lines[0]) == {"field_name": "total_revenue", "status": "ok"}

    assert (run_dir / "diff.md").read_text(encoding="utf-8") == "# Diff\n- none"
