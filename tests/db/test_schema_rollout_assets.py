from __future__ import annotations

from pathlib import Path


def test_schema_rollout_sql_exists_for_legacy_generic_table_removal() -> None:
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "db"
        / "migrations"
        / "20260418_drop_legacy_generic_result_tables.sql"
    )

    payload = migration_path.read_text(encoding="utf-8")

    assert "ALTER TABLE review_task" in payload
    assert "DROP COLUMN IF EXISTS primary_evidence_id" in payload
    assert "DROP TABLE IF EXISTS extraction_evidence" in payload
    assert "DROP TABLE IF EXISTS extracted_fact" in payload
