# SEC Filing Backend Roadmap Design

Date: 2026-04-03

## 1. Purpose

This document defines the roadmap and decomposition strategy for building the SEC filing backend described in `DEMANDS.md`.

The roadmap is explicitly constrained by the following rule: the end state must satisfy the full scope and hard requirements in `DEMANDS.md`, even when early execution phases intentionally limit scope to a narrower production slice.

The roadmap is therefore split into two levels:

- program roadmap: the full sequence required to satisfy all requirements in `DEMANDS.md`
- execution roadmap: the near-term implementation scope that should be planned and built first

## 2. Fixed Design Decisions

The following decisions are fixed for this roadmap unless a later approved design supersedes them.

### 2.1 Delivery shape

- The roadmap will use a mixed decomposition strategy.
- Platform capabilities are built first.
- Business routes are onboarded incrementally on top of the shared platform.
- The first route-specific production slice is the `owner` route.

### 2.2 Storage strategy

- `PostgreSQL` is the primary system of record and control plane store.
- `ClickHouse` is not the primary correctness boundary.
- `ClickHouse` is used for reference data intake and analytical or downstream consumption where appropriate.
- The upstream universe source is `data_quant.us_stock_universe`.

### 2.3 Quality and correctness strategy

- The system is `precision-first`.
- The roadmap optimizes for ingestion correctness, auditability, amendment retention, and deterministic idempotency before broader form coverage.
- Low-priority extraction methods must never silently override high-priority methods.
- LLM usage remains restricted to schema-constrained structuring of already-located narrative snippets.

### 2.4 Route rollout order

- First route: `owner`
- Second route: `holdings` with independent `13F` discovery
- Third route: `issuer`

This order is chosen because `owner`, especially `3/4/5`, is the best early validation target for structured-first parsing, amendment handling, evidence persistence, and decision-layer correctness.

## 3. Program-Level Goal

The final roadmap outcome must satisfy the complete requirements of `DEMANDS.md`, including but not limited to:

- cold-start and incremental ingestion
- full raw artifact persistence
- append-only storage and ETL-side deterministic deduplication
- preservation of original and amendment filings together
- controlled parser fallback in the fixed precedence order
- route-specific fact tables and audit trail persistence
- review queue driven by exception cases only
- security mapping with fixed precedence and auditability
- spaCy model training, versioning, evaluation, rollback, and feedback loop
- LLM narrative snippet structuring with schema validation and no-hallucination guardrails
- QA, replay, auditing, and acceptance metrics

## 4. Recommended Top-Level Decomposition

The system is decomposed into four roadmap layers.

### 4.1 Platform Control Plane

Responsibilities:

- configuration and environment handling
- route and form canonicalization
- amendment grouping and event time rules
- natural keys and deterministic idempotency
- ingestion state tracking
- raw archive and parser input snapshots
- parser registry and model registry
- review queue persistence and audit links

This layer defines the correctness boundaries for the rest of the system.

### 4.2 Route Implementations

Responsibilities:

- route-specific discovery
- route-specific deterministic parsing
- route-specific mandatory field matrices
- route-specific fact tables
- route-specific evidence location logic

Routes are implemented separately:

- `owner`
- `holdings`
- `issuer`

Each route consumes shared platform contracts but keeps route-specific discovery and parser logic independent.

### 4.3 Decision and Quality Layer

Responsibilities:

- parser cascade orchestration
- attempted-method and chosen-method tracking
- fallback reason tracking
- conflict persistence
- confidence scoring
- decision-state assignment
- review-queue admission
- QA metrics and audit sampling

### 4.4 Learning and Structuring Layer

Responsibilities:

- spaCy inference integration
- training data generation and feedback loop
- model registry, shadow mode, and rollout evaluation
- LLM snippet structuring adapter

This layer is subordinate to the deterministic and structured extraction layers. It exists to reduce review load without weakening precision constraints.

## 5. Roadmap Phases And Exit Criteria

The roadmap is organized into seven phases.

### 5.1 Phase 0: Foundation and Architecture Freeze

Objective:

- Freeze the project boundaries, domain taxonomy, storage roles, and core schemas before broad implementation begins.

