# SEC Filing Backend Rollout Design

Date: 2026-04-03

## 1. Goal

Build a precision-first SEC filing backend that satisfies `DEMANDS.md` while keeping runtime workers stateless, persisting all operational state in PostgreSQL, using deterministic raw artifact storage for replay/audit, and using ClickHouse mainly as an upstream ticker/market-data source plus optional downstream analytics sink.

This design is intentionally broader than the current owner-route Phase 3 slice. It defines the target system boundary and the rollout order needed to close the gap between the current repository state and the full requirement set.

## 2. Current State Summary

The current repository already has a meaningful but narrow foundation:

- owner-route processing entrypoints exist in `src/cli.py`
- owner-route parsing currently focuses on `3/4/5`
- the implemented decision chain is limited to `structured_xml -> deterministic_rule -> needs_review`
- PostgreSQL-backed core tables already exist for filing/document/fact/review persistence
- parse-route attempt logging exists for the current owner slice
- deterministic raw artifact persistence exists

The codebase does **not** yet meet the full requirement set in `DEMANDS.md` because the following are still missing or incomplete:

- issuer route coverage
- independent holdings/`13F-HR` route coverage
- complete parser cascade including spaCy and LLM layers
- security mapping system
- model registry / training / shadow evaluation loop
- daily QA / benchmark / audit reporting
- full route-agnostic ingestion state and orchestration layer

## 3. Fixed Decisions

The following decisions are fixed for this rollout.

### 3.1 Storage roles

- **PostgreSQL is the only system-of-record database.**
- **Raw artifacts do not live inside PostgreSQL blobs.** They live in deterministic file storage, referenced by PostgreSQL metadata.
- **ClickHouse is not responsible for ingestion correctness.**
- ClickHouse is used for:
  - ticker universe input
  - market / K-line / macro data input
  - optional downstream analytics or published fact sync later

### 3.2 Runtime model

- workers and scheduled functions are stateless
- every invocation reads required state from PostgreSQL
- no correctness-critical process-local cache is allowed
- replay behavior must be driven by persisted run and cursor state, not in-memory state

### 3.3 Ingestion policy

- cold start begins from 2014 onward
- incremental progression is tracked in PostgreSQL
- incremental state must use both:
  - `last_acceptance_datetime_utc`
  - `last_accession_no`
- event ordering prefers `acceptance_datetime_utc`; only downgrade when absent

### 3.4 Universe policy

- ticker scope is sourced from ClickHouse
- issuer/owner/holdings discovery should be driven from the upstream universe and route-specific discovery rules
- if `active = 0` and filing acceptance time is later than `delisted_utc`, that filing is skipped

### 3.5 Correctness policy

- all primary tables are append-only
- idempotency is guaranteed by ETL-side natural keys / dedup keys
- original and amendment filings always coexist
- lower-priority parsers can only fill gaps or produce candidates; they do not silently override higher-priority sources
- every accepted fact must retain evidence, locator, parser method, confidence, decision state, and validation output

## 4. Target Architecture

### 4.1 Major components

1. **Universe Loader**
   - reads target ticker/issuer universe from ClickHouse
   - normalizes CIK/ticker/FIGI inputs for downstream route planners

2. **Route Planners**
   - issuer planner
   - owner planner
   - holdings planner (`13F`-specific, independent from issuer-only discovery)

3. **Discovery Layer**
   - translates route + universe state into filing discovery tasks
   - handles cold-start windows and incremental windows

4. **Download + Raw Archive Layer**
   - fetches filing payloads and attachments
   - persists filing-level and document-level raw artifacts to deterministic storage
   - stores content hash, URL, byte length, content type, fetch timestamps, decoded text paths, parser snapshot paths in PostgreSQL

5. **Canonical Index Layer**
   - writes canonical filing/document rows
   - performs form canonicalization, accession normalization, amendment grouping, and event-time assignment

