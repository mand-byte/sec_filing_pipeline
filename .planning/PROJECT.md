# SEC Filing Precision-First Backend

## What This Is

A precision-first SEC filing backend for quantitative data extraction. It ingests filings via edgartools, supports both cold-start and incremental ingestion, and persists operational truth in PostgreSQL while consuming stock universe seeds from ClickHouse. The system is designed to maximize extraction correctness and minimize manual corrections through deterministic extraction first, strict QA gates, and replayable lineage.

## Core Value

Quant-critical filing data is extracted with verifiable correctness, auditable lineage, and minimal manual intervention.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Cold-start + incremental ingestion pipeline using edgartools
- [ ] Precision-first multi-tier extraction with strict QA/review gates
- [ ] Parse/extraction logs persisted for success/failure and failure-reason analysis
- [ ] End-to-end runnable flow for high-value form families (10-K/10-Q, 8-K, Form 4, 13F)
- [ ] Canonical schema and field-level traceability for quantitative consumption

### Out of Scope

- Full one-shot coverage of every form family in v1 — first milestone prioritizes high-value forms to reduce delivery and correctness risk
- spaCy-first NLP extraction strategy — current priority is deterministic structural extraction (obj/XBRL/XML/anchored) over generic NER

## Context

- Download/filing access must use edgartools.
- Upstream stock universe source: ClickHouse `data_quant.us_stock_universe`.
- Universe table constraints from demand:
  - `figi` and `cik` are 1:1
  - Universe already filtered to CS/ADR and excludes multi-ticker-to-single-figi cases (e.g., GOOG/GOOGL style duplicates)
  - For `active=0`, filings with submit time `> delisted_utc` should be ignored
- Precision-first approach in reference docs:
  - Prefer structured sources: `filing.obj()` / `xbrl()` / XML paths
  - Use anchored regex locally (not full-document free regex)
  - LLM only for span normalization, not global value discovery
  - Registry-driven extraction and strict replayable lineage
- User-selected v1 strategy:
  - High-value-first delivery
  - Strict acceptance thresholds
  - PostgreSQL as source of truth
  - v1 must be end-to-end runnable

## Constraints

- **Ingestion**: Must support cold-start and incremental ingestion — required by demand scope
- **Downloader**: Must use edgartools — explicit requirement
- **Data source**: Must consume universe from ClickHouse table `data_quant.us_stock_universe` — explicit requirement
- **State store**: PostgreSQL is source of truth for operational/extraction state — selected architecture
- **Accuracy**: Strict correctness gate for v1 acceptance — selected quality bar
- **Observability**: Parse/extraction logs must be persisted with failure reasons — explicit requirement for diagnostics and continuous improvement

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use PostgreSQL as operational source of truth | Supports reliable state transitions, auditability, and deterministic replay for precision-first pipeline | — Pending |
| Use high-value-first form scope for v1 | De-risks delivery while proving E2E quality loop on highest-return forms first | — Pending |
| Enforce strict quality threshold | Project objective prioritizes correctness over raw coverage/speed | — Pending |
| Adopt tiered extractor strategy (deterministic first, LLM last) | Matches reference design to minimize hallucination and maintenance cost | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-05 after initialization*
