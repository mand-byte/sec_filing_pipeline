# DB Migrations

This directory contains checked-in schema rollout assets for runtime changes that
cannot rely on `Base.metadata.create_all(...)` in existing databases.

Current required rollout:

- `20260418_drop_legacy_generic_result_tables.sql`
  - drops `review_task.primary_evidence_id`
  - drops legacy tables `extraction_evidence` and `extracted_fact`

Apply the SQL before deploying the corresponding application code to an existing
PostgreSQL database.

Operational notes:

- The checked-in SQL uses `IF EXISTS` guards so re-applying the same rollout
  is safe on existing databases.
- Apply the SQL in filename order from this directory.
- Rollback is manual: restore or recreate the removed legacy objects only if an
  older application version still depends on them.