6. **Parser Cascade Layer**
   - applies ordered extractors:
     - `structured_xbrl`
     - `structured_xml`
     - `official_table` / `information_table`
     - `deterministic_rule`
     - `spacy_model`
     - `llm_structuring`
   - records all attempts and fallback reasons

7. **Decision Layer**
   - scores confidence
   - resolves source conflicts by fixed precedence
   - decides `accepted`, `accepted_with_warning`, `needs_review`, or `dropped`

8. **Security Mapping Layer**
   - links extracted facts to securities using fixed precedence rules
   - records candidate sets, confidence, and review reasons

9. **QA / Audit Layer**
   - computes route/form/parser/fact-type metrics
   - supports replay trace for a single accession
   - supports benchmark/audit sampling

10. **Model Lifecycle Layer**
    - model registry
    - parser registry
    - training dataset lineage
    - reviewed-correction feedback loop
    - shadow / A-B evaluation metadata

### 4.2 Stateless execution model

Each run executes as:

1. read universe snapshot and ingestion state from PostgreSQL / ClickHouse
2. derive discovery tasks
3. fetch new filings and persist raw artifacts
4. canonicalize and index filings/documents
5. parse through the ordered cascade
6. persist facts, review items, mapping attempts, and audit logs
7. update PostgreSQL ingestion state atomically at the workflow boundary

No step assumes any prior in-memory process state.

## 5. PostgreSQL Data Model

### 5.1 Core operational tables

Required core tables in PostgreSQL:

- `ingestion_state`
- `filing_index`
- `filing_document`
- `parse_route_log` / parse attempt audit table
- `extracted_fact`
- `review_queue`
- `filing_security_link`
- route-specific fact tables:
  - `issuer_facts`
  - `ownership_facts`
  - `holdings_facts`
- `parser_registry`
- `model_registry`
- mapping candidate / correction tables
- QA snapshot tables
- training data lineage tables

### 5.2 Raw storage contract

Raw storage keeps:

- submission payload
- primary document
- all attachments
- decoded text
- cleaned text
- parser input snapshot

PostgreSQL stores only:

- deterministic path
- SHA-256
- source URL
- content type
- byte length
- fetch timestamp
- document linkage keys

## 6. Route Strategy

### 6.1 Owner route

Owner route is the current foundation and should be the first route completed into a production-quality minimal loop.

First target forms:

- `3`, `3/A`
- `4`, `4/A`
- `5`, `5/A`
- later extend owner route to `13D`, `13D/A`, `13G`, `13G/A`, `144`, `144/A`

### 6.2 Issuer route

First issuer slice should prioritize the forms most likely to provide useful, high-signal metadata and narrative events for quant workflows:

- `8-K`, `8-K/A`
- `10-Q`, `10-Q/A`
- `10-K`, `10-K/A`
- `6-K`, `6-K/A`
- `20-F`, `20-F/A`

Additional forms from `DEMANDS.md` should be onboarded after the common platform layer is stable.

### 6.3 Holdings route

`13F-HR` / `13F-HR/A` is a dedicated holdings route.

It must:

- use its own discovery strategy
- use information table / structured table extraction as the primary source
- produce line-level evidence and row/cell locators
- preserve original/amendment family state independently of issuer route logic

## 7. Parser and Decision Policy

### 7.1 Fixed parser precedence

For each fact type, the cascade order is:

1. `structured_xbrl`
2. `structured_xml`
3. `official_table` / `information_table`
4. `deterministic_rule`
5. `spacy_model`
6. `llm_structuring`

### 7.2 Fallback rules

A parser may fall back only when the higher-priority layer is:

- unavailable
- incomplete for required fields
- structurally unsupported
- invalid under explicit validation rules

All attempts must record:

- parser method
- status
- failure type
- error message
- fallback reason
- decision linkage
- whether the candidate was selected

### 7.3 Acceptance rules

- critical numeric and identifier facts require high-priority source + validation pass
- spaCy output does not independently auto-accept critical numeric / identifier facts
- LLM output does not independently auto-accept critical numeric / identifier facts
- low-risk narrative fields may be auto-accepted only when schema validation, evidence, and no-conflict checks all pass