Primary deliverables:

- package and CLI structure
- configuration system
- route and form canonicalization rules
- amendment and event-time rules
- core table and entity definitions
- parser and model registry contracts

Exit criteria:

- route and form taxonomy is fixed in code-level contracts
- amendment family and event-time rules are fixed
- append-only and natural-key constraints are represented in the storage design
- later route implementations can build on the schemas without redefining core entities

### 5.2 Phase 1: Ingestion Control Plane and Raw Archive

Objective:

- Build the SEC acquisition, raw persistence, replay, and incremental state machinery.

Primary deliverables:

- SEC client with compliant user-agent, throttling, retry, and observability
- route-aware discovery framework
- deterministic raw artifact persistence for filing and document levels
- decoded and cleaned text persistence
- parser input snapshots
- ingestion state tracking and replay commands

Exit criteria:

- the same accession can be replayed without duplicate fact creation
- filing-level and document-level artifacts are both persisted
- source URL, fetch time, content metadata, byte size, and hash are traceable
- cold-start and incremental progress state are both supported

### 5.3 Phase 2: Owner Route First Production Slice

Objective:

- Use the `owner` route as the first end-to-end production validation slice, with `3/4/5` as the initial form family.

Primary deliverables:

- owner discovery implementation
- `3/4/5` XML parser
- ownership fact persistence
- evidence locator for XML-backed facts
- mandatory field matrix and validation rules

Exit criteria:

- `3/4/5` filings can be discovered, fetched, persisted, parsed, and written to append-only tables
- core ownership facts are sourced from XML first
- amendment family handling is correct
- every persisted fact includes method, evidence, locator, validation, confidence, and decision metadata

### 5.4 Phase 3: Decision Layer and Controlled Fallback

Objective:

- Turn parser fallback, conflict handling, confidence scoring, and review admission into shared platform capabilities.

Primary deliverables:

- parser cascade contract
- fallback reason taxonomy
- candidate persistence for competing outputs
- confidence scoring engine
- decision engine
- review queue and reason generation

Exit criteria:

- fallback occurs only in the fixed precedence order
- lower-priority methods do not override higher-priority results
- review and acceptance states are explainable
- parser conflicts are persisted and auditable

### 5.5 Phase 4: Holdings Route as an Independent `13F` System

Objective:

- Implement `13F-HR` and `13F-HR/A` as an independent holdings route with its own discovery flow and information-table parsing.

Primary deliverables:

- 13F discovery implementation
- information table parser
- holdings fact model and persistence
- row and cell level evidence location
- holdings-specific review rules and metrics

Exit criteria:

- `13F` discovery is independent from issuer-only logic
- holdings rows are sourced from structured tables first
- holdings evidence can point to specific rows and cells
- amendment and idempotency rules hold for holdings data as well

### 5.6 Phase 5: Security Mapping, Issuer Route, and Shared Reference Layer

Objective:

- Introduce the shared security mapping layer and onboard the issuer route.

Primary deliverables:

- reference data ingestion from `data_quant.us_stock_universe`
- exact-id, composite-key, and fuzzy fallback mapping engine
- mapping audit trail
- issuer discovery and deterministic parser family
- reviewed correction feedback loop for mapping references

Exit criteria:

- mapping precedence is enforced and auditable
- the one-to-one `figi` and `cik` property is used where applicable
- filings after `delisted_utc` are skipped for `active=0` securities
- issuer route facts are integrated into the shared decision layer

### 5.7 Phase 6: Learning, LLM Structuring, QA, and Acceptance Closure

Objective:

- Complete the learning, review reduction, QA, and acceptance portions of the system without weakening correctness guarantees.

Primary deliverables:

- spaCy inference adapter
- training and evaluation pipeline
- reviewed feedback loop for labels
- LLM snippet structuring adapter
- daily QA reporting
- audit sampling, benchmark, replay, and runbook tooling

Exit criteria:

- spaCy and LLM are operating as controlled fallback layers only
- model rollout is versioned and evaluated
- QA reporting covers forms, routes, parser methods, and fact types
- the remaining acceptance criteria from `DEMANDS.md` are demonstrably closed

