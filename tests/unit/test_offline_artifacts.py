import json
from pathlib import Path

from src.pipeline.offline_artifacts import write_run_artifacts


def test_write_run_artifacts_creates_summary_samples_and_diff(tmp_path: Path) -> None:
    write_run_artifacts(
        base_dir=tmp_path,
        run_id="run-001",
        summary={"coverage": {"issuer": 1.0}},
        samples=[{"field_name": "total_revenue", "status": "ok"}],
        diff_markdown="# Diff\n- none",
    )

    run_dir = tmp_path / "run-001"
    assert (run_dir / "summary.json").exists()
    assert (run_dir / "samples.ndjson").exists()
    assert (run_dir / "diff.md").exists()

    summary_payload = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary_payload == {"coverage": {"issuer": 1.0}}

    samples_lines = (run_dir / "samples.ndjson").read_text(encoding="utf-8").strip().splitlines()
    assert len(samples_lines) == 1
    assert json.loads(samples_lines[0]) == {"field_name": "total_revenue", "status": "ok"}

    assert (run_dir / "diff.md").read_text(encoding="utf-8") == "# Diff\n- none"