## 8. Security Mapping Policy

Mapping precedence is fixed:

1. exact CUSIP
2. issuer CIK
3. explicit ticker history
4. composite keys
5. fuzzy issuer name

Every mapping attempt must retain:

- `match_method`
- `match_key_raw`
- `match_confidence`
- `candidate_count`
- upstream reference linkage

Ambiguous mappings go to review and are never silently accepted.

## 9. spaCy and LLM Roles

### 9.1 spaCy role

spaCy is a review-reduction layer used primarily for:

- entity/span detection in narrative text
- relation/span categorization when needed
- locating candidate snippets for downstream structuring

spaCy does not replace discovery, truth arbitration, or deterministic parsing.

### 9.2 LLM role

LLM usage is narrowly constrained:

- input is an already-located snippet plus explicit schema
- output must be strict JSON and schema-valid
- output must cite snippet-supported evidence
- LLM does not read the full filing to decide what to extract
- LLM does not perform final truth verification or security mapping arbitration

## 10. Rollout Plan

This design is too broad for one implementation plan and should be executed as a sequence of sub-project plans.

### Phase A1 — Owner route production closure

Goal:

- complete the current owner `3/4/5` slice into a stable production-quality loop

Focus:

- PostgreSQL-driven ingestion state
- replay-safe idempotency
- append-only audit trails
- complete review reason taxonomy for current slice
- deterministic raw/archive contract hardening

### Phase A2 — Common platform extraction

Goal:

- refactor owner-specific orchestration into route-agnostic platform contracts

Focus:

- route dispatcher
- parser registry
- canonical decision contracts
- run/cursor state
- generalized audit and review models

### Phase A3 — Issuer route minimum viable coverage

Goal:

- add first issuer forms and reusable issuer-specific deterministic parsing

Focus:

- issuer discovery
- issuer canonical facts
- narrative snippet location
- amendment family support

### Phase A4 — Holdings / 13F route

Goal:

- add independent holdings discovery and information-table extraction

Focus:

- 13F manager stream discovery
- holdings row extraction
- row/cell evidence locators
- amendment preservation

### Phase A5 — Security mapping

Goal:

- map filing facts to securities with review-safe precedence and ambiguity guards

### Phase A6 — QA / audit / benchmark layer

Goal:

- provide daily metrics, replay traceability, random audit sampling, and gold-set evaluation hooks

### Phase A7 — spaCy lifecycle

Goal:

- add model inference, dataset lineage, evaluation, shadow mode, and reviewed-feedback loop

### Phase A8 — LLM snippet structuring

Goal:

- add schema-constrained narrative structuring only after snippet location and decision policy are already stable

## 11. Testing Strategy

Testing should expand in the same phase order.

### 11.1 Foundation tests

- accession normalization
- form canonicalization / route dispatch
- amendment grouping
- raw store hashing / dedup
- ingestion cursor progression

### 11.2 Route tests

- owner route replay + idempotency
- issuer route canonical extraction
- 13F independent discovery and information-table extraction

### 11.3 Decision tests

- precedence enforcement
- fallback reason generation
- conflict routing to review
- confidence score + bucket generation

### 11.4 Model / mapping tests

- mapping precedence and ambiguity handling
- spaCy adapter integration
- LLM schema validation and guardrails

### 11.5 End-to-end tests

- cold-start from persisted PostgreSQL state
- incremental from persisted PostgreSQL state
- original + amendment coexistence
- accession replay trace reconstruction
- daily QA metrics generation

## 12. Non-Goals for the First Detailed Plan

The first detailed implementation plan should **not** attempt to deliver the entire backend at once.

It should focus on **Phase A1 only**:

- finish the owner route minimal production loop
- harden PostgreSQL state management
- make replay/idempotency/audit behavior explicit
- prepare clean contracts for later issuer and holdings expansion

That first plan is the shortest path from current code to a trustworthy base layer.
