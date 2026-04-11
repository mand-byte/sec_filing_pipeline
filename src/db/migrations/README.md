# DB Migrations

This directory contains checked-in schema rollout assets for runtime changes that
cannot rely on `Base.metadata.create_all(...)` in existing databases.

Current required rollout:

- `20260411_add_evidence_locator_and_filing_attempt.sql`
  - adds `extraction_evidence.source_locator_json`
  - creates `filing_attempt`

Apply the SQL before deploying the corresponding application code to an existing
PostgreSQL database.

Operational notes:

- The checked-in SQL uses `IF NOT EXISTS` guards so re-applying the same rollout
  is safe on existing databases.
- Apply the SQL in filename order from this directory.
- Rollback is manual: remove or revert the deployed application code first, then
  drop the added columns/table/indexes only after confirming no production data
  depends on them.
