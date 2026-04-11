# DB Migrations

This directory contains checked-in schema rollout assets for runtime changes that
cannot rely on `Base.metadata.create_all(...)` in existing databases.

Current required rollout:

- `20260411_add_evidence_locator_and_filing_attempt.sql`
  - adds `extraction_evidence.source_locator_json`
  - creates `filing_attempt`

Apply the SQL before deploying the corresponding application code to an existing
PostgreSQL database.
