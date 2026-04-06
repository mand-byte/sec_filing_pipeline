# Phase 3 Tier2 Offline Loop Design

## 1. Goal
Build a Phase 3, accuracy-first Tier2 extraction loop for regex-based text/section extraction with explicit closure via golden set regression, while keeping LLM disabled.

## 2. Scope
### In scope
- Tier2 text extraction pipeline extension (section/window-anchored regex; no full-document regex scan).
- Review closure flow for ambiguous/first-seen/outlier results.
- Offline evaluation script for rapid iteration: run -> inspect artifacts -> adjust regex + golden set -> rerun.
- Deterministic artifacts for regression tracking.

### Out of scope
- LLM span normalization (deferred to later phase).
- Frontend/manual review UI implementation.
- Expanding to unrelated routes/fields beyond selected Tier2 starter set.

## 3. Chosen Approach
Use **Approach A**: extend existing extraction/persistence/logging pipeline with a parallel Tier2 text track and introduce a dedicated offline evaluator and golden set contract.

Why:
- Aligns with current precision-first roadmap.
- Reuses stable components already in place (`run-once`, persistence, artifacts, logs).
- Keeps failure analysis debuggable by separating locator/regex issues from model behavior.

## 4. Architecture
### 4.1 Registry and contracts
Add a text extraction contract layer parallel to numeric:
- `src/pipeline/extraction/text_contracts.py`
- `src/pipeline/extraction/text_registry.py`

Contract shape:
- `field_name`
- `route`
- `form_families`
- `locators` (ordered reliability chain)
- `window_rules` (section/item anchors)
- `regex_rules` (local patterns only)
- `normalization` (optional structured packing to `value_json`)
- `qa_rules`

Boundary rules:
- Max 3 locators per field.
- Regex must run on anchored window, never on full document body.
- Field config remains declarative; extraction logic remains generic.

### 4.2 Tier2 engine
Add:
- `src/pipeline/extraction/text_engine.py`

Behavior:
1. Resolve candidate windows from section/item anchors.
2. Run ordered regex candidates within window scope.
3. Normalize and QA-check output.
4. Return either:
   - `ok`: `value_text` or `value_json` + lineage/evidence metadata
   - `error`: explicit `error_code`

Representative error codes:
- `WINDOW_NOT_FOUND`
- `PATTERN_NOT_MATCHED`
- `MULTIPLE_CANDIDATES`
- `NORMALIZATION_FAILED`
- `QA_FAILED`

### 4.3 Pipeline integration
Extend `src/cli.py` route processing flow:
- Keep numeric extraction unchanged.
- Run text extraction after numeric for matching `form_family`.
- Persist in one bundle transaction (same current atomic behavior model).
- Continue run even when individual field extraction fails.

Storage reuse:
- `ExtractedFact.value_text` / `ExtractedFact.value_json`
- `ExtractionEvidence` for locator/path/span/raw/normalized
- `PipelineLog` for structured extraction errors

### 4.4 Review closure gate
Add review decision gate for Tier2 outcomes (new module under `src/pipeline/review/`):
- `first_seen_for_issuer`
- `first_seen_template`
- `outlier_vs_history`

Gate result:
- Auto-accept and store fact, or
- Create `review_task` with deterministic reason and priority.

The run must not block when review tasks are created.

### 4.5 Offline evaluator (core requirement)
Add offline entrypoint:
- `scripts/offline_tier2_eval.py` (or equivalent CLI command)

Input:
- Local filing fixtures (html/xml/txt snapshots)
- Tier2 regex config (`configs/tier2/regex/*.yaml`)
- Golden set config (`configs/tier2/golden_set/*.yaml`)
- Optional selectors (`route`, `form_family`, `field`, `case_id`)

Output per run:
- `artifacts/offline/<run_id>/summary.json`
- `artifacts/offline/<run_id>/by_field.json`
- `artifacts/offline/<run_id>/failures.ndjson`
- `artifacts/offline/<run_id>/candidates.ndjson`
- `artifacts/offline/<run_id>/diff.md`

Purpose:
Enable fast local loop for regex and golden set tuning without network dependency or live incremental state.

## 5. Data Flow
### 5.1 Online run (`run-once`)
1. Load securities and fetch filings (existing provider).
2. Numeric extraction executes (existing).
3. Text extraction executes for Tier2 fields.
4. Persist facts/evidence in atomic bundle write.
5. Log extraction failures with explicit error types.
6. Apply review gate and enqueue review tasks as needed.
7. Write run artifacts with text-coverage and review metrics.

### 5.2 Offline eval run
1. Read fixture files + regex registry + golden set.
2. Execute text extraction only.
3. Compare expected vs actual at case/field granularity.
4. Emit deterministic artifacts.
5. Generate baseline diff for regression visibility.

## 6. Testing Strategy
### Unit tests
- `text_engine` locator/anchor/regex matching behavior.
- Error-code determinism.
- Window-only regex guard.
- Review gate rule triggers.

### Integration tests
- End-to-end `run-once` with mocked filings producing text facts/evidence/logs/review tasks.
- Mixed success/failure bundle behavior (run continues, watermark behavior preserved).

### Offline regression tests
- Golden set replay test in CI.
- Regression block on newly introduced failures for previously passing cases.

## 7. Closure Rules (收口)
A Tier2 field set is considered closed for rollout only when all are true:
1. Precision and recall meet agreed thresholds on golden set.
2. No regressions against previous accepted baseline.
3. Failure distribution is explainable by known error codes.
4. Review queue growth is stable (no uncontrolled spike).

## 8. Milestones
1. Text contracts + registry scaffolding.
2. Text engine + error codes.
3. Pipeline persistence/log integration.
4. Review gate + task enqueueing.
5. Offline evaluator + artifact contract.
6. Golden set seed and regression baseline.

## 9. Acceptance Criteria
- Offline evaluator supports rapid local iteration loop using artifacts.
- Tier2 extraction writes reproducible facts/evidence/logs.
- Golden set regression can prevent accidental regex regressions.
- No LLM dependency in Phase 3 implementation.
