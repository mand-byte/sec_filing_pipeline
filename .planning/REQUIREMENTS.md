# Requirements: SEC Filing Precision-First Backend

**Defined:** 2026-04-05
**Core Value:** Quant-critical filing data is extracted with verifiable correctness, auditable lineage, and minimal manual intervention.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Ingestion Lifecycle

- [ ] **ING-01**: Operator can run cold-start ingestion for configured universe and selected form families.
- [ ] **ING-02**: Operator can run incremental ingestion using persisted watermark cursors to fetch only new filings.
- [ ] **ING-03**: System can identify and process `/A` amendment filings with explicit supersession linkage.
- [ ] **ING-04**: Operator can replay/backfill by accession, date range, or form family without creating duplicate canonical outputs.
- [ ] **ING-05**: System enforces universe filters from `data_quant.us_stock_universe`, including inactive security delisting cutoff behavior.
- [ ] **ING-06**: System deduplicates discovered filings by accession identity before extraction.

### Extraction Coverage

- [ ] **EXT-01**: System extracts v1 canonical numeric fields from 10-K/10-Q using deterministic structured/XBRL-first paths.
- [ ] **EXT-02**: System extracts 8-K item/event fields (including Item 5.07 vote blocks when present) with explicit unresolved status when unavailable.
- [ ] **EXT-03**: System extracts Form 4 ownership transactions and holdings from deterministic ownership XML/object paths.
- [ ] **EXT-04**: System extracts 13F position-level rows and document totals while preserving row integrity.
- [ ] **EXT-05**: System writes normalized canonical outputs with explicit `accepted` or `unresolved(reason)` status for each required v1 field.

### Quality and Governance

- [ ] **QLT-01**: Every extracted candidate passes strict QA gates (schema, normalization, range/logic, cross-check, completeness) before auto-accept.
- [ ] **QLT-02**: Any candidate that fails QA or is ambiguous is routed to a review queue with explicit failure reason codes.
- [ ] **QLT-03**: Every accepted/rejected field stores full lineage (locator, raw value, normalized value, evidence pointer, extractor/registry versions, decision source).
- [ ] **QLT-04**: Deterministic extractors are authoritative over non-deterministic methods; unsupported values fail closed to review/unresolved.
- [ ] **QLT-05**: Re-running the same filing with the same versions produces identical extraction results.

### Operations and Compliance

- [ ] **OPS-01**: Parsing and extraction logs are persisted in PostgreSQL with success/failure outcomes and categorized failure reasons.
- [ ] **OPS-02**: Replay jobs produce before/after diffs for changed values and preserve audit history.
- [ ] **OPS-03**: SEC access compliance is enforced via descriptive User-Agent, global request shaping, and retry backoff policy.
- [ ] **OPS-04**: Operator can query failure-reason distribution and review queue backlog from persisted operational data.

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Capability Expansion

- **V2-01**: LLM span normalization for selected narrative snippet fields (only after deterministic span localization).
- **V2-02**: Expanded form coverage beyond v1 (e.g., 13D/13G, DEF 14A, Form 144, selected S-1/424B paths).
- **V2-03**: Metrics dashboards and alerting suite (freshness, queue age, QA failure spikes, compliance anomalies).
- **V2-04**: Advanced review optimization (confidence calibration and automated triage prioritization).

## Out of Scope

| Feature | Reason |
|---------|--------|
| Full SEC form-family coverage in v1 | High correctness risk and delivery risk; v1 is high-value-first by design |
| LLM full-document value discovery | Conflicts with precision-first and replayability constraints |
| spaCy-first NLP extraction layer | Current core problem is structural deterministic extraction, not general NER |
| Sub-minute real-time ingestion SLA | v1 prioritizes correctness and auditability over ultra-low latency |
| ClickHouse as operational source of truth | Postgres selected as single source of truth for deterministic workflow state |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| ING-01 | Phase 1 | Pending |
| ING-02 | Phase 2 | Pending |
| ING-03 | Phase 2 | Pending |
| ING-04 | Phase 2 | Pending |
| ING-05 | Phase 1 | Pending |
| ING-06 | Phase 1 | Pending |
| EXT-01 | Phase 3 | Pending |
| EXT-02 | Phase 3 | Pending |
| EXT-03 | Phase 3 | Pending |
| EXT-04 | Phase 3 | Pending |
| EXT-05 | Phase 4 | Pending |
| QLT-01 | Phase 4 | Pending |
| QLT-02 | Phase 5 | Pending |
| QLT-03 | Phase 4 | Pending |
| QLT-04 | Phase 4 | Pending |
| QLT-05 | Phase 4 | Pending |
| OPS-01 | Phase 5 | Pending |
| OPS-02 | Phase 5 | Pending |
| OPS-03 | Phase 1 | Pending |
| OPS-04 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 20 total
- Mapped to phases: 20
- Unmapped: 0

---
*Requirements defined: 2026-04-05*
*Last updated: 2026-04-05 after roadmap mapping*
