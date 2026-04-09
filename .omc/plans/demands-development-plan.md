# DEMANDS.md Development Plan

## Requirements Summary
- Build a precision-first SEC filing backend with cold-start + incremental ingestion using `edgartools` as the required fetch/parsing base (`DEMANDS.md:3-10`).
- Support three routes: `issuer`, `owner`, `holding`, with stateless scheduler-driven progression based on `accepted_at` (`DEMANDS.md:42-50`).
- Deliver 53 deterministic numeric fields plus selected text/span outputs, with row/subject-grain persistence where required (`DEMANDS.md:52-57`).
- Preserve reviewable evidence and support a human-review correction loop (`DEMANDS.md:59-61`).
- Progress through phased rollout from deterministic infrastructure to review/UI, text understanding, and historical backfill (`DEMANDS.md:63-75`).

## Current Implementation Snapshot
### Already in place
- Database models for filings, facts, evidence, logs, review tasks, and watermarks exist in `src/db/models.py`.
- CLI run-loop, scheduler integration, provider fetch path, persistence service, and review gate plumbing exist in `src/cli.py`, `src/pipeline/edgar_provider.py`, `src/pipeline/services.py`, and `src/pipeline/review/*`.
- Numeric/text registries exist in `src/pipeline/extraction/registry.py` and `src/pipeline/extraction/text_registry.py`.

### Implemented in this session
- First deterministic production slice: issuer-route `10-Q` / `10-Q/A` XBRL-only extraction for `total_revenue`, `operating_income`, and `net_income`.
- XBRL candidate filtering/ranking and evidence emission implemented in `src/pipeline/extraction/engine.py`.
- Slice config added in `src/pipeline/extraction/contracts.py` and `src/pipeline/extraction/registry.py`.
- CLI bundle-building now preserves XBRL evidence and guards empty issuer 10-Q slice outcomes in `src/cli.py`.
- 13 offline tests now cover engine ranking, amendment handling, XBRL precedence, empty-bundle handling, and golden-batch scorer compatibility.

### Still missing / incomplete
- Most issuer numeric fields beyond the first 3-field slice.
- Owner-route deterministic XML/object extraction.
- Holding-route 13F extraction.
- Text/span extraction beyond existing placeholder rules.
- Human-review API/UI workflow.
- Full golden-set / offline artifact rollout beyond the targeted 10-Q batch helper.
- Historical backfill + daily incremental production hardening.

## Acceptance Criteria
### Phase A — Deterministic issuer seed
- Issuer `10-Q` / `10-Q/A` extraction for the current 3 fields remains green in tests.
- XBRL evidence (`xbrl_concept`, source reference, source span) persists for successful facts.
- Empty issuer 10-Q slice outcomes are logged and not silently treated as successful extraction.

### Phase B — Expand issuer deterministic numerics
- Add next issuer statement/document fields in deterministic channels only (XBRL/object/table as appropriate).
- Each added field gets field-specific tests and regression coverage.
- Non-document fields remain subject/row-grain in persistence.

### Phase C — Owner route
- Support Forms 3/4/5 and 13D/13G/144 through XML/object-first extraction.
- Preserve transaction/reporting-person/form144 notice grain.
- Add targeted fixtures/tests for row selection and persistence.

### Phase D — Holding route
- Support 13F-HR / 13F-HR/A filing totals and position-level rows.
- Add row-level consistency checks against filing totals.

### Phase E — Text/span extraction + review evidence
- Implement bounded span extraction for the targeted text fields.
- Persist reviewable evidence per `EXTRACTION_METHOD.md` and `DEMANDS.md:59-61`.
- Route low-confidence or first-seen cases into review tasks.

### Phase F — Human review workflow + UI/API
- Expose review queue CRUD/API around `ReviewTask` and `ReviewDecision`.
- Support side-by-side source/evidence review and correction persistence.
- Ensure correction loop can emit `error_code + golden_case + patch` artifacts.

### Phase G — Golden/eval hardening
- Expand offline eval coverage to the broader numeric field set.
- Align evaluation helpers with runtime selection rules.
- Make golden artifacts/config discoverable and runnable without hidden paths.

### Phase H — Backfill + scheduler hardening
- Historical replay over the target universe.
- Daily incremental execution with durable progress/watermark semantics.
- Route-level monitoring/log review workflow for sustained runs.

## Implementation Steps
1. **Lock current slice as baseline**
   - Keep the new issuer `10-Q` XBRL-only path stable in:
     - `src/pipeline/extraction/contracts.py`
     - `src/pipeline/extraction/registry.py`
     - `src/pipeline/extraction/engine.py`
     - `src/cli.py`
     - `tests/pipeline/extraction/test_numeric_engine.py`
     - `tests/test_cli_numeric_bundles.py`
     - `tests/test_golden_10q_numeric_batch.py`
2. **Expand issuer deterministic fields**
   - Add the next batch of issuer numeric fields using field-specific registry metadata and deterministic extractors.
   - Prioritize statement-style document fields before multi-row issuer fields.
3. **Implement owner-route deterministic extraction**
   - Fill `owner` route coverage from XML/object-backed forms with subject-grain persistence.
4. **Implement holding-route extraction**
   - Add 13F filing totals plus position-row extraction and row-vs-total checks.
5. **Strengthen text/span extraction**
   - Move from placeholder regex windows to bounded span + evidence contracts.
6. **Build review API/UI**
   - Add backend review endpoints first, then UI/workbench tied to persisted evidence.
7. **Harden evaluation/backfill paths**
   - Make eval fixtures/config runnable from checked-in paths and scale the golden set.
8. **Run staged productionization**
   - Cold-start backfill, then scheduled incremental operation.

## Risks and Mitigations
- **Scope explosion**: keep work in route/form/field slices; verify each slice before expanding.
- **Runtime/eval drift**: share ranking/filtering logic or mirror it explicitly with regression tests.
- **Silent extraction misses**: preserve explicit error codes and slice-specific empty-result logging.
- **Review-system delay**: build backend review contracts before attempting a full UI.

## Verification Steps
- `uv run pytest -q tests`
- `uv run --with ruff ruff check src tests`
- `uv run python -m compileall src tests`
- Route-specific regression fixtures for each newly added slice
- Independent architecture/code/security review before each major slice lands

## ADR
### Decision
Proceed in phased slices, using the implemented issuer `10-Q` deterministic XBRL path as the baseline and extending route-by-route.

### Drivers
- `DEMANDS.md` is much broader than the current codebase; phased implementation reduces rework.
- Deterministic extractor quality must precede review/UI and text understanding.
- Existing code already provides enough scaffolding to expand incrementally.

### Alternatives considered
- **Big-bang full DEMANDS implementation** — rejected due to large surface area and weak verification.
- **UI/review-first** — rejected because extraction correctness is not broad enough yet.
- **Owner/holding-first** — rejected because issuer statement numerics are the strongest deterministic starting point and already partially landed.

### Why chosen
This plan preserves the work already completed, keeps verification tight, and follows the roadmap in `DEMANDS.md`.

### Consequences
- Faster iteration and lower regression risk.
- Broader feature coverage still requires multiple follow-up slices.

### Follow-ups
- Phase B: issuer field expansion.
- Phase C: owner route.
- Phase D: holding route.
- Phase E/F: text + review workflow/UI.
