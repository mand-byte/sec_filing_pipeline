# Autopilot Implementation Plan

## Chosen Slice
Build issuer-route `10-Q` / `10-Q/A` XBRL-first extraction for `total_revenue`, `operating_income`, and `net_income`.

## Why This Slice
- Matches the precision-first architecture in `DEMANDS.md` and `EXTRACTION_METHOD.md`.
- Uses the strongest existing channel (`edgartools` XBRL facts) before broader fallback work.
- Fits the current repository state: plumbing exists, field-aware extraction does not.
- Is small enough to verify properly with offline tests.

## Files To Change
- `src/pipeline/extraction/contracts.py`
- `src/pipeline/extraction/registry.py`
- `src/pipeline/extraction/engine.py`
- `src/cli.py`
- `tests/pipeline/extraction/test_numeric_engine.py`
- `tests/test_cli_numeric_bundles.py`

## Steps
1. Extend `NumericFieldSpec` with minimal XBRL selection metadata.
2. Add XBRL-first config for the three issuer fields in the registry.
3. Implement XBRL fact querying and candidate ranking in the numeric engine.
4. Persist concept/path/span evidence from numeric extraction in the CLI bundle builder.
5. Add offline pytest coverage for engine ranking and bundle construction.
6. Run `pytest`.
7. Run independent validation/review agents.

## Verification
- `pytest`
- Independent architecture/security/code review agents after tests pass
