from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_run_artifacts(
    *,
    base_dir: Path,
    run_id: str,
    summary: dict[str, Any],
    samples: list[dict[str, Any]],
    diff_markdown: str,
) -> None:
    run_dir = base_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with (run_dir / "samples.ndjson").open("w", encoding="utf-8") as output:
        for sample in samples:
            output.write(json.dumps(sample, ensure_ascii=False) + "\n")

    (run_dir / "diff.md").write_text(diff_markdown, encoding="utf-8")
