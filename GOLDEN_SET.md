# Strict Numeric Golden Set (Authoritative Specification)

This document is the single authoritative specification for the strict numeric golden set. It defines truth tiers, canonical field coverage, entity-granular keys, source reliability policy, invariant handling, evaluation metrics, and release gates.

## Scope and non-goals

- Scope: numeric fields only, point-in-time truth, entity-granular evaluation, reproducible artifacts.
- Non-goals: legacy mixed-truth labeling, narrative implementation task lists, schedule/checklist prose.

## Truth tiers

- **Gold**: manually adjudicated or independently verified raw XML/XBRL truth; this is the only tier used for strict accuracy claims.
- **Silver**: `companyfacts` or `edgartools` object values used for bootstrap coverage and surveillance; silver does not count as gold accuracy.
- **Invariant**: accounting identities and internal consistency checks; invariant pass/fail is reported separately and never treated as truth.

The numeric golden set contains **53 unique fields**. Repeated appearances of the same canonical field on different form families (for example `total_revenue` on both `10-Q` and `S-1`) do not increase the field count.

Every golden record is keyed by `case_id + subject_id + field_name`. Filing-level truth is not sufficient for multi-row forms such as Form 4 transactions, 13F positions, proposal vote tables, executive compensation tables, or beneficial ownership holder tables.
Entity identity key is `case_id + subject_id + field_name`. Truth-row uniqueness is `(case_id, subject_id, field_name, truth_tier, truth_source)`. `is_applicable` is a row attribute and is not part of that uniqueness constraint.

## Canonical 53-field freeze and subject-type distribution

The field inventory is frozen at 53 canonical numeric fields.

Subject-type counts that must remain stable:

- `(issuer, filing)` = 20
- `(issuer, proposal)` = 4
- `(issuer, executive)` = 1
- `(issuer, holder_row)` = 2
- `(owner, transaction_row)` = 6
- `(owner, reporting_person)` = 8
- `(owner, form144_notice)` = 4
- `(holding, holding_position)` = 5
- `(holding, filing)` = 3

## Strict case/subject schema concepts

- `golden_case` is point-in-time and amendment-aware (`accepted_at`, `is_amendment`, `amendment_no`, `truth_cutoff_at`, source accession/snapshot metadata).
- `golden_subject` defines entity-granular rows (`subject_type`, `subject_key`, optional parent/ordinal).
- `golden_truth` stores truth rows with explicit tier/source/applicability and Decimal precision.
- Invariants are stored separately from truth.

Core strict-v2 tables:

- `golden_case`
- `golden_subject`
- `golden_truth`
- `golden_invariant_result`
- `golden_candidate`
- `golden_eval_run`
- `golden_eval_result`
- `golden_review_packet`

## Channel types by filing family

| Filing family | Primary channel type | Document-type routing |
|---|---|---|
| 10-K, 10-Q, 20-F | **XBRL-first** | Prefer XBRL concepts and taxonomy mapping for financial statements. |
| Selected financial exhibits in S-1/424B4 | **XBRL-first (when present)** | Use XBRL concepts for statement numerics; fall back to anchored tables only where XBRL absent. |
| 3, 4, 5, 13D, 13G, 13F-HR, 144 | **Object/XML-first** | Primary extraction/truth from raw XML and object-backed parsing. |
| DEF 14A | **HTML / anchored-table-first** | Ownership, proposal votes, and executive comp typically anchored-table driven. |
| 8-K, S-1, 424B4, SC TO-I, SC 13E3 (non-statement sections) | **HTML / anchored-table-first** | Deal terms and event-driven numerics often require anchored section/table parsing. |

Routing notes:

- **8-K**: mixed route. Itemized votes (e.g., 5.07) are table/anchor-heavy; transaction terms are often narrative anchors.
- **DEF 14A**: prioritize anchored compensation and ownership tables; do not treat filing-level aggregates as row truth when row subjects exist.
- **S-1 / 424B4 / SC TO-I / SC 13E3**: split routing by section; financial statements use XBRL-first where available, offering/deal terms use anchored-table/text locators.

## Truth source reliability ranking

Extraction/source preference by channel:

- Financial-statement filings: xbrl-querying ≈ getting-xbrl > extract-statements > company-facts
- XML/object filings: raw_xml > filing.obj()/typed object > anchored HTML/XML parsing

Allowed gold truth sources (orthogonal to extraction preference):

- Manual adjudication
- Independently verified raw XML/XBRL facts

Why this policy:

- For statement numerics, direct XBRL concept retrieval preserves concept identity, period context, and deterministic source locators better than downstream convenience layers.
- `companyfacts` is valuable for silver coverage/surveillance but is not strict gold truth because it is an aggregated endpoint.
- For 3/4/5, 13D/G, 13F-HR, and 144, primary extraction trust is raw XML plus object-backed parsing because these forms are fundamentally XML/object structured rather than XBRL-financial-statement driven.
- Manual adjudication remains a first-class gold truth source when independently verifiable machine extraction is unavailable or ambiguous.

## Cross-checks and accounting invariants

Use these invariants for validation and anomaly detection:

