from __future__ import annotations

from pathlib import Path


def test_schema_rollout_sql_exists_for_new_runtime_tables_and_columns() -> None:
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "db"
        / "migrations"
        / "20260411_add_evidence_locator_and_filing_attempt.sql"
    )

    payload = migration_path.read_text(encoding="utf-8")

    assert "ALTER TABLE extraction_evidence" in payload
    assert "ADD COLUMN IF NOT EXISTS source_locator_json TEXT" in payload
    assert "CREATE TABLE IF NOT EXISTS filing_attempt" in payload
