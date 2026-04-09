# Owner Route First Slice Plan

## Decision
Start owner-route work with a row-grain Form 4 transaction slice.

## Why this slice
- `EXTRACTION_FIELDS.md:163-168` shows the cleanest deterministic owner fields are Form 4 transaction-row metrics.
- Context7/edgartools docs indicate `filing.obj()` for Form 4 exposes transaction objects with `shares`, `price_per_share`, and `shares_owned_following_transaction`.
- The current blocker is persistence grain, not extractor logic: `src/db/models.py:76-117` only supports `(accession_no, route, field_name)` uniqueness and cannot represent multiple transaction rows in one filing.

## First implementation scope
1. Add row-grain persistence keys for facts/evidence.
2. Add deterministic Form 4 extraction for:
   - `shares_acquired_or_disposed`
   - `transaction_price_per_share`
   - `shares_owned_following_txn`
3. Add focused tests for row-level persistence and extraction.

## Minimal schema direction
Add a row identity field that is stable within a filing, such as `subject_key` (string), to both `ExtractedFact` and `ExtractionEvidence`, and make it part of the uniqueness rule.

Recommended first shape:
- `subject_key: String | nullable=False | default='document'`
- Update fact uniqueness to `(accession_no, route, field_name, subject_key)`
- Add `subject_key` to evidence uniqueness lookup as well

This is the smallest change that unlocks owner-route multi-row storage while remaining compatible with the existing issuer document-level path.

## Code areas to change
- `src/db/models.py`
- `src/pipeline/services.py`
- `src/pipeline/extraction/contracts.py` or new owner-specific extraction contract module
- `src/pipeline/edgar_provider.py` (likely unchanged for fetch, only consumed differently)
- `src/cli.py`
- tests: new persistence + Form 4 slice tests

## Acceptance criteria
- Facts/evidence can persist multiple rows for one filing without collisions.
- Existing issuer document-level tests keep passing.
- A fake Form 4 filing with two transactions persists distinct rows for the three target fields.
- Validation passes: pytest, ruff, compileall.