## 6. Work Packages And Dependencies

Each phase is further decomposed into work packages with explicit dependency rules.

### 6.1 Phase 0 work packages

- `P0.1` project structure and CLI entrypoints
- `P0.2` domain enums and canonicalization
- `P0.3` core entities and storage contracts
- `P0.4` natural-key and idempotency key design
- `P0.5` storage role allocation across PostgreSQL, raw archive, and ClickHouse

Dependency rules:

- `P0.2` and `P0.3` are prerequisites for all later work
- `P0.4` must be frozen before ingestion logic is implemented
- `P0.5` must be fixed before persistence contracts are finalized

### 6.2 Phase 1 work packages

- `P1.1` SEC client
- `P1.2` discovery framework
- `P1.3` raw persistence
- `P1.4` decode and parser snapshot persistence
- `P1.5` ingestion state and replay

Dependency rules:

- `P1.1` depends on `P0.5`
- `P1.3` and `P1.5` depend on `P0.4`
- `P1.4` depends on `P1.3`
- all route implementations must use `P1.2` rather than bypassing the discovery contract

### 6.3 Phase 2 work packages

- `P2.1` owner discovery implementation
- `P2.2` ownership XML parser
- `P2.3` ownership fact model
- `P2.4` XML evidence locator
- `P2.5` owner-route validation rules

Dependency rules:

- `P2.2` depends on the Phase 1 ingestion outputs
- `P2.3` depends on the frozen core entities from `P0.3`
- `P2.4` depends on parsed XML structures from `P2.2`
- `P2.5` spans extraction, evidence, and amendment consistency

### 6.4 Phase 3 work packages

- `P3.1` parser cascade contract
- `P3.2` competing candidate persistence
- `P3.3` confidence engine
- `P3.4` decision engine
- `P3.5` review queue and reason generation

Dependency rules:

- Phase 3 is first integrated with the owner route
- later routes must plug into the shared cascade contract
- the confidence and decision engines must share a single field-criticality model

### 6.5 Phase 4 work packages

- `P4.1` 13F discovery implementation
- `P4.2` information table parser
- `P4.3` holdings fact model
- `P4.4` holdings validation rules
- `P4.5` holdings decision integration

Dependency rules:

- `P4.1` reuses the shared discovery framework but keeps route logic separate
- `P4.2` enters through the shared parser cascade
- `P4.3` must not be distorted to fit the ownership schema
- `P4.5` reuses the shared decision layer with route-specific rules layered on top

### 6.6 Phase 5 work packages

- `P5.1` reference ingestion from `data_quant.us_stock_universe`
- `P5.2` mapping engine
- `P5.3` mapping auditability
- `P5.4` issuer discovery and parser family
- `P5.5` mapping correction feedback loop

Dependency rules:

- `P5.1` is the prerequisite for `P5.2`
- `P5.2` serves all routes rather than being embedded in any one route
- `P5.4` must reuse the shared decision layer rather than fork it
- `P5.5` depends on review queue and audit links already being stable

### 6.7 Phase 6 work packages

- `P6.1` spaCy inference adapter
- `P6.2` training data pipeline
- `P6.3` model evaluation and rollout process
- `P6.4` LLM structuring adapter
- `P6.5` QA, benchmark, audit sampling, replay, and runbook tooling

Dependency rules:

- `P6.1` depends on reliable deterministic snippet location
- `P6.2` depends on both silver-label and reviewed-label inputs
- `P6.4` depends on a stable snippet evidence contract
- `P6.3` and `P6.5` depend on audit and review data already being persisted cleanly

## 7. Hard Dependency Rules

The following dependency rules are non-negotiable.

1. Natural keys and append-only rules must exist before ingestion logic is considered production-eligible.
2. Raw archive and parser input snapshots must exist before parser rollout expands.
3. Structured and deterministic parsers must establish the baseline before spaCy or LLM is used as fallback.
4. Review reason taxonomy must exist before review-rate metrics are treated as meaningful.
5. Independent `13F` discovery contracts must exist before holdings route implementation is accepted.

## 8. Program-Level Success Criteria