- `total_revenue >= operating_income`
- `diluted_eps ≈ net_income / shares_outstanding`
- `cash_and_equivalents >= 0`
- `total_debt >= 0`
- `gross_proceeds ≈ offering_price_per_share × securities_offered_qty`
- `net_proceeds ≈ gross_proceeds - underwriter_discount_total`
- `underwriter_discount_total > 0`
- `offering_price_per_share > 0`
- `shares_owned_following_txn == prior_balance + shares_acquired_or_disposed`
- `transaction_price_per_share > 0`
- `beneficial_ownership_pct ∈ [0,100]`
- `sole_voting_power + shared_voting_power >= beneficially_owned_shares (usually)`
- `sum(position_value_usd) ≈ info_table_value_total_usd`
- `count(positions) == info_table_entry_total`
- `sole_voting_auth_shares + shared_voting_auth_shares + none_voting_auth_shares == shares_or_principal_amount`

Auxiliary terms: `prior_balance` is the immediately preceding holdings balance for the same reporting-person/position key, and `position_count` (shown as `count(positions)`) is the number of info-table holding rows in the filing.

Interpretation policy:

- Invariants are diagnostic consistency checks, not truth rows.
- Invariant failures trigger review packets and mismatch artifacts.
- Invariant pass/fail is reported separately and must never be counted as gold accuracy.

## Metric definitions (strict denominators)

- `gold_strict_accuracy`: matched gold-applicable rows / total gold-applicable rows
- `gold_coverage`: candidate rows with status `ok` on gold-applicable rows / total gold-applicable rows
- `row_selection_accuracy`: rows where selected candidate hit correct `subject_id` / total gold-applicable rows
- `not_applicable_precision`: rows predicted absent only when truth is `not_applicable`
- `silver_alignment`: matched silver-applicable rows / total silver-applicable rows
- `invariant_pass_rate`: pass invariant rows / invariant rows with status `pass` or `fail`

## Artifact contract and stable phase gates

Each strict-v2 eval run must write:

Reproducibility note: `manifest.json` records config paths, applied filters, git SHA (when available), and source snapshot hashes.

- `artifacts/golden/<run_id>/manifest.json`
- `artifacts/golden/<run_id>/summary.json`
- `artifacts/golden/<run_id>/by_field.json`
- `artifacts/golden/<run_id>/coverage.json`
- `artifacts/golden/<run_id>/mismatches.ndjson`
- `artifacts/golden/<run_id>/silver_alignment.ndjson`
- `artifacts/golden/<run_id>/invariants.ndjson`
- `artifacts/golden/<run_id>/review_packets/<case_id>__<subject_key>__<field_name>.json`

Stable phase gates:

- **Phase 0 (inventory freeze):** exactly 53 canonical fields; required catalog keys and subject-type counts valid.
- **Phase 1 (deterministic seed):** minimum 20 gold-applicable rows per deterministic field class, minimum 5 distinct CIKs per field, and minimum 2 filing years per field; required forms are `10-K`, `10-Q`, `3`, `4`, `5`, `13D`, `13G`, `144`, `13F-HR`; required seeds are `MSFT`, `AAPL`, `AMZN`, `NVDA`, `TSLA`; gate is `gold_strict_accuracy = 1.0` and `row_selection_accuracy = 1.0` on deterministic fields.
- **Phase 2 (complex structure):** minimum 10 ADR/20-F rows, minimum 5 amendment pairs, and minimum 10 multi-row entity cases; required financial seeds are `JPM`, `BAC`, `WFC`, `GS`, `MS`, `C`, `JEF`, `LAZ`; gate is `gold_strict_accuracy >= 0.99`, `row_selection_accuracy = 1.0`, and `not_applicable_precision = 1.0`.
- **Phase 3 (historical expansion):** minimum 14 issuers spanning domestic + ADR/foreign issuers, with 2014-current coverage where data exists; gate is `gold_strict_accuracy >= 0.99`, `silver_alignment >= 0.98`, and `invariant_pass_rate >= 0.99`.
- **Phase 4 (surveillance scale-out):** silver + invariants are used for monitoring at scale while gold remains the release gate for strict claims.

## Concept registry and seed-ticker rationale

- Concept registry is mandatory and versioned: per-field concept candidates, priority order, form applicability, and explicit fallback derivations with required inputs.
- Preserve concrete concept knowledge (including IFRS candidates for 20-F coverage) as config, not prose.
- Curated seed-ticker sets are intentional (not random):
  - Phase-1 baseline includes `MSFT`, `AAPL`, `AMZN`, `NVDA`, `TSLA` for canonical XBRL, fiscal-year variance, magnitude, growth profile, and dense insider activity edge cases.
  - Phase-2 financial expansion includes names such as `JPM`, `BAC`, `WFC`, `GS`, `MS`, `C`, `JEF`, `LAZ` to cover bank and broker/advisory statement structure differences.

## Governance rules

- Gold truth allowed sources: manual adjudication or independently verified raw XML/XBRL.
- Silver sources (`companyfacts`, object convenience values) are for bootstrap/surveillance and never counted as gold.
- Decimal precision (`NUMERIC(38,10)` / `Decimal`) is required for strict golden-set data.
- If independent gold truth is unavailable for a row, keep it silver or invariant-only rather than inflating gold coverage.
