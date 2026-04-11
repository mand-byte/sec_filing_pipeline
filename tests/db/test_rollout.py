from __future__ import annotations

from src.db.rollout import describe_rollout_assets, migration_asset_paths, migration_readme_path


def test_rollout_assets_include_checked_in_migration_and_readme() -> None:
    payload = describe_rollout_assets()

    assert migration_readme_path().name == "README.md"
    assert any(path.name == "20260411_add_evidence_locator_and_filing_attempt.sql" for path in migration_asset_paths())
    assert payload["readme_path"].endswith("src/db/migrations/README.md")
    assert "safe on existing databases" in payload["instructions"]
    assert payload["migrations"] == [
        {
            "name": "20260411_add_evidence_locator_and_filing_attempt.sql",
            "path": str(migration_asset_paths()[0]),
        }
    ]
