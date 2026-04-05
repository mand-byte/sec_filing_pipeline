# Roadmap: SEC Filing Precision-First Backend

## Overview

This roadmap delivers a precision-first SEC filing backend in five requirement-driven phases: compliant ingestion foundation, lifecycle completeness (incremental/amendment/replay), deterministic extraction for the v1 form set, strict QA plus lineage guarantees, and operational review/diagnostics loops. The sequence is designed so each phase ends with observable operator outcomes while preserving PostgreSQL as source of truth and stateless worker execution.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Compliant Ingestion Foundation** - Establish universe-scoped, deduplicated, SEC-compliant cold-start intake.
- [ ] **Phase 2: Incremental, Amendment, and Backfill Lifecycle** - Complete stateful ingestion controls for new filings, /A updates, and replay scopes.
- [ ] **Phase 3: Deterministic v1 Form Extraction Coverage** - Deliver deterministic extraction for 10-K/10-Q, 8-K, Form 4, and 13F.
- [ ] **Phase 4: Canonical QA and Lineage Guarantees** - Enforce strict acceptance gates with canonical accepted/unresolved outputs and deterministic replayability.
- [ ] **Phase 5: Review Queue and Operational Diagnostics** - Operationalize failure handling, diffable replay audits, and backlog/failure analytics.

## Phase Details

### Phase 1: Compliant Ingestion Foundation
**Goal**: Operators can run a cold-start ingestion that only ingests eligible universe filings, deduplicates accessions, and complies with SEC access policies.
**Depends on**: Nothing (first phase)
**Requirements**: ING-01, ING-05, ING-06, OPS-03
**Success Criteria** (what must be TRUE):
  1. Operator can run cold-start ingestion for configured universe and selected v1 form families.
  2. Discovered filings are filtered by `data_quant.us_stock_universe`, including inactive-security delisting cutoff behavior.
  3. Repeated discovery of the same accession does not create duplicate filing records before extraction.
  4. SEC access controls (descriptive User-Agent, global request shaping, retry/backoff) are enforced during ingestion runs.
**Plans**: TBD

### Phase 2: Incremental, Amendment, and Backfill Lifecycle
**Goal**: Operators can maintain filing freshness and historical correctness through incremental ingestion, amendment linkage, and idempotent replay/backfill controls.
**Depends on**: Phase 1
**Requirements**: ING-02, ING-03, ING-04
**Success Criteria** (what must be TRUE):
  1. Operator can run incremental ingestion using persisted watermark cursors and fetch only newly available filings.
  2. Amendment filings (`/A`) are identified and linked with explicit supersession relationships.
  3. Operator can replay/backfill by accession, date range, or form family without creating duplicate canonical outputs.
**Plans**: TBD

### Phase 3: Deterministic v1 Form Extraction Coverage
**Goal**: The system deterministically extracts required v1 data for each in-scope form family from structured sources.
**Depends on**: Phase 2
**Requirements**: EXT-01, EXT-02, EXT-03, EXT-04
**Success Criteria** (what must be TRUE):
  1. 10-K/10-Q required v1 numeric fields are extracted through deterministic structured/XBRL-first paths.
  2. 8-K item/event fields are extracted, including Item 5.07 vote blocks when present, with unresolved output when unavailable.
  3. Form 4 ownership holdings and transactions are extracted from deterministic ownership XML/object paths.
  4. 13F position-level rows and document totals are extracted while preserving row integrity.
**Plans**: TBD

### Phase 4: Canonical QA and Lineage Guarantees
**Goal**: Every required v1 field is emitted as canonical accepted/unresolved output under strict QA gates, with complete lineage and deterministic reproducibility.
**Depends on**: Phase 3
**Requirements**: EXT-05, QLT-01, QLT-03, QLT-04, QLT-05
**Success Criteria** (what must be TRUE):
  1. Every required v1 field is stored with explicit `accepted` or `unresolved(reason)` status.
  2. Only extraction candidates that pass schema, normalization, range/logic, cross-check, and completeness gates are auto-accepted.
  3. Each accepted/rejected field stores full lineage (locator, raw/normalized values, evidence pointer, extractor/registry versions, decision source).
  4. Deterministic extractors are authoritative; unsupported or ambiguous values fail closed to unresolved/review.
  5. Re-running the same filing with the same versions produces identical extraction results.
**Plans**: TBD

### Phase 5: Review Queue and Operational Diagnostics
**Goal**: Operators can triage unresolved/failed extractions, audit replay changes, and inspect operational failure trends directly from persisted PostgreSQL state.
**Depends on**: Phase 4
**Requirements**: QLT-02, OPS-01, OPS-02, OPS-04
**Success Criteria** (what must be TRUE):
  1. Candidates that fail QA or are ambiguous are routed to a review queue with explicit failure reason codes.
  2. Parsing and extraction outcomes (success/failure + categorized failure reasons) are persisted and queryable in PostgreSQL.
  3. Replay jobs produce before/after diffs for changed values and preserve audit history.
  4. Operator can query failure-reason distributions and review-queue backlog from operational data.
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Compliant Ingestion Foundation | 0/TBD | Not started | - |
| 2. Incremental, Amendment, and Backfill Lifecycle | 0/TBD | Not started | - |
| 3. Deterministic v1 Form Extraction Coverage | 0/TBD | Not started | - |
| 4. Canonical QA and Lineage Guarantees | 0/TBD | Not started | - |
| 5. Review Queue and Operational Diagnostics | 0/TBD | Not started | - |
