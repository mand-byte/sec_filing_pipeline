from __future__ import annotations

from pathlib import Path
import sys

import typer

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline.offline_evaluator import OfflineEvalSelectors, run_offline_tier2_evaluation

app = typer.Typer(help="Offline Tier2 evaluator")


@app.command("run")
def run(
    regex_config: Path = typer.Option(
        Path("configs/tier2/regex/default.yaml"),
        "--regex-config",
        help="Path to Tier2 regex config yaml",
    ),
    golden_set: Path = typer.Option(
        Path("configs/tier2/golden_set/default.yaml"),
        "--golden-set",
        help="Path to Tier2 golden set yaml",
    ),
    fixtures_dir: Path = typer.Option(
        Path("configs/tier2/fixtures"),
        "--fixtures-dir",
        help="Directory that stores local fixture snapshots",
    ),
    artifacts_dir: Path = typer.Option(
        Path("artifacts/offline"),
        "--artifacts-dir",
        help="Directory for offline evaluator artifacts",
    ),
    route: str | None = typer.Option(None, "--route", help="Optional route filter"),
    form_family: str | None = typer.Option(None, "--form-family", help="Optional form family filter"),
    field_name: str | None = typer.Option(None, "--field", help="Optional field filter"),
    case_id: str | None = typer.Option(None, "--case-id", help="Optional case id filter"),
    baseline: Path | None = typer.Option(None, "--baseline", help="Optional baseline summary json"),
    min_pass_rate: float = typer.Option(0.95, "--min-pass-rate", help="Minimum pass rate threshold"),
) -> None:
    selectors = OfflineEvalSelectors(
        route=route,
        form_family=form_family,
        field_name=field_name,
        case_id=case_id,
    )

    result = run_offline_tier2_evaluation(
        regex_config_path=regex_config,
        golden_set_path=golden_set,
        fixtures_dir=fixtures_dir,
        artifacts_dir=artifacts_dir,
        selectors=selectors,
        baseline_path=baseline,
        min_pass_rate=min_pass_rate,
    )

    typer.echo(f"run_id={result.run_id}")
    typer.echo(f"passed={result.summary['metrics']['passed']}")
    typer.echo(f"failed={result.summary['metrics']['failed']}")


if __name__ == "__main__":
    app()
