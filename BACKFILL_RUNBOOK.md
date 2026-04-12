# Historical Backfill and Daily Incremental Runbook

## Goal
- run seed or recovery backfills without losing the current incremental watermark contract
- prove that daily incremental runs still skip filings that are already behind the stored watermark

## Historical backfill
Use `backfill` when you need to replay older filings for a route, seed cohort, or recovery window.

### Examples
```bash
./.venv/bin/python main.py backfill --route issuer --start-date 2014-01-01
./.venv/bin/python main.py backfill --route owner --ticker MSFT --ticker AAPL --start-date 2020-01-01
./.venv/bin/python main.py backfill --route holding --cik 0000789019 --limit 1
./.venv/bin/python main.py backfill-cohort --cohort phase1_deterministic --start-date 2014-01-01
./.venv/bin/python main.py backfill-cohort --cohort phase2_financial --route issuer --start-date 2014-01-01
```

### Watermark modes
- default: `--ignore-existing-watermarks`
  - replays historical filings even when the DB watermark is newer
  - use for cold-start backfills and targeted recovery
- optional: `--respect-watermarks`
  - keeps normal incremental semantics while still allowing route / ticker / CIK scoping

## Evidence artifacts
Every runtime run writes an artifact directory under `artifacts/<run_id>/` when `WRITE_OFFLINE_ARTIFACTS=1`.

Key files:
- `manifest.json`
  - mode (`run_once` or `backfill`)
  - selected routes
  - start date
  - watermark mode
  - applied ticker / CIK filters
  - selected security count
- `cohorts/<cohort_name>__<run_id>.json`
  - maps a named backfill cohort run to its per-route runtime run IDs
- `summary.json`
  - route coverage
  - filing-attempt totals and by-status counts
  - error distribution
- `candidates.ndjson` / `failures.ndjson`
  - per-log replay trail for the run

## Recovery workflow
1. Identify the affected route and seed cohort.
2. Run `backfill` with `--ignore-existing-watermarks`.
3. Inspect `manifest.json` and `summary.json`.
4. Confirm DB state:
   - `filing_attempt`
   - `pipeline_log`
   - `route_watermark`
   - or run:
     ```bash
     ./.venv/bin/python main.py verify-runtime-run --run-id <run_id>
     ```
5. Run the normal incremental entrypoint:
   ```bash
   ./.venv/bin/python main.py run-once --route <route>
   ```
6. Verify that the incremental run reports `skipped_before_watermark > 0` for already-covered historical filings.

## Daily incremental operation
After backfill, continue with the normal scheduler:
```bash
./.venv/bin/python main.py schedule --route issuer
./.venv/bin/python main.py schedule --route owner
./.venv/bin/python main.py schedule --route holding
```

Expected contract:
- no single filing failure blocks the rest of the route
- `error_detail` is persisted for failed attempts
- successful filings advance the watermark forward only
- reruns do not duplicate fact rows because persistence is accession/route/field/subject keyed

## Downstream truth precedence
For factor consumption and other downstream reads, prefer:
- manual review ground truth
- then parsed extracted fact

Probe the effective value with:
```bash
./.venv/bin/python main.py truth-select \
  --accession-no <accession_no> \
  --route <issuer|owner|holding> \
  --field <field_name> \
  --subject-key <subject_key>
```

Expected contract:
- when a `manual_review` `GoldenTruth` exists for the same accession/field/subject, it wins
- otherwise the parsed `ExtractedFact` wins
