# DEMANDS Implementation Audit

This note records the current code-quality/documentation review for the
implemented `DEMANDS.md` tranche. It is intentionally scoped to what is
verified in-repo today, not to unverified live SEC/DB deployment behavior.

## Verified alignment with `DEMANDS.md`

| DEMANDS area | Current implementation evidence | Status |
| --- | --- | --- |
| Unified runtime config and start timestamp | `.env.example`, `configs/runtime/README.md`, and `src/config.py` centralize `PG_DSN`, `CH_DSN`, `SEC_UNIVERSE_TABLE`, `START_DATE`, and scheduler settings while preserving legacy env compatibility. | Implemented |
| Three-route scheduler entrypoints (`issuer`, `owner`, `holding`) | `src/cli.py` exposes `run-once`, `run-route`, `run-issuer`, `run-owner`, and `run-holding`; `src/pipeline/scheduler.py` fixes route order to issuer → owner → holding. | Implemented |
| Stateless incremental progression by accepted-at watermark | `src/pipeline/route_runtime.py` loads route watermarks, filters by `accepted_at`, persists successful bundles, and advances the watermark only after completed persistence. | Implemented |
| Delisted-security eligibility boundary | `src/pipeline/rules.py` enforces `accepted_at <= delisted_utc` for inactive names; `src/pipeline/route_runtime.py` also tracks per-route delisted completion snapshots. | Implemented |
| ClickHouse-backed universe source with safe fallback | `src/pipeline/universe.py` loads `data_quant.us_stock_universe` via `CH_DSN` first, falls back to SQLAlchemy table reads, then to `SecurityMaster`. | Implemented |
| Failure isolation + runtime logging | `src/pipeline/scheduler.py` and `src/pipeline/route_runtime.py` catch per-router/per-filing exceptions, write structured logs, and continue processing the rest of the batch. | Implemented |
| Precision-first extraction/review lineage | `configs/extraction/*.yaml`, `EXTRACTION_METHOD.md`, and `GOLDEN_SET.md` define the registry and truth contract; `source_locator_json` is persisted in `src/pipeline/services.py` / `src/db/models.py`. | Implemented |
| Side-by-side review workflow requirement | `src/pipeline/review/server.py` and `src/pipeline/review/dashboard.py` render evidence/result panels and expose locator JSON for reviewer replay. | Implemented |
| “Fix once” release gate | `src/pipeline/release_gates.py` plus `main.py release-gate` require open review tasks to be resolved and review packets exported before release. | Implemented |
| Deterministic strict-v2 release proof | `configs/tier2/golden_set/default.yaml` currently holds a 15-case seed across issuer/owner/holding routes; `main.py strict-v2-eval` is the executable gate. | Implemented for current tranche |

## Code-quality review notes

- The current tranche is strongest where contracts are explicit: runtime config,
  route processing, review evidence, and release gating each live in separate,
  test-backed modules instead of being intertwined in one CLI path.
- The highest-value documentation drift was in `docs/rollout/phase-gates.md`,
  which still described the older 6-case strict-v2 seed. That gap is corrected
  in this task so the rollout doc matches the checked-in 15-case assets.
- Current release proof is pragmatic but narrow: `pyproject.toml` only configures
  `pytest` in dev dependencies, so the operational quality bar is effectively
  `pytest + build + strict-v2 eval` rather than a dedicated lint/typecheck stage.

## Remaining gaps to keep explicit

- `DEMANDS.md` describes a larger program than the currently verified slice. The
  repo now has the deterministic seed, review/evidence plumbing, and route-level
  invariants, but not a documented proof of full historical backfill or live
  incremental SEC execution against real infrastructure.
- Existing PostgreSQL deployments still need the checked-in migration
  `src/db/migrations/20260411_add_evidence_locator_and_filing_attempt.sql`
  applied before the richer evidence / filing-attempt code is rolled out.
- The review UI contract is present in code, but operator-facing runbook steps
  for launching it in production are still lightweight and may need expansion
  once deployment automation is finalized.
