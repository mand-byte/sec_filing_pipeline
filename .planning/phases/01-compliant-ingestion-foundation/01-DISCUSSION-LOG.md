# Phase 1: Compliant Ingestion Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves alternatives considered.

**Date:** 2026-04-05
**Phase:** 01-compliant-ingestion-foundation
**Areas discussed:** Universe filtering, Dedup identity, SEC access policy, Cold-start run contract

---

## Universe filtering

| Option | Description | Selected |
|--------|-------------|----------|
| ClickHouse snapshot at run start | Fixed set per run; deterministic/replayable | ✓ |
| Live lookup per filing | Most current but less deterministic | |
| You decide | Defer to Claude | |

**User's choice:** Trigger-time full load from `data_quant.us_stock_universe` for manual starts and scheduler runs.
**Notes:** App remains stateless, PostgreSQL is sole operational state source; `active=0` uses `<= delisted_utc` cutoff.

---

## 13F handling

| Option | Description | Selected |
|--------|-------------|----------|
| 13F full scan + hit-only persistence | Scan broadly but persist only universe-relevant outcomes | ✓ |
| Persist all 13F filings | Keep all filings regardless of universe hit | |
| You decide | Defer to Claude | |

**User's choice:** Full 13F scan; only persist when holdings hit universe.
**Notes:** FIGI/CIK relationship is usable; CUSIP mapping is incomplete and should not drive gating decisions.

---

## Dedup identity

| Option | Description | Selected |
|--------|-------------|----------|
| `accession_no` global unique | Strong idempotency and replay stability | ✓ |
| `accession_no + cik` | Allows more duplicates in edge cases | |
| Custom | User-defined key | |

**User's choice:** Authorized Claude to choose; finalized as global `accession_no` uniqueness with duplicate-hit skip behavior.
**Notes:** User expectation is low natural duplication via timestamp querying, but accepted DB-level safeguard as zero-cost protection.

---

## SEC access policy

| Option | Description | Selected |
|--------|-------------|----------|
| edgartools manages compliance, no outer layer | Avoid duplicate throttling/retry logic | ✓ |
| Add project-level retry wrapper | Extra control, extra complexity | |
| You decide | Defer to Claude | |

**User's choice:** SEC behavior managed by edgartools itself.
**Notes:** Project still configures descriptive User-Agent; no additional outer throttle/retry policy in Phase 1.

---

## Cold-start run contract

| Option | Description | Selected |
|--------|-------------|----------|
| Sync scheduler + continue on per-CIK failures | Complete cycle robustness and next-trigger recovery | ✓ |
| Stop entire run on first failure | Strict fail-fast | |
| You decide | Defer to Claude | |

**User's choice:** Synchronous scheduler, full-universe for-loop, continue mode.
**Notes:** Final clarification: continue processing and wait for next scheduler trigger.

---

## Claude's Discretion

- Failure summary schema and exact end-of-run diagnostics fields.

## Deferred Ideas

- None.
