# Autopilot Spec

## Goal
Implement the first deterministic production slice implied by `DEMANDS.md`: issuer-route `10-Q` / `10-Q/A` numeric extraction for three document-level fields using an XBRL-first path.

## In Scope
- `total_revenue`
- `operating_income`
- `net_income`
- XBRL-first candidate selection for issuer `10-Q` / `10-Q/A`
- Replayable evidence persistence for numeric extractions
- Offline pytest coverage with fake filing/XBRL fixtures

## Out of Scope
- Owner route
- Holding route
- Text/snippet extraction
- Review UI
- Full 53-field rollout
- Router refactor

## Functional Requirements
1. Numeric field specs can declare XBRL concept priorities and selection constraints.
2. The numeric extraction engine can inspect XBRL facts and choose the best candidate for the three target fields.
3. Candidate selection prefers concept priority, correct statement type, dimensionless facts, and quarter-duration facts for `10-Q`.
4. Extraction returns replayable evidence metadata (`xbrl_concept`, `source_xpath`, `source_span`) when available.
5. CLI bundle-building persists the richer numeric evidence.
6. Tests cover success cases and common false-positive cases.

## Acceptance Criteria
- Fake XBRL data with mixed concepts, dimensions, and periods yields the correct result for the three target fields.
- Dimensioned-only or wrong-duration facts are not selected for the `10-Q` slice.
- `_build_bundles_from_provider()` produces numeric `FactInput` plus `EvidenceInput` containing concept and replay context.
- `pytest` passes for the new tests.