The roadmap is successful only if both structural and outcome requirements are satisfied.

### 8.1 Structural success criteria

- append-only primary tables are preserved
- original and amendment filings coexist
- ETL-side deterministic deduplication is enforced
- structured-first source precedence is preserved
- LLM scope is restricted to snippet structuring
- raw artifacts, parser snapshots, evidence, and decision traces are replayable
- review queue admission is exception-driven
- `13F` remains an independent route
- security mapping remains auditable and correctable

### 8.2 Outcome success criteria

- critical numeric and identifier fact auto-accepted precision is at least `99%`
- exact-id security mapping precision is at least `99%`
- narrative structuring auto-accepted precision is at least `95%`
- review rates decline only without sacrificing precision
- QA can be sliced by route, form, parser method, and fact type
- any accession can be replayed end to end

## 9. Phase Exit Metrics

### 9.1 Phase 0

- schema and core entity design are frozen
- route and form taxonomy are frozen
- amendment family and event-time rules are frozen

### 9.2 Phase 1

- repeated accession ingestion does not create duplicate facts
- filing and document artifacts are both persisted
- replay works from archived inputs

### 9.3 Phase 2

- `3/4/5` discovery through fact persistence works end to end
- XML is the primary source for core ownership facts
- amendment behavior is correct

### 9.4 Phase 3

- fallback order is platform-enforced
- decision state and review reason are fully persisted
- conflict cases are reproducible and auditable

### 9.5 Phase 4

- `13F-HR` and `13F-HR/A` discovery is independent and functional
- holdings evidence is row- and cell-addressable
- holdings idempotency and amendment handling are correct

### 9.6 Phase 5

- mapping precedence is enforced and auditable
- `active=0` and `delisted_utc` rules are applied correctly
- issuer route is integrated into the shared platform contracts

### 9.7 Phase 6

- spaCy lifecycle management is operational
- LLM adapter is schema-safe and policy-constrained
- QA, audit, replay, benchmark, and runbook capabilities are complete
- all remaining `DEMANDS.md` acceptance items are closed

## 10. Execution Model

Work should be organized by system boundary rather than by library or technology.

Suggested responsibility areas:

- platform and control plane
- route parsers
- decision and quality systems
- intelligence layer including spaCy and LLM integration

This keeps route parsers from embedding ad hoc decision rules and prevents ML or LLM integration from dictating the control-plane schema.

## 11. First Implementation Planning Scope

The first implementation plan should not attempt the entire roadmap. It should cover only the minimum slice that validates the platform and correctness model.

Included in the first implementation plan:

- Phase 0
- Phase 1
- the minimum Phase 2 slice for the `owner` route, centered on `3/4/5`

That means the first plan should include:

- core schemas and storage contracts
- raw archive
- ingestion state
- replay support
- owner discovery
- `3/4/5` XML parsing
- ownership fact persistence
- XML evidence location
- basic validation rules
- minimum decision and review plumbing required for this slice

Explicitly excluded from the first implementation plan:

- `13F` route implementation
- broad issuer route rollout
- fuzzy security mapping
- spaCy training pipeline
- LLM structuring integration
- full QA platform rollout
- full form-family coverage

The purpose of the first implementation plan is to validate a durable platform shape using the route most suitable for proving structured-first correctness.

## 12. Expected First Slice Outcome

After the first implementation plan is completed, the system should be able to:

- perform cold-start and incremental owner filing ingestion
- persist raw artifacts and parser input snapshots
- parse `3/4/5` XML submissions
- write append-only records into PostgreSQL
- preserve original and amendment filings together
- attach evidence, validation, confidence, and decision metadata to key facts
- replay a single accession deterministically
- send conflict and exception cases into the review queue

If this minimum slice cannot be demonstrated cleanly, the roadmap should not proceed to broader route rollout.

## 13. Final Recommendation

Proceed with the roadmap in two layers:

1. program roadmap that ultimately satisfies all requirements in `DEMANDS.md`
2. immediate execution roadmap limited to `Phase 0 + Phase 1 + owner 3/4/5 minimum slice`

This approach minimizes early architectural drift while preserving a direct path to the full target system.
