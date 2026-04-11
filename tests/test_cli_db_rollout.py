from __future__ import annotations

import json

from typer.testing import CliRunner

import src.cli as cli_module


runner = CliRunner()


def test_cli_db_rollout_assets_lists_checked_in_sql_and_readme() -> None:
    result = runner.invoke(cli_module.app, ["db-rollout-assets"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["readme_path"].endswith("src/db/migrations/README.md")
    assert payload["migrations"] == [
        {
            "name": "20260411_add_evidence_locator_and_filing_attempt.sql",
            "path": payload["migrations"][0]["path"],
        }
    ]
    assert payload["migrations"][0]["path"].endswith(
        "src/db/migrations/20260411_add_evidence_locator_and_filing_attempt.sql"
    )
