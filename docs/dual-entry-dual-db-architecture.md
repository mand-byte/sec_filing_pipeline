# Dual Entry / Dual DB Architecture

## Goal

Split the pipeline into:

1. **Production flow**
   - writes final specialized result tables
   - does **not** depend on run-scoped history tables
   - uses `PG_DSN`

2. **Audit flow**
   - keeps run-scoped tracking (`run_id`, logs, attempts, artifacts)
   - can be used for sampled replay / regression / verification
   - uses `AUDIT_PG_DSN` (falls back to `PG_DSN` if unset)

## Entrypoints

### Production commands
- `prod-db-init`
- `prod-runtime-preflight`
- `prod-run-once`
- `prod-backfill`
- `prod-schedule`

### Audit commands
- `db-init` / `audit-db-init`
- `runtime-preflight` / `audit-runtime-preflight`
- `run-once` / `audit-run-once`
- `backfill` / `audit-backfill`
- `schedule` / `audit-schedule`

Compatibility note:
- Existing unprefixed commands remain the **audit** flow to preserve current CLI behavior.
- New `prod-*` commands expose the normal no-run-history flow.

## Database roles

### Production DB
Schema scope: `prod`

Key tables:
- `filing_document`
- `filing_status`
- `route_watermark`
- `delisted_route_completion`
- specialized result tables (`issuer_*`, `owner_*`, `holding_*`)
- review / truth tables needed for final-value consumption

### Audit DB
Schema scope: `audit`

Contains the full schema, including:
- run-scoped history tables (`pipeline_log`, `filing_attempt`)
- eval / review packet history
- specialized result tables (for isolated replay / audit runs)

## State model

### Production flow state
- current filing state lives in `filing_status`
- unique by `(route, accession_no)`
- supports resume / stale-in-progress cleanup without `run_id`

### Audit flow state
- run-scoped history lives in `filing_attempt` and `pipeline_log`
- unique by `(run_id, route, accession_no)`
- suitable for artifacts, replay, and run-by-run audit analysis

## Rationale

This split keeps:
- production querying simple and run-id free
- audit history rich and isolated
- long backfills resumable without mixing current-value tables with execution history
