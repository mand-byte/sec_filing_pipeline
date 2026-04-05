# Phase 1: Compliant Ingestion Foundation - Context

**Gathered:** 2026-04-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver a cold-start ingestion flow that scans filing candidates, keeps only universe-eligible records, deduplicates by accession before extraction, and enforces SEC-compliant access behavior for ingestion operations.

</domain>

<decisions>
## Implementation Decisions

### Universe filtering and source of truth
- **D-01:** On every manual start and every scheduler trigger, load the full ticker/universe snapshot from ClickHouse table `data_quant.us_stock_universe`.
- **D-02:** Worker/runtime remains stateless; PostgreSQL is the only operational state source.
- **D-03:** For `active=0` securities, keep only filings with acceptance time `<= delisted_utc`.
- **D-04:** Universe gating relies on FIGI/CIK mapping; CUSIP is not used for matching because CUSIP coverage is incomplete.

### 13F handling in Phase 1
- **D-05:** 13F discovery runs as a full scan.
- **D-06:** A 13F filing is persisted only when at least one holding maps to a security in `data_quant.us_stock_universe`; no-hit 13F filings are not inserted.
- **D-07:** 13F target matching follows available FIGI/CIK paths from universe data, not CUSIP-only mapping.

### Deduplication and cursor semantics
- **D-08:** `accession_no` is the global deduplication identity.
- **D-09:** Discovery cursor advances by `acceptance_datetime_utc`; when timestamps are equal, use `accession_no` tie-break ordering.
- **D-10:** Duplicate accession discovery is skipped (no overwrite) and recorded as a dedup hit for auditability.

### SEC access policy
- **D-11:** SEC compliance controls (request shaping/rate behavior/retry-backoff behavior) are delegated to edgartools; no extra outer throttle/retry layer is added in this project.
- **D-12:** Project code must still provide a descriptive configured SEC User-Agent.

### Cold-start run contract
- **D-13:** Use a synchronous scheduler and single-threaded loop across the full universe set (no shard-level parallelism in Phase 1).
- **D-14:** If one CIK fails, continue with the next CIK and finish the run; wait for next scheduler trigger rather than aborting the entire cycle.

### Claude's Discretion
- Failure summary reporting format (counter schema and log payload fields) for end-of-run diagnostics.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and requirements
- `.planning/ROADMAP.md` — Phase 1 goal, requirement mapping, and success criteria.
- `.planning/REQUIREMENTS.md` — Requirement definitions for `ING-01`, `ING-05`, `ING-06`, `OPS-03`.
- `.planning/PROJECT.md` — Project-wide non-negotiables (PostgreSQL source of truth, precision-first constraints).

### Existing ingestion implementation points
- `src/models/filing.py` — `filing_index.accession_no` uniqueness and filing metadata model.
- `src/storage/ingestion_state_repo.py` — current cursor/state advancement semantics.
- `src/storage/sec_submissions_client.py` — SEC submissions retrieval path and User-Agent wiring.
- `src/storage/sec_download_adapter.py` — edgartools-backed filing download adapter.
- `src/core/config.py` — SEC User-Agent and rate-limit configuration inputs.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/storage/sec_submissions_client.py`: wraps SEC submissions fetch through shared `SecClient` with configured User-Agent.
- `src/storage/sec_download_adapter.py`: central adapter for edgartools filing downloads and normalized filing bundle output.
- `src/storage/ingestion_state_repo.py`: reusable persisted watermark update logic with timestamp + accession tie-break semantics.
- `src/models/filing.py`: existing filing metadata tables and unique accession constraint.
- `src/cli.py`: existing operational command entrypoints (`owner-sync`, `replay-accession`) and transaction handling pattern.

### Established Patterns
- Repository/service orchestration with explicit DB session management.
- Runtime dependency/network errors normalized to `RuntimeError` in storage adapters.
- Command-level transaction boundary (`commit` on success, `rollback` on runtime failure).

### Integration Points
- Scheduler/ingestion execution should pass through service layer used by `owner-sync` command.
- Dedup and cursor progression should leverage existing filing model + ingestion state repository.
- SEC access config should remain centralized in `src/core/config.py` and consumed by SEC clients.

</code_context>

<specifics>
## Specific Ideas

- Keep Phase 1 ingestion deterministic via per-trigger full universe load.
- Treat scheduler runs as sync loops; partial failures are tolerated and recovered in later cycles.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-compliant-ingestion-foundation*
*Context gathered: 2026-04-05*
