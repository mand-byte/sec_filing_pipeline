# DEMANDS Closure Status

This file separates code-delivered closure from still-external operating decisions so release claims stay evidence-based.

## Code-delivered surfaces

### Deterministic core
- DB rollout asset introspection and apply flow
- base schema bootstrap via `db-init`
- DB-backed `filing_attempt`, `pipeline_log`, `route_watermark`, and error-detail persistence
- route runtime failure isolation, delisted gating, and scheduler/run-once artifacts

### Strict-v2 evaluation
- shared strict-v2 phase-gate + summary helpers
- numeric-batch strict-v2 artifacts
- default text strict-v2 vertical slice for all 15 runtime text fields
- release-gate support for repeatable `--strict-summary` inputs

### Provider-backed bounded text understanding
- schema-backed `value_json` for all 15 runtime text fields
- explicit `NORMALIZATION_UNAVAILABLE`, `NORMALIZATION_FAILED`, and `NORMALIZATION_TIMEOUT`
- bounded-span provider input
- provider adequacy-signal persistence
- one-step expand retry on insufficient context
- provider uncertainty escalation into review when confidence/context signals are weak

### Review / fix-once / release linkage
- review decisions create `GoldenTruth` / `GoldenReviewPacket`
- release-gate blocks on open review tasks, missing packets, failed strict summaries, failed runtime-run verification, and failed cohort-manifest runtime verification
- downstream truth precedence probe via `truth-select`

### Historical backfill / runtime verification
- `backfill` CLI with route/ticker/cik/limit filters
- config-driven `backfill-cohort` CLI for phase seed cohorts
- cohort manifest artifacts that bind a named seed cohort to per-route runtime run ids
- `runtime-preflight` CLI for environment readiness
- watermark replay mode for historical recovery
- `verify-runtime-run` CLI for artifact-vs-DB verification
- `BACKFILL_RUNBOOK.md` for backfill/incremental/recovery flow

## Current verification evidence
- `./.venv/bin/pytest -q`
- `./.venv/bin/python -m compileall -q src tests`
- `./.venv/bin/python main.py strict-v2-eval --artifacts-dir artifacts/golden`

## Still external / not code-complete by itself
These items require real environment execution or operator decisions, not just more repository code:

- provider choice / production budget
- production DB topology
- representative large-scale historical backfill execution window and capacity
- real production/semi-production backfill evidence across the intended issuer cohorts
- real scheduler evidence after backfill on the target environment

## Release-claim rule
Do not claim full `DEMANDS.md` production completion until the external run evidence above exists in addition to the code and test surfaces already closed.
