# Strict Golden Set V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a strict, point-in-time, entity-granular numeric golden set system that replaces the current mixed-truth design in `GOLDEN_SET.md` with independently auditable gold/silver/invariant data, reproducible artifacts, and executable DB-backed evaluation.

**Architecture:** Introduce a dedicated `src/pipeline/golden/` subsystem and normalized golden-set tables that store filing case, subject row, truth row, candidate row, evaluation run, and review packet separately. Gold truth comes only from manual adjudication or independently verified raw XML/XBRL anchors; companyfacts and `edgartools` object values remain silver bootstrap/surveillance data and are never counted as strict gold accuracy. Metrics are computed only on eligible denominators, amendment pairs and ADR/20-F cases are explicit sample strata, and every run writes a reproducible manifest plus mismatch artifacts.

**Tech Stack:** Python 3, SQLAlchemy, PostgreSQL, Typer, YAML, Decimal, edgartools, pytest

---

## 1. Scope

### In scope
- Numeric golden set only
- Canonical field inventory freeze for the 53 unique numeric fields
- Gold / silver / invariant separation
- Point-in-time and amendment-aware case model
- Entity-granular truth rows for transaction / holder / proposal / position / executive subjects
- DB schema, repositories, evaluator, metrics, review packets, CLI, artifacts
- Rewrite of `GOLDEN_SET.md` after code lands

### Out of scope
- Text-field LLM extraction changes
- Review UI implementation
- Scheduler / production ingestion behavior outside the golden-set commands
- Replacing current text-oriented `offline-eval`; numeric v2 should land beside it first

---

## 2. Hard rules this plan enforces

1. **Gold is independent truth only.** Allowed gold sources: `manual_adjudication`, `raw_xbrl`, `raw_xml`. `companyfacts` and `edgartools_obj` are silver only.
2. **Invariant is never truth.** Accounting identities and cross-checks are stored and reported separately; they can fail or pass, but they do not become `truth_value`.
3. **No FLOAT in new golden tables.** Numeric values use `NUMERIC(38,10)` in SQL and `Decimal` in Python. `Float` remains tolerated only in legacy extraction tables until they are migrated separately.
4. **Truth rows are entity-granular.** Every numeric fact is keyed by `case_id + subject_id + field_name + truth_tier + truth_source`.
5. **Point-in-time is mandatory.** Each case stores `accepted_at`, `is_amendment`, `amendment_no`, `truth_cutoff_at`, `source_accession_no`, and `source_observed_at`.
6. **Eligible denominators only.** Gold strict accuracy uses only rows where `truth_tier=gold` and `applicability=applicable`.
7. **Sampling must include complexity, not only clean large-cap cases.** ADR/20-F, amendment pairs, and multi-row entity cases are explicit phase gates.
8. **Artifacts must be reproducible.** Every run writes a manifest with config paths, git SHA if available, filters, and source snapshot hashes.
9. **Legacy domain knowledge must survive the rewrite.** Concrete XBRL concept candidates, derivation formulas, executable invariants, and curated seed tickers with rationale must live in versioned config and tests, not only in narrative docs.

---

## 3. Canonical numeric field inventory to freeze

This plan freezes **53 unique numeric fields**, counted by canonical field name, not by repeated form-family appearance.

### 3.1 Issuer route — filing subject (20)
- `total_revenue`
- `operating_income`
- `net_income`
- `diluted_eps`
- `cash_and_equivalents`
- `total_debt`
- `operating_cash_flow`
- `capex`
- `shares_outstanding`
- `filing_delay_days`
- `gross_proceeds`
- `net_proceeds`
- `offering_price_per_share`
- `securities_offered_qty`
- `underwriter_discount_total`
- `deal_value`
- `offer_price_per_share`
- `tender_shares_sought`
- `financing_commitment_amount`
- `termination_fee`

### 3.2 Issuer route — proposal subject (4)
- `proposal_votes_for`
- `proposal_votes_against`
- `proposal_votes_abstain`
- `proposal_broker_non_votes`

### 3.3 Issuer route — executive subject (1)
- `exec_total_comp`

### 3.4 Issuer route — holder-row subject (2)
- `holder_beneficial_ownership_shares`
- `holder_beneficial_ownership_pct`

### 3.5 Owner route — transaction-row subject (6)
- `non_derivative_shares_owned`
- `derivative_underlying_shares`
- `shares_acquired_or_disposed`
- `transaction_price_per_share`
- `shares_owned_following_txn`
- `exercise_or_conversion_price`

### 3.6 Owner route — reporting-person subject (8)
- `beneficially_owned_shares`
- `beneficial_ownership_pct`
- `sole_voting_power`
- `shared_voting_power`
- `sole_dispositive_power`
- `shared_dispositive_power`
- `aggregate_purchase_price`
- `source_of_funds_amount`

### 3.7 Owner route — Form 144 notice subject (4)
- `proposed_sale_shares`
- `proposed_sale_market_value`
- `shares_sold_past_3m`
- `market_value_sold_past_3m`

### 3.8 Holding route — holding-position subject (5)
- `position_value_usd`
- `shares_or_principal_amount`
- `sole_voting_auth_shares`
- `shared_voting_auth_shares`
- `none_voting_auth_shares`

### 3.9 Holding route — filing subject (3)
- `other_included_managers_count`
- `info_table_entry_total`
- `info_table_value_total_usd`

### 3.10 Subject-type counts that must validate in the catalog
- `(issuer, filing)` = 20
- `(issuer, proposal)` = 4
- `(issuer, executive)` = 1
- `(issuer, holder_row)` = 2
- `(owner, transaction_row)` = 6
- `(owner, reporting_person)` = 8
- `(owner, form144_notice)` = 4
- `(holding, holding_position)` = 5
- `(holding, filing)` = 3

---

## 4. Target file structure

### Create
- `configs/golden/v2/field_catalog_numeric.yaml` — canonical field inventory, subject type, form applicability, unit semantics, tolerance rules, truth-tier policy
- `configs/golden/v2/metric_thresholds.yaml` — phase gates and metric thresholds
- `configs/golden/v2/concept_registry_numeric.yaml` — concrete XBRL concept candidates, source priorities, fallback derivations, and taxonomy-specific notes
- `configs/golden/v2/invariants_numeric.yaml` — executable cross-check formulas and tolerances by validation group
- `configs/golden/v2/seed_tickers.yaml` — curated seed tickers with rationale, target forms, and the edge case each ticker is meant to cover
- `configs/golden/v2/sampling_plan.yaml` — case quotas for domestic, ADR/20-F, amendment pairs, and multi-row entity samples
- `src/db/golden_models.py` — ORM models for the new golden-set tables
- `src/pipeline/golden/contracts.py` — enums / dataclasses for case, subject, truth, candidate, run, metrics
- `src/pipeline/golden/catalog.py` — YAML loader + validation for field catalog, concept registry, invariants, seed tickers, and thresholds
- `src/pipeline/golden/loaders.py` — load case YAML/JSON into normalized case/subject/truth rows
- `src/pipeline/golden/repositories.py` — persistence helpers for golden tables
- `src/pipeline/golden/review_packets.py` — deterministic review packet builder with point-in-time metadata
- `src/pipeline/golden/metrics.py` — eligible-denominator metric functions
- `src/pipeline/golden/evaluator.py` — v2 evaluator comparing extracted candidates to gold/silver/invariant data
- `src/pipeline/golden/artifacts.py` — run manifest, summary, by-field, mismatches, coverage, review-packet emission
- `migrations/0002_golden_set_v2.sql` — raw SQL migration for the new schema
- `tests/unit/test_golden_catalog.py`
- `tests/unit/test_golden_review_packets.py`
- `tests/unit/test_golden_metrics.py`
- `tests/unit/test_golden_evaluator.py`
- `tests/integration/test_golden_schema_roundtrip.py`
- `tests/integration/test_golden_cli_eval.py`

### Modify
- `src/cli.py` — add `golden-validate-catalog`, `golden-load-v2`, `golden-eval-v2`, `golden-export-review-packets`
- `GOLDEN_SET.md` — rewrite terminology and process after implementation passes

### Leave unchanged for now
- `src/pipeline/offline_evaluator.py` — keep as the current text/Tier-2 evaluator until numeric v2 is proven
- `src/pipeline/offline_artifacts.py` — keep for legacy runs; v2 gets its own artifact writer
- `src/db/models.py` — do not overload further; add dedicated `src/db/golden_models.py`

---

## 5. Target schema and artifact contracts

### 5.1 Database tables

Use these tables in `migrations/0002_golden_set_v2.sql` and mirror them in `src/db/golden_models.py`.

```sql
CREATE TABLE golden_case (
    case_id TEXT PRIMARY KEY,
    accession_no TEXT NOT NULL,
    route TEXT NOT NULL,
    form_type TEXT NOT NULL,
    form_family TEXT NOT NULL,
    cik TEXT NOT NULL,
    ticker TEXT,
    filed_at TIMESTAMPTZ,
    accepted_at TIMESTAMPTZ NOT NULL,
    period_end DATE,
    is_amendment BOOLEAN NOT NULL,
    amendment_no INTEGER,
    truth_cutoff_at TIMESTAMPTZ NOT NULL,
    filing_sha256 TEXT NOT NULL,
    source_snapshot_kind TEXT NOT NULL,
    source_snapshot_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (accession_no, route)
);

CREATE TABLE golden_subject (
    subject_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES golden_case(case_id),
    subject_type TEXT NOT NULL,
    subject_key TEXT NOT NULL,
    parent_subject_id TEXT REFERENCES golden_subject(subject_id),
    ordinal INTEGER,
    label TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (case_id, subject_type, subject_key)
);

CREATE TABLE golden_truth (
    truth_id BIGSERIAL PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES golden_case(case_id),
    subject_id TEXT NOT NULL REFERENCES golden_subject(subject_id),
    field_name TEXT NOT NULL,
    truth_tier TEXT NOT NULL CHECK (truth_tier IN ('gold', 'silver')),
    truth_source TEXT NOT NULL,
    applicability TEXT NOT NULL CHECK (applicability IN ('applicable', 'not_applicable', 'unknown')),
    value_decimal NUMERIC(38,10),
    value_text TEXT,
    value_unit TEXT,
    currency_code TEXT,
    tolerance_basis_points INTEGER NOT NULL,
    source_locator TEXT NOT NULL,
    source_accession_no TEXT,
    source_observed_at TIMESTAMPTZ NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (case_id, subject_id, field_name, truth_tier, truth_source)
);

CREATE TABLE golden_invariant_result (
    invariant_id BIGSERIAL PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES golden_case(case_id),
    subject_id TEXT REFERENCES golden_subject(subject_id),
    invariant_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pass', 'fail', 'not_applicable')),
    lhs_value NUMERIC(38,10),
    rhs_value NUMERIC(38,10),
    tolerance_basis_points INTEGER NOT NULL,
    detail_json TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE golden_candidate (
    candidate_id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    case_id TEXT NOT NULL REFERENCES golden_case(case_id),
    subject_id TEXT REFERENCES golden_subject(subject_id),
    route TEXT NOT NULL,
    field_name TEXT NOT NULL,
    rank INTEGER NOT NULL,
    candidate_status TEXT NOT NULL CHECK (candidate_status IN ('ok', 'not_found', 'error')),
    value_decimal NUMERIC(38,10),
    value_text TEXT,
    value_unit TEXT,
    locator_kind TEXT,
    locator_path TEXT,
    source_span TEXT,
    error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE golden_eval_run (
    run_id TEXT PRIMARY KEY,
    config_path TEXT NOT NULL,
    thresholds_path TEXT NOT NULL,
    sampling_plan_path TEXT NOT NULL,
    filters_json TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE golden_eval_result (
    result_id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES golden_eval_run(run_id),
    case_id TEXT NOT NULL REFERENCES golden_case(case_id),
    subject_id TEXT REFERENCES golden_subject(subject_id),
    field_name TEXT NOT NULL,
    truth_tier TEXT NOT NULL,
    applicability TEXT NOT NULL,
    matched BOOLEAN NOT NULL,
    subject_matched BOOLEAN NOT NULL,
    expected_decimal NUMERIC(38,10),
    actual_decimal NUMERIC(38,10),
    expected_text TEXT,
    actual_text TEXT,
    metric_bucket TEXT NOT NULL,
    failure_code TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE golden_review_packet (
    packet_id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES golden_eval_run(run_id),
    case_id TEXT NOT NULL REFERENCES golden_case(case_id),
    subject_id TEXT REFERENCES golden_subject(subject_id),
    field_name TEXT NOT NULL,
    packet_path TEXT NOT NULL,
    packet_sha256 TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (run_id, case_id, subject_id, field_name)
);
```

### 5.2 Artifact directory contract

Every `golden-eval-v2` run must write:

```text
artifacts/golden/<run_id>/manifest.json
artifacts/golden/<run_id>/summary.json
artifacts/golden/<run_id>/by_field.json
artifacts/golden/<run_id>/coverage.json
artifacts/golden/<run_id>/mismatches.ndjson
artifacts/golden/<run_id>/silver_alignment.ndjson
artifacts/golden/<run_id>/invariants.ndjson
artifacts/golden/<run_id>/review_packets/<case_id>__<subject_key>__<field_name>.json
```

### 5.3 Concept registry contract

The rewrite must preserve the old document’s concrete locator knowledge in versioned config rather than prose only.

`configs/golden/v2/concept_registry_numeric.yaml` must use this shape:

```yaml
fields:
  total_revenue:
    concept_candidates:
      - taxonomy: us-gaap
        concept: RevenueFromContractWithCustomerExcludingAssessedTax
        priority: 1
        applies_to_forms: [10-K, 10-Q]
      - taxonomy: us-gaap
        concept: Revenues
        priority: 2
        applies_to_forms: [10-K, 10-Q, 20-F]
      - taxonomy: us-gaap
        concept: SalesRevenueNet
        priority: 3
        applies_to_forms: [10-K, 10-Q, S-1, 424B4]
      - taxonomy: ifrs-full
        concept: Revenue
        priority: 4
        applies_to_forms: [20-F]
    fallback_derivation:
      expression: GrossProfit + CostOfGoodsAndServicesSold
      requires:
        - us-gaap:GrossProfit
        - us-gaap:CostOfGoodsAndServicesSold
  operating_income:
    concept_candidates:
      - taxonomy: us-gaap
        concept: OperatingIncomeLoss
        priority: 1
        applies_to_forms: [10-K, 10-Q, 20-F]
  total_debt:
    concept_candidates:
      - taxonomy: us-gaap
        concept: DebtInstrumentCarryingAmount
        priority: 99
        applies_to_forms: [10-K, 10-Q, 20-F]
    fallback_derivation:
      expression: LongTermDebt + LongTermDebtCurrent + ShortTermBorrowings
      requires:
        - us-gaap:LongTermDebt
        - us-gaap:LongTermDebtCurrent
        - us-gaap:ShortTermBorrowings
```

Rules:
- Preserve the old concept candidate lists from `GOLDEN_SET.md` for every field that had them.
- Add `ifrs-full` candidates for ADR / `20-F` coverage where applicable.
- Allow `fallback_derivation` only when every required input concept is explicit.
- The evaluator must record which concept or derivation actually produced a candidate.

### 5.4 Invariant registry contract

`configs/golden/v2/invariants_numeric.yaml` must convert the old cross-check chapter into executable assertions.

```yaml
groups:
  income_statement:
    level: filing
    applies_to_fields: [total_revenue, operating_income, net_income, diluted_eps, shares_outstanding]
    invariants:
      - name: revenue_ge_operating_income
        expression: total_revenue >= operating_income
        tolerance_basis_points: 0
      - name: operating_income_ge_net_income_usually
        expression: operating_income >= net_income * 0.5
        tolerance_basis_points: 0
      - name: diluted_eps_consistency
        expression: abs(diluted_eps - net_income / shares_outstanding) / max(abs(diluted_eps), 0.01) <= 0.05
        tolerance_basis_points: 500
  balance_sheet_cashflow:
    level: filing
    applies_to_fields: [cash_and_equivalents, total_debt, operating_cash_flow, capex]
    invariants:
      - name: cash_nonnegative
        expression: cash_and_equivalents >= 0
        tolerance_basis_points: 0
      - name: debt_nonnegative
        expression: total_debt >= 0
        tolerance_basis_points: 0
  offering:
    level: filing
    applies_to_fields: [gross_proceeds, net_proceeds, offering_price_per_share, securities_offered_qty, underwriter_discount_total]
    invariants:
      - name: gross_eq_price_times_qty
        expression: abs(gross_proceeds - offering_price_per_share * securities_offered_qty) / gross_proceeds <= 0.02
        tolerance_basis_points: 200
      - name: net_eq_gross_minus_discount
        expression: abs(net_proceeds - (gross_proceeds - underwriter_discount_total)) / gross_proceeds <= 0.02
        tolerance_basis_points: 200
      - name: underwriter_discount_positive
        expression: underwriter_discount_total > 0
        tolerance_basis_points: 0
      - name: offering_price_positive
        expression: offering_price_per_share > 0
        tolerance_basis_points: 0
  section16_ownership:
    level: row
    applies_to_fields: [shares_owned_following_txn, shares_acquired_or_disposed, transaction_price_per_share]
    invariants:
      - name: post_txn_balance
        expression: shares_owned_following_txn == prior_balance + shares_acquired_or_disposed
        tolerance_basis_points: 0
      - name: price_positive_if_present
        expression: transaction_price_per_share > 0
        tolerance_basis_points: 0
  beneficial_ownership:
    level: row
    applies_to_fields: [beneficially_owned_shares, beneficial_ownership_pct, sole_voting_power, shared_voting_power, aggregate_purchase_price]
    invariants:
      - name: voting_power_covers_beneficial_shares_usually
        expression: sole_voting_power + shared_voting_power >= beneficially_owned_shares
        tolerance_basis_points: 0
      - name: ownership_pct_in_range
        expression: beneficial_ownership_pct >= 0 and beneficial_ownership_pct <= 100
        tolerance_basis_points: 0
      - name: aggregate_purchase_price_nonnegative
        expression: aggregate_purchase_price >= 0
        tolerance_basis_points: 0
  form144_sale:
    level: row
    applies_to_fields: [proposed_sale_shares, proposed_sale_market_value]
    invariants:
      - name: proposed_sale_shares_positive
        expression: proposed_sale_shares > 0
        tolerance_basis_points: 0
      - name: proposed_sale_market_value_positive
        expression: proposed_sale_market_value > 0
        tolerance_basis_points: 0
  holdings_13f:
    level: mixed
    applies_to_fields: [position_value_usd, shares_or_principal_amount, sole_voting_auth_shares, shared_voting_auth_shares, none_voting_auth_shares, info_table_entry_total, info_table_value_total_usd]
    invariants:
      - name: value_total_match
        expression: abs(sum_position_value_usd - info_table_value_total_usd) <= 1000
        tolerance_basis_points: 0
      - name: entry_count_match
        expression: position_count == info_table_entry_total
        tolerance_basis_points: 0
      - name: voting_auth_sum_equals_shares
        expression: sole_voting_auth_shares + shared_voting_auth_shares + none_voting_auth_shares == shares_or_principal_amount
        tolerance_basis_points: 0
```

Rules:
- Port the concrete invariant formulas from the old document’s cross-check section into this registry.
- Distinguish filing-level invariants from row-level invariants.
- The invariant runner must emit `pass`, `fail`, or `not_applicable` with captured lhs/rhs values.

### 5.5 Seed ticker registry contract

`configs/golden/v2/seed_tickers.yaml` must preserve the old curated seed list and rationale.

```yaml
seed_sets:
  phase_1_seed:
    - ticker: MSFT
      route_focus: [issuer]
      rationale: standard XBRL coverage and stable large-cap baseline
      edge_case: canonical us-gaap concepts
    - ticker: AAPL
      route_focus: [issuer]
      rationale: non-12/31 fiscal year
      edge_case: fiscal year alignment
    - ticker: AMZN
      route_focus: [issuer]
      rationale: very large absolute values
      edge_case: magnitude and scaling
    - ticker: NVDA
      route_focus: [issuer]
      rationale: rapid growth profile
      edge_case: z-score robustness
    - ticker: TSLA
      route_focus: [issuer, owner]
      rationale: historically irregular presentation and frequent insider activity
      edge_case: layout variance and Form 4 density
  phase_2_financials:
    - ticker: JPM
      route_focus: [issuer]
      rationale: bank income statement structure
      edge_case: interest-income-led revenue concepts
    - ticker: BAC
      route_focus: [issuer]
      rationale: bank disclosures with different revenue vocabulary
      edge_case: non-standard revenue mapping
    - ticker: GS
      route_focus: [issuer]
      rationale: investment bank structure
      edge_case: trading and fair-value presentation
```

Rules:
- Start with the old named seeds and their rationale before adding random or quota-filling names.
- Sampling-plan quotas are minimums; the seed ticker registry determines the intentional cold-start set.
- The sampling validator must assert that required named seeds are present before phase gates can pass.

### 5.6 Metric definitions

- `gold_strict_accuracy`: matched gold-applicable rows / total gold-applicable rows
- `gold_coverage`: candidate rows with status `ok` on gold-applicable rows / total gold-applicable rows
- `row_selection_accuracy`: rows where the chosen candidate hit the correct `subject_id` / total gold-applicable rows
- `not_applicable_precision`: rows predicted as absent only when truth says `not_applicable`
- `silver_alignment`: matched silver-applicable rows / total silver-applicable rows
- `invariant_pass_rate`: pass invariant rows / invariant rows where status is `pass` or `fail`

Do **not** mix these numerators or denominators.

---

## 6. Sampling and phase gates

### Phase 0 — inventory freeze
- Catalog validates with exactly 53 unique `(route, field_name)` pairs
- All fields have `subject_type`, `allowed_form_families`, `value_kind`, `default_tolerance_basis_points`, `gold_source_policy`, `silver_source_policy`

### Phase 1 — deterministic domestic seed
- Minimum `20` gold-applicable rows per deterministic field class
- Minimum `5` distinct CIKs per field
- Minimum `2` filing years per field where historical filings exist
- Required forms: `10-K`, `10-Q`, `3`, `4`, `5`, `13D`, `13G`, `144`, `13F-HR`
- Required curated seeds: `MSFT`, `AAPL`, `AMZN`, `NVDA`, `TSLA`
- Business intent: use `AAPL` to validate non-12/31 fiscal year alignment, `TSLA` to validate edge-case layouts and dense Form 4 activity, `AMZN` to validate magnitude/scaling, `NVDA` to validate fast-growth z-score behavior, and `MSFT` as a stable canonical XBRL baseline
- Gate: `gold_strict_accuracy = 1.0` and `row_selection_accuracy = 1.0` on deterministic fields

### Phase 2 — complex structure seed
- Minimum `10` ADR / `20-F` gold-applicable rows for relevant issuer fields
- Minimum `5` amendment pairs (`/A`) across issuer and owner routes
- Minimum `10` multi-row entity cases across proposal / holder / transaction / holding-position subjects
- Required curated financial seeds: `JPM`, `BAC`, `WFC`, `GS`, `MS`, `C`, `JEF`, `LAZ`
- Business intent: banks validate interest-income-led revenue mappings and non-industrial financial statement structure; broker-dealers and advisors validate trading, fair-value, and advisory-led presentation differences
- Gate: `gold_strict_accuracy >= 0.99`, `row_selection_accuracy = 1.0`, `not_applicable_precision = 1.0`

### Phase 3 — historical expansion
- Minimum `14` issuers spanning domestic + ADR / foreign issuers
- Coverage across `2014` to current year where data exists
- Gate: `gold_strict_accuracy >= 0.99`, `silver_alignment >= 0.98`, `invariant_pass_rate >= 0.99`

### Phase 4 — scale-out surveillance
- Use silver + invariants for broad monitoring
- Gold remains release gate for precision claims
- New fields do not graduate until they meet Phase 2 and Phase 3 gates

---

## 7. Task plan

### Task 1: Freeze the canonical field catalog and thresholds

**Files:**
- Create: `configs/golden/v2/field_catalog_numeric.yaml`
- Create: `configs/golden/v2/metric_thresholds.yaml`
- Create: `configs/golden/v2/concept_registry_numeric.yaml`
- Create: `configs/golden/v2/invariants_numeric.yaml`
- Create: `configs/golden/v2/seed_tickers.yaml`
- Create: `configs/golden/v2/sampling_plan.yaml`
- Test: `tests/unit/test_golden_catalog.py`

- [ ] **Step 1: Write the failing catalog test**

```python
from collections import Counter
from pathlib import Path

import yaml

EXPECTED_FIELDS = {
    ("issuer", "total_revenue"),
    ("issuer", "operating_income"),
    ("issuer", "net_income"),
    ("issuer", "diluted_eps"),
    ("issuer", "cash_and_equivalents"),
    ("issuer", "total_debt"),
    ("issuer", "operating_cash_flow"),
    ("issuer", "capex"),
    ("issuer", "shares_outstanding"),
    ("issuer", "filing_delay_days"),
    ("issuer", "gross_proceeds"),
    ("issuer", "net_proceeds"),
    ("issuer", "offering_price_per_share"),
    ("issuer", "securities_offered_qty"),
    ("issuer", "underwriter_discount_total"),
    ("issuer", "deal_value"),
    ("issuer", "offer_price_per_share"),
    ("issuer", "tender_shares_sought"),
    ("issuer", "financing_commitment_amount"),
    ("issuer", "termination_fee"),
    ("issuer", "exec_total_comp"),
    ("issuer", "holder_beneficial_ownership_shares"),
    ("issuer", "holder_beneficial_ownership_pct"),
    ("issuer", "proposal_votes_for"),
    ("issuer", "proposal_votes_against"),
    ("issuer", "proposal_votes_abstain"),
    ("issuer", "proposal_broker_non_votes"),
    ("owner", "non_derivative_shares_owned"),
    ("owner", "derivative_underlying_shares"),
    ("owner", "shares_acquired_or_disposed"),
    ("owner", "transaction_price_per_share"),
    ("owner", "shares_owned_following_txn"),
    ("owner", "exercise_or_conversion_price"),
    ("owner", "beneficially_owned_shares"),
    ("owner", "beneficial_ownership_pct"),
    ("owner", "sole_voting_power"),
    ("owner", "shared_voting_power"),
    ("owner", "sole_dispositive_power"),
    ("owner", "shared_dispositive_power"),
    ("owner", "aggregate_purchase_price"),
    ("owner", "source_of_funds_amount"),
    ("owner", "proposed_sale_shares"),
    ("owner", "proposed_sale_market_value"),
    ("owner", "shares_sold_past_3m"),
    ("owner", "market_value_sold_past_3m"),
    ("holding", "position_value_usd"),
    ("holding", "shares_or_principal_amount"),
    ("holding", "sole_voting_auth_shares"),
    ("holding", "shared_voting_auth_shares"),
    ("holding", "none_voting_auth_shares"),
    ("holding", "other_included_managers_count"),
    ("holding", "info_table_entry_total"),
    ("holding", "info_table_value_total_usd"),
}

EXPECTED_SUBJECT_COUNTS = {
    ("issuer", "filing"): 20,
    ("issuer", "proposal"): 4,
    ("issuer", "executive"): 1,
    ("issuer", "holder_row"): 2,
    ("owner", "transaction_row"): 6,
    ("owner", "reporting_person"): 8,
    ("owner", "form144_notice"): 4,
    ("holding", "holding_position"): 5,
    ("holding", "filing"): 3,
}


def test_field_catalog_freezes_canonical_numeric_inventory() -> None:
    payload = yaml.safe_load(Path("configs/golden/v2/field_catalog_numeric.yaml").read_text())
    rows = payload["fields"]
    keys = {(row["route"], row["field_name"]) for row in rows}
    assert keys == EXPECTED_FIELDS
    assert len(keys) == 53

    counts = Counter((row["route"], row["subject_type"]) for row in rows)
    assert dict(counts) == EXPECTED_SUBJECT_COUNTS


def test_thresholds_keep_gold_silver_and_invariant_separate() -> None:
    payload = yaml.safe_load(Path("configs/golden/v2/metric_thresholds.yaml").read_text())
    metrics = payload["metrics"]
    assert set(metrics) == {
        "gold_strict_accuracy",
        "gold_coverage",
        "row_selection_accuracy",
        "not_applicable_precision",
        "silver_alignment",
        "invariant_pass_rate",
    }


def test_concept_registry_preserves_explicit_locator_knowledge() -> None:
    payload = yaml.safe_load(Path("configs/golden/v2/concept_registry_numeric.yaml").read_text())
    fields = payload["fields"]

    total_revenue = fields["total_revenue"]
    revenue_concepts = {
        f"{row['taxonomy']}:{row['concept']}"
        for row in total_revenue["concept_candidates"]
    }
    assert "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax" in revenue_concepts
    assert "us-gaap:Revenues" in revenue_concepts
    assert "us-gaap:SalesRevenueNet" in revenue_concepts
    assert "ifrs-full:Revenue" in revenue_concepts
    assert total_revenue["fallback_derivation"]["expression"] == "GrossProfit + CostOfGoodsAndServicesSold"

    total_debt = fields["total_debt"]
    assert total_debt["fallback_derivation"]["requires"] == [
        "us-gaap:LongTermDebt",
        "us-gaap:LongTermDebtCurrent",
        "us-gaap:ShortTermBorrowings",
    ]


def test_invariant_registry_ports_old_cross_checks() -> None:
    payload = yaml.safe_load(Path("configs/golden/v2/invariants_numeric.yaml").read_text())
    groups = payload["groups"]
    income_names = {row["name"] for row in groups["income_statement"]["invariants"]}
    offering_names = {row["name"] for row in groups["offering"]["invariants"]}
    ownership_names = {row["name"] for row in groups["section16_ownership"]["invariants"]}
    holdings_names = {row["name"] for row in groups["holdings_13f"]["invariants"]}
    assert "revenue_ge_operating_income" in income_names
    assert "diluted_eps_consistency" in income_names
    assert "gross_eq_price_times_qty" in offering_names
    assert "net_eq_gross_minus_discount" in offering_names
    assert "post_txn_balance" in ownership_names
    assert "voting_auth_sum_equals_shares" in holdings_names


def test_seed_tickers_preserve_curated_business_rationale() -> None:
    payload = yaml.safe_load(Path("configs/golden/v2/seed_tickers.yaml").read_text())
    phase_1 = {row["ticker"]: row for row in payload["seed_sets"]["phase_1_seed"]}
    phase_2 = {row["ticker"]: row for row in payload["seed_sets"]["phase_2_financials"]}
    assert phase_1["AAPL"]["edge_case"] == "fiscal year alignment"
    assert phase_1["TSLA"]["route_focus"] == ["issuer", "owner"]
    assert phase_2["JPM"]["edge_case"] == "interest-income-led revenue concepts"
```

- [ ] **Step 2: Run the catalog test and verify it fails**

Run: `pytest tests/unit/test_golden_catalog.py -q`
Expected: FAIL with `FileNotFoundError` for `configs/golden/v2/field_catalog_numeric.yaml`

- [ ] **Step 3: Create the catalog, thresholds, and sampling YAML files**

Use this exact schema and populate **all 53 rows** from Section 3 of this plan. Do not stop at the examples below.

```yaml
# configs/golden/v2/field_catalog_numeric.yaml
fields:
  - route: issuer
    field_name: total_revenue
    subject_type: filing
    allowed_form_families: [10-K, 10-Q, 20-F, S-1, 424B4]
    value_kind: money
    default_tolerance_basis_points: 1
    gold_source_policy: [manual_adjudication, raw_xbrl]
    silver_source_policy: [companyfacts]
  - route: issuer
    field_name: proposal_votes_for
    subject_type: proposal
    allowed_form_families: [8-K]
    value_kind: integer_count
    default_tolerance_basis_points: 0
    gold_source_policy: [manual_adjudication, raw_html_table]
    silver_source_policy: []
  - route: owner
    field_name: transaction_price_per_share
    subject_type: transaction_row
    allowed_form_families: [4, 5]
    value_kind: price_per_share
    default_tolerance_basis_points: 1
    gold_source_policy: [raw_xml]
    silver_source_policy: [edgartools_obj]
  - route: holding
    field_name: position_value_usd
    subject_type: holding_position
    allowed_form_families: [13F-HR]
    value_kind: money
    default_tolerance_basis_points: 1
    gold_source_policy: [raw_xml]
    silver_source_policy: [edgartools_obj]
```

Also add these validation rules to `tests/unit/test_golden_catalog.py` so the catalog cannot silently drift:

```python
def test_every_catalog_row_has_required_keys() -> None:
    payload = yaml.safe_load(Path("configs/golden/v2/field_catalog_numeric.yaml").read_text())
    for row in payload["fields"]:
        assert set(row) == {
            "route",
            "field_name",
            "subject_type",
            "allowed_form_families",
            "value_kind",
            "default_tolerance_basis_points",
            "gold_source_policy",
            "silver_source_policy",
        }
        assert row["route"] in {"issuer", "owner", "holding"}
        assert isinstance(row["allowed_form_families"], list) and row["allowed_form_families"]
        assert isinstance(row["gold_source_policy"], list)
        assert isinstance(row["silver_source_policy"], list)
```

```yaml
# configs/golden/v2/metric_thresholds.yaml
metrics:
  gold_strict_accuracy:
    phase_1_seed: 1.0
    phase_2_complex: 0.99
    phase_3_history: 0.99
  gold_coverage:
    phase_1_seed: 0.95
    phase_2_complex: 0.95
    phase_3_history: 0.97
  row_selection_accuracy:
    phase_1_seed: 1.0
    phase_2_complex: 1.0
    phase_3_history: 0.995
  not_applicable_precision:
    phase_1_seed: 1.0
    phase_2_complex: 1.0
    phase_3_history: 0.995
  silver_alignment:
    phase_2_complex: 0.98
    phase_3_history: 0.98
  invariant_pass_rate:
    phase_2_complex: 0.99
    phase_3_history: 0.99
```

```yaml
# configs/golden/v2/concept_registry_numeric.yaml
fields:
  total_revenue:
    concept_candidates:
      - taxonomy: us-gaap
        concept: RevenueFromContractWithCustomerExcludingAssessedTax
        priority: 1
        applies_to_forms: [10-K, 10-Q]
      - taxonomy: us-gaap
        concept: Revenues
        priority: 2
        applies_to_forms: [10-K, 10-Q, 20-F]
      - taxonomy: us-gaap
        concept: SalesRevenueNet
        priority: 3
        applies_to_forms: [10-K, 10-Q, S-1, 424B4]
      - taxonomy: us-gaap
        concept: RevenueFromContractWithCustomerIncludingAssessedTax
        priority: 4
        applies_to_forms: [10-K, 10-Q]
      - taxonomy: us-gaap
        concept: InterestAndDividendIncomeOperating
        priority: 5
        applies_to_forms: [10-K, 10-Q]
      - taxonomy: ifrs-full
        concept: Revenue
        priority: 6
        applies_to_forms: [20-F]
    fallback_derivation:
      expression: GrossProfit + CostOfGoodsAndServicesSold
      requires:
        - us-gaap:GrossProfit
        - us-gaap:CostOfGoodsAndServicesSold
  operating_income:
    concept_candidates:
      - taxonomy: us-gaap
        concept: OperatingIncomeLoss
        priority: 1
        applies_to_forms: [10-K, 10-Q, 20-F]
      - taxonomy: us-gaap
        concept: IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest
        priority: 2
        applies_to_forms: [10-K, 10-Q]
  net_income:
    concept_candidates:
      - taxonomy: us-gaap
        concept: NetIncomeLoss
        priority: 1
        applies_to_forms: [10-K, 10-Q, 20-F]
      - taxonomy: us-gaap
        concept: ProfitLoss
        priority: 2
        applies_to_forms: [10-K, 10-Q, 20-F]
      - taxonomy: ifrs-full
        concept: ProfitLoss
        priority: 3
        applies_to_forms: [20-F]
  diluted_eps:
    concept_candidates:
      - taxonomy: us-gaap
        concept: EarningsPerShareDiluted
        priority: 1
        applies_to_forms: [10-K, 10-Q, 20-F]
      - taxonomy: ifrs-full
        concept: BasicAndDilutedEarningsLossPerShare
        priority: 2
        applies_to_forms: [20-F]
  shares_outstanding:
    concept_candidates:
      - taxonomy: dei
        concept: EntityCommonStockSharesOutstanding
        priority: 1
        applies_to_forms: [10-K, 10-Q, 20-F]
      - taxonomy: us-gaap
        concept: CommonStockSharesOutstanding
        priority: 2
        applies_to_forms: [10-K, 10-Q]
      - taxonomy: ifrs-full
        concept: NumberOfSharesOutstanding
        priority: 3
        applies_to_forms: [20-F]
  cash_and_equivalents:
    concept_candidates:
      - taxonomy: us-gaap
        concept: CashAndCashEquivalentsAtCarryingValue
        priority: 1
        applies_to_forms: [10-K, 10-Q, 20-F]
      - taxonomy: us-gaap
        concept: CashCashEquivalentsAndShortTermInvestments
        priority: 2
        applies_to_forms: [10-K, 10-Q]
      - taxonomy: ifrs-full
        concept: CashAndCashEquivalents
        priority: 3
        applies_to_forms: [20-F]
  total_debt:
    concept_candidates:
      - taxonomy: us-gaap
        concept: DebtInstrumentCarryingAmount
        priority: 99
        applies_to_forms: [10-K, 10-Q, 20-F]
    fallback_derivation:
      expression: LongTermDebt + LongTermDebtCurrent + ShortTermBorrowings
      requires:
        - us-gaap:LongTermDebt
        - us-gaap:LongTermDebtCurrent
        - us-gaap:ShortTermBorrowings
  operating_cash_flow:
    concept_candidates:
      - taxonomy: us-gaap
        concept: NetCashProvidedByUsedInOperatingActivities
        priority: 1
        applies_to_forms: [10-K, 10-Q, 20-F]
      - taxonomy: ifrs-full
        concept: CashFlowsFromUsedInOperatingActivities
        priority: 2
        applies_to_forms: [20-F]
  capex:
    concept_candidates:
      - taxonomy: us-gaap
        concept: PaymentsToAcquirePropertyPlantAndEquipment
        priority: 1
        applies_to_forms: [10-K, 10-Q, 20-F]
      - taxonomy: us-gaap
        concept: CapitalExpenditureDiscontinuedOperations
        priority: 2
        applies_to_forms: [10-K, 10-Q]
      - taxonomy: ifrs-full
        concept: PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities
        priority: 3
        applies_to_forms: [20-F]
```

```yaml
# configs/golden/v2/invariants_numeric.yaml
groups:
  income_statement:
    applies_to_fields: [total_revenue, operating_income, net_income, diluted_eps, shares_outstanding]
    invariants:
      - name: revenue_ge_operating_income
        expression: total_revenue >= operating_income
        tolerance_basis_points: 0
      - name: operating_income_ge_net_income_usually
        expression: operating_income >= net_income * 0.5
        tolerance_basis_points: 0
      - name: diluted_eps_consistency
        expression: abs(diluted_eps - net_income / shares_outstanding) / max(abs(diluted_eps), 0.01) <= 0.05
        tolerance_basis_points: 500
  offering:
    applies_to_fields: [gross_proceeds, net_proceeds, offering_price_per_share, securities_offered_qty, underwriter_discount_total]
    invariants:
      - name: gross_eq_price_times_qty
        expression: abs(gross_proceeds - offering_price_per_share * securities_offered_qty) / gross_proceeds <= 0.02
        tolerance_basis_points: 200
      - name: net_eq_gross_minus_discount
        expression: abs(net_proceeds - (gross_proceeds - underwriter_discount_total)) / gross_proceeds <= 0.02
        tolerance_basis_points: 200
  holdings_13f:
    applies_to_fields: [position_value_usd, shares_or_principal_amount, sole_voting_auth_shares, shared_voting_auth_shares, none_voting_auth_shares, info_table_entry_total, info_table_value_total_usd]
    invariants:
      - name: value_total_match
        expression: abs(sum_position_value_usd - info_table_value_total_usd) <= 1000
        tolerance_basis_points: 0
      - name: entry_count_match
        expression: position_count == info_table_entry_total
        tolerance_basis_points: 0
      - name: voting_auth_sum_equals_shares
        expression: sole_voting_auth_shares + shared_voting_auth_shares + none_voting_auth_shares == shares_or_principal_amount
        tolerance_basis_points: 0
```

```yaml
# configs/golden/v2/seed_tickers.yaml
seed_sets:
  phase_1_seed:
    - ticker: MSFT
      route_focus: [issuer]
      rationale: standard XBRL coverage and stable large-cap baseline
      edge_case: canonical us-gaap concepts
    - ticker: AAPL
      route_focus: [issuer]
      rationale: non-12/31 fiscal year
      edge_case: fiscal year alignment
    - ticker: AMZN
      route_focus: [issuer]
      rationale: very large absolute values
      edge_case: magnitude and scaling
    - ticker: NVDA
      route_focus: [issuer]
      rationale: rapid growth profile
      edge_case: z-score robustness
    - ticker: TSLA
      route_focus: [issuer, owner]
      rationale: historically irregular presentation and frequent insider activity
      edge_case: layout variance and Form 4 density
  phase_2_financials:
    - ticker: JPM
      route_focus: [issuer]
      rationale: bank income statement structure
      edge_case: interest-income-led revenue concepts
    - ticker: BAC
      route_focus: [issuer]
      rationale: bank disclosures with different revenue vocabulary
      edge_case: non-standard revenue mapping
    - ticker: WFC
      route_focus: [issuer]
      rationale: additional bank structure coverage
      edge_case: balance sheet and income classification drift
    - ticker: GS
      route_focus: [issuer]
      rationale: investment bank structure
      edge_case: trading and fair-value presentation
    - ticker: MS
      route_focus: [issuer]
      rationale: second investment-bank sample
      edge_case: broker-dealer revenue presentation
    - ticker: C
      route_focus: [issuer]
      rationale: restructuring-heavy history
      edge_case: historical concept continuity
    - ticker: JEF
      route_focus: [issuer]
      rationale: mid-cap broker-dealer sample
      edge_case: non-bank financial presentation
    - ticker: LAZ
      route_focus: [issuer]
      rationale: advisory-focused financial sample
      edge_case: low-complexity financial revenue pattern
```

```yaml
# configs/golden/v2/sampling_plan.yaml
phases:
  - phase_id: phase_1_seed
    min_gold_rows_per_field: 20
    min_distinct_cik_per_field: 5
    min_distinct_filing_years_per_field: 2
    required_form_families: [10-K, 10-Q, 3, 4, 5, 13D, 13G, 144, 13F-HR]
    required_seed_sets: [phase_1_seed]
    min_adr_20f_rows: 0
    min_amendment_pairs: 0
    min_multi_row_cases: 0
  - phase_id: phase_2_complex
    min_gold_rows_per_field: 30
    min_distinct_cik_per_field: 8
    min_distinct_filing_years_per_field: 3
    required_form_families: [10-K, 10-Q, 20-F, 8-K, 3, 4, 5, 13D, 13G, 144, 13F-HR, SC TO-I, SC 13E3]
    required_seed_sets: [phase_1_seed, phase_2_financials]
    min_adr_20f_rows: 10
    min_amendment_pairs: 5
    min_multi_row_cases: 10
  - phase_id: phase_3_history
    min_gold_rows_per_field: 50
    min_distinct_cik_per_field: 14
    min_distinct_filing_years_per_field: 5
    required_form_families: [10-K, 10-Q, 20-F, 8-K, 3, 4, 5, 13D, 13G, 144, 13F-HR, SC TO-I, SC 13E3, DEF 14A, S-1, 424B4]
    required_seed_sets: [phase_1_seed, phase_2_financials]
    min_adr_20f_rows: 10
    min_amendment_pairs: 5
    min_multi_row_cases: 20
```

- [ ] **Step 4: Run the catalog test and verify it passes**

Run: `pytest tests/unit/test_golden_catalog.py -q`
Expected: PASS

- [ ] **Step 5: Commit the catalog freeze**

```bash
git add configs/golden/v2/field_catalog_numeric.yaml configs/golden/v2/metric_thresholds.yaml configs/golden/v2/concept_registry_numeric.yaml configs/golden/v2/invariants_numeric.yaml configs/golden/v2/seed_tickers.yaml configs/golden/v2/sampling_plan.yaml tests/unit/test_golden_catalog.py
git commit -m "feat: freeze strict golden set domain registries"
```

### Task 2: Add normalized golden-set tables and persistence layer

**Files:**
- Create: `src/db/golden_models.py`
- Create: `src/pipeline/golden/repositories.py`
- Create: `migrations/0002_golden_set_v2.sql`
- Test: `tests/integration/test_golden_schema_roundtrip.py`

- [ ] **Step 1: Write the failing schema round-trip test**

```python
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.db.base import Base
from src.db.golden_models import GoldenCase, GoldenEvalResult, GoldenEvalRun, GoldenSubject, GoldenTruth


def test_golden_schema_round_trip() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    now = datetime(2026, 4, 8, tzinfo=timezone.utc)

    with Session(engine) as session:
        session.add(
            GoldenCase(
                case_id="issuer|0000320193|10-Q|2025-12-28",
                accession_no="0000320193-26-000001",
                route="issuer",
                form_type="10-Q",
                form_family="10-Q",
                cik="0000320193",
                ticker="AAPL",
                filed_at=now,
                accepted_at=now,
                period_end=now.date(),
                is_amendment=False,
                amendment_no=None,
                truth_cutoff_at=now,
                filing_sha256="abc123",
                source_snapshot_kind="sec_filing_snapshot",
                source_snapshot_path="snapshots/aapl-10q.html",
                created_at=now,
            )
        )
        session.add(
            GoldenSubject(
                subject_id="issuer|0000320193|10-Q|2025-12-28|filing",
                case_id="issuer|0000320193|10-Q|2025-12-28",
                subject_type="filing",
                subject_key="filing",
                parent_subject_id=None,
                ordinal=1,
                label="filing",
                created_at=now,
            )
        )
        session.add(
            GoldenTruth(
                case_id="issuer|0000320193|10-Q|2025-12-28",
                subject_id="issuer|0000320193|10-Q|2025-12-28|filing",
                field_name="total_revenue",
                truth_tier="gold",
                truth_source="raw_xbrl",
                applicability="applicable",
                value_decimal=Decimal("123456789.12"),
                value_text=None,
                value_unit="USD",
                currency_code="USD",
                tolerance_basis_points=1,
                source_locator="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                source_accession_no="0000320193-26-000001",
                source_observed_at=now,
                notes=None,
                created_at=now,
            )
        )
        session.add(
            GoldenEvalRun(
                run_id="run_001",
                config_path="configs/golden/v2/field_catalog_numeric.yaml",
                thresholds_path="configs/golden/v2/metric_thresholds.yaml",
                sampling_plan_path="configs/golden/v2/sampling_plan.yaml",
                filters_json="{}",
                manifest_json="{}",
                created_at=now,
            )
        )
        session.add(
            GoldenEvalResult(
                run_id="run_001",
                case_id="issuer|0000320193|10-Q|2025-12-28",
                subject_id="issuer|0000320193|10-Q|2025-12-28|filing",
                field_name="total_revenue",
                truth_tier="gold",
                applicability="applicable",
                matched=True,
                subject_matched=True,
                expected_decimal=Decimal("123456789.12"),
                actual_decimal=Decimal("123456789.12"),
                expected_text=None,
                actual_text=None,
                metric_bucket="gold_strict_accuracy",
                failure_code=None,
                created_at=now,
            )
        )
        session.commit()

        persisted = session.query(GoldenTruth).one()
        assert persisted.value_decimal == Decimal("123456789.12")
```

- [ ] **Step 2: Run the schema round-trip test and verify it fails**

Run: `pytest tests/integration/test_golden_schema_roundtrip.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.db.golden_models'`

- [ ] **Step 3: Create the migration, ORM models, and repository wrappers**

Implement the ORM and repository layer with concrete, one-to-one mappings to the SQL schema in Section 5.1.

```python
# src/db/golden_models.py
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class GoldenCase(Base):
    __tablename__ = "golden_case"

    case_id: Mapped[str] = mapped_column(Text, primary_key=True)
    accession_no: Mapped[str] = mapped_column(Text, nullable=False)
    route: Mapped[str] = mapped_column(Text, nullable=False)
    form_type: Mapped[str] = mapped_column(Text, nullable=False)
    form_family: Mapped[str] = mapped_column(Text, nullable=False)
    cik: Mapped[str] = mapped_column(Text, nullable=False)
    ticker: Mapped[str | None] = mapped_column(Text, nullable=True)
    filed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_amendment: Mapped[bool] = mapped_column(Boolean, nullable=False)
    amendment_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    truth_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    filing_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    source_snapshot_kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_snapshot_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GoldenSubject(Base):
    __tablename__ = "golden_subject"

    subject_id: Mapped[str] = mapped_column(Text, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("golden_case.case_id"), nullable=False)
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_key: Mapped[str] = mapped_column(Text, nullable=False)
    parent_subject_id: Mapped[str | None] = mapped_column(ForeignKey("golden_subject.subject_id"), nullable=True)
    ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GoldenTruth(Base):
    __tablename__ = "golden_truth"

    truth_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("golden_case.case_id"), nullable=False)
    subject_id: Mapped[str] = mapped_column(ForeignKey("golden_subject.subject_id"), nullable=False)
    field_name: Mapped[str] = mapped_column(Text, nullable=False)
    truth_tier: Mapped[str] = mapped_column(Text, nullable=False)
    truth_source: Mapped[str] = mapped_column(Text, nullable=False)
    applicability: Mapped[str] = mapped_column(Text, nullable=False)
    value_decimal: Mapped[Decimal | None] = mapped_column(Numeric(38, 10), nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    tolerance_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    source_locator: Mapped[str] = mapped_column(Text, nullable=False)
    source_accession_no: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GoldenInvariantResult(Base):
    __tablename__ = "golden_invariant_result"

    invariant_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("golden_case.case_id"), nullable=False)
    subject_id: Mapped[str | None] = mapped_column(ForeignKey("golden_subject.subject_id"), nullable=True)
    invariant_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    lhs_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 10), nullable=True)
    rhs_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 10), nullable=True)
    tolerance_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    detail_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GoldenCandidate(Base):
    __tablename__ = "golden_candidate"

    candidate_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(Text, nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("golden_case.case_id"), nullable=False)
    subject_id: Mapped[str | None] = mapped_column(ForeignKey("golden_subject.subject_id"), nullable=True)
    route: Mapped[str] = mapped_column(Text, nullable=False)
    field_name: Mapped[str] = mapped_column(Text, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_status: Mapped[str] = mapped_column(Text, nullable=False)
    value_decimal: Mapped[Decimal | None] = mapped_column(Numeric(38, 10), nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    locator_kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    locator_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_span: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GoldenEvalRun(Base):
    __tablename__ = "golden_eval_run"

    run_id: Mapped[str] = mapped_column(Text, primary_key=True)
    config_path: Mapped[str] = mapped_column(Text, nullable=False)
    thresholds_path: Mapped[str] = mapped_column(Text, nullable=False)
    sampling_plan_path: Mapped[str] = mapped_column(Text, nullable=False)
    filters_json: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GoldenEvalResult(Base):
    __tablename__ = "golden_eval_result"

    result_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("golden_eval_run.run_id"), nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("golden_case.case_id"), nullable=False)
    subject_id: Mapped[str | None] = mapped_column(ForeignKey("golden_subject.subject_id"), nullable=True)
    field_name: Mapped[str] = mapped_column(Text, nullable=False)
    truth_tier: Mapped[str] = mapped_column(Text, nullable=False)
    applicability: Mapped[str] = mapped_column(Text, nullable=False)
    matched: Mapped[bool] = mapped_column(Boolean, nullable=False)
    subject_matched: Mapped[bool] = mapped_column(Boolean, nullable=False)
    expected_decimal: Mapped[Decimal | None] = mapped_column(Numeric(38, 10), nullable=True)
    actual_decimal: Mapped[Decimal | None] = mapped_column(Numeric(38, 10), nullable=True)
    expected_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    metric_bucket: Mapped[str] = mapped_column(Text, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GoldenReviewPacket(Base):
    __tablename__ = "golden_review_packet"

    packet_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("golden_eval_run.run_id"), nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("golden_case.case_id"), nullable=False)
    subject_id: Mapped[str | None] = mapped_column(ForeignKey("golden_subject.subject_id"), nullable=True)
    field_name: Mapped[str] = mapped_column(Text, nullable=False)
    packet_path: Mapped[str] = mapped_column(Text, nullable=False)
    packet_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

```python
# src/pipeline/golden/repositories.py
from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.db.golden_models import GoldenCandidate, GoldenCase, GoldenEvalResult, GoldenEvalRun, GoldenInvariantResult, GoldenReviewPacket, GoldenSubject, GoldenTruth
from src.pipeline.golden.contracts import GoldenCandidateRow, GoldenCaseRow, GoldenEvalResultRow, GoldenEvalRunRow, GoldenInvariantRow, GoldenReviewPacketRow, GoldenSubjectRow, GoldenTruthRow


class GoldenRepository:
    def __init__(self, session: Session):
        self.session = session

    def upsert_case(self, row: GoldenCaseRow) -> None:
        self.session.merge(GoldenCase(**row.as_db_dict()))

    def upsert_subject(self, row: GoldenSubjectRow) -> None:
        self.session.merge(GoldenSubject(**row.as_db_dict()))

    def insert_truth_rows(self, rows: Sequence[GoldenTruthRow]) -> None:
        self.session.add_all(GoldenTruth(**row.as_db_dict()) for row in rows)

    def insert_invariant_rows(self, rows: Sequence[GoldenInvariantRow]) -> None:
        self.session.add_all(GoldenInvariantResult(**row.as_db_dict()) for row in rows)

    def create_eval_run(self, row: GoldenEvalRunRow) -> None:
        self.session.add(GoldenEvalRun(**row.as_db_dict()))

    def insert_candidates(self, rows: Sequence[GoldenCandidateRow]) -> None:
        self.session.add_all(GoldenCandidate(**row.as_db_dict()) for row in rows)

    def insert_eval_results(self, rows: Sequence[GoldenEvalResultRow]) -> None:
        self.session.add_all(GoldenEvalResult(**row.as_db_dict()) for row in rows)

    def insert_review_packets(self, rows: Sequence[GoldenReviewPacketRow]) -> None:
        self.session.add_all(GoldenReviewPacket(**row.as_db_dict()) for row in rows)

    def commit(self) -> None:
        self.session.commit()
```

Use the SQL DDL from Section 5.1 directly in `migrations/0002_golden_set_v2.sql`, and keep the column names in the SQL and ORM classes identical.

- [ ] **Step 4: Run the schema round-trip test and verify it passes**

Run: `pytest tests/integration/test_golden_schema_roundtrip.py -q`
Expected: PASS

- [ ] **Step 5: Smoke-test the raw SQL migration against PostgreSQL**

Run: `psql "$PG_DSN" -f migrations/0002_golden_set_v2.sql`
Expected: each `CREATE TABLE` succeeds without syntax errors

- [ ] **Step 6: Commit the schema layer**

```bash
git add src/db/golden_models.py src/pipeline/golden/repositories.py migrations/0002_golden_set_v2.sql tests/integration/test_golden_schema_roundtrip.py
git commit -m "feat: add strict golden set schema"
```

### Task 2.5: Wire domain registries into the loader and evaluator

**Files:**
- Modify: `src/pipeline/golden/catalog.py`
- Modify: `src/pipeline/golden/loaders.py`
- Modify: `src/pipeline/golden/evaluator.py`
- Test: `tests/unit/test_golden_catalog.py`
- Test: `tests/unit/test_golden_evaluator.py`

- [ ] **Step 1: Add a failing evaluator test for concept-registry-backed derivation**

```python
from decimal import Decimal

from src.pipeline.golden.evaluator import resolve_truth_candidate


def test_resolve_truth_candidate_prefers_explicit_concept_before_derivation() -> None:
    registry = {
        "total_revenue": {
            "concept_candidates": [
                {"taxonomy": "us-gaap", "concept": "RevenueFromContractWithCustomerExcludingAssessedTax", "priority": 1},
                {"taxonomy": "us-gaap", "concept": "Revenues", "priority": 2},
            ],
            "fallback_derivation": {
                "expression": "GrossProfit + CostOfGoodsAndServicesSold",
                "requires": ["us-gaap:GrossProfit", "us-gaap:CostOfGoodsAndServicesSold"],
            },
        }
    }
    facts = {
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax": Decimal("100"),
        "us-gaap:GrossProfit": Decimal("40"),
        "us-gaap:CostOfGoodsAndServicesSold": Decimal("60"),
    }

    resolved = resolve_truth_candidate(field_name="total_revenue", registry=registry, facts=facts)

    assert resolved["source_kind"] == "concept"
    assert resolved["source_locator"] == "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
    assert resolved["value_decimal"] == Decimal("100")
```

- [ ] **Step 2: Add a failing evaluator test for executable invariants**

```python
from decimal import Decimal

from src.pipeline.golden.evaluator import run_invariant_group


def test_run_invariant_group_executes_old_offering_formula() -> None:
    invariant_group = {
        "invariants": [
            {
                "name": "net_eq_gross_minus_discount",
                "expression": "abs(net_proceeds - (gross_proceeds - underwriter_discount_total)) / gross_proceeds <= 0.02",
                "tolerance_basis_points": 200,
            }
        ]
    }
    values = {
        "gross_proceeds": Decimal("1000"),
        "net_proceeds": Decimal("930"),
        "underwriter_discount_total": Decimal("70"),
    }

    rows = run_invariant_group(group_name="offering", group_config=invariant_group, values=values)

    assert rows[0].status == "pass"
    assert rows[0].invariant_name == "net_eq_gross_minus_discount"
```

- [ ] **Step 3: Run the focused tests and verify they fail**

Run: `pytest tests/unit/test_golden_catalog.py tests/unit/test_golden_evaluator.py -q`
Expected: FAIL because the catalog loader does not yet expose concept / invariant / seed registries and evaluator helpers do not exist

- [ ] **Step 4: Extend the catalog bundle and evaluator to load and use domain registries**

Implement these exact responsibilities:

```python
# src/pipeline/golden/catalog.py
@dataclass(frozen=True)
class CatalogBundle:
    fields: tuple[dict[str, object], ...]
    field_map: dict[tuple[str, str], dict[str, object]]
    metric_thresholds: dict[str, object]
    concept_registry: dict[str, object]
    invariant_registry: dict[str, object]
    seed_tickers: dict[str, object]
    sampling_plan: dict[str, object]
```

```python
# src/pipeline/golden/evaluator.py

def resolve_truth_candidate(*, field_name: str, registry: dict[str, object], facts: dict[str, Decimal]) -> dict[str, object]:
    ...


def run_invariant_group(*, group_name: str, group_config: dict[str, object], values: dict[str, Decimal]) -> list[GoldenInvariantRow]:
    ...
```

Rules:
- `resolve_truth_candidate()` must sort concept candidates by ascending `priority` and use derivation only if no explicit concept is present.
- The returned locator must be fully qualified, e.g. `us-gaap:Revenues`.
- `run_invariant_group()` must evaluate the concrete formula strings from `configs/golden/v2/invariants_numeric.yaml` and emit `GoldenInvariantRow` outputs.
- `load_catalog_bundle()` must validate that every `required_seed_sets` entry in `sampling_plan.yaml` exists in `seed_tickers.yaml`.

- [ ] **Step 5: Run the focused tests and verify they pass**

Run: `pytest tests/unit/test_golden_catalog.py tests/unit/test_golden_evaluator.py -q`
Expected: PASS

- [ ] **Step 6: Commit the domain-registry wiring**

```bash
git add src/pipeline/golden/catalog.py src/pipeline/golden/loaders.py src/pipeline/golden/evaluator.py tests/unit/test_golden_catalog.py tests/unit/test_golden_evaluator.py
git commit -m "feat: wire golden domain registries into evaluation"
```

### Task 3: Build point-in-time case loading and review packet generation

**Files:**
- Create: `src/pipeline/golden/contracts.py`
- Create: `src/pipeline/golden/catalog.py`
- Create: `src/pipeline/golden/loaders.py`
- Create: `src/pipeline/golden/review_packets.py`
- Test: `tests/unit/test_golden_review_packets.py`

- [ ] **Step 1: Write the failing review-packet and loader test**

```python
from datetime import datetime, timezone
from decimal import Decimal

from src.pipeline.golden.contracts import Applicability, GoldenCandidateRow, GoldenCaseRow, GoldenSubjectRow, GoldenTruthRow, TruthTier
from src.pipeline.golden.review_packets import build_review_packet


def test_review_packet_keeps_subject_identity_and_point_in_time() -> None:
    now = datetime(2026, 4, 8, tzinfo=timezone.utc)
    case = GoldenCaseRow(
        case_id="owner|0000899243|4|2026-03-31",
        accession_no="0000899243-26-000005",
        route="owner",
        form_type="4/A",
        form_family="4",
        cik="0000899243",
        ticker="TSLA",
        accepted_at=now,
        period_end=None,
        is_amendment=True,
        amendment_no=1,
        truth_cutoff_at=now,
    )
    subject = GoldenSubjectRow(
        subject_id="owner|0000899243|4|2026-03-31|txn:2",
        case_id=case.case_id,
        subject_type="transaction_row",
        subject_key="txn:2",
        ordinal=2,
        label="Common Stock purchase",
    )
    truth = GoldenTruthRow(
        case_id=case.case_id,
        subject_id=subject.subject_id,
        field_name="transaction_price_per_share",
        truth_tier=TruthTier.GOLD,
        truth_source="raw_xml",
        applicability=Applicability.APPLICABLE,
        value_decimal=Decimal("183.42"),
        value_text=None,
        value_unit="USD/share",
        source_locator="/ownershipDocument/nonDerivativeTable/nonDerivativeTransaction[2]/transactionPricePerShare/value",
        source_accession_no=case.accession_no,
        source_observed_at=now,
    )
    candidate = GoldenCandidateRow(
        run_id="run_001",
        case_id=case.case_id,
        subject_id=subject.subject_id,
        route="owner",
        field_name="transaction_price_per_share",
        rank=1,
        candidate_status="ok",
        value_decimal=Decimal("183.42"),
        value_text=None,
        value_unit="USD/share",
        locator_kind="xml_path",
        locator_path=truth.source_locator,
        source_span="183.42",
        error_code=None,
    )

    packet = build_review_packet(case=case, subject=subject, truth_rows=[truth], candidate_rows=[candidate])

    assert packet["case"]["is_amendment"] is True
    assert packet["case"]["accession_no"] == "0000899243-26-000005"
    assert packet["subject"]["subject_key"] == "txn:2"
    assert packet["truth"][0]["truth_tier"] == "gold"
    assert packet["candidates"][0]["locator_kind"] == "xml_path"
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `pytest tests/unit/test_golden_review_packets.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.pipeline.golden.contracts'`

- [ ] **Step 3: Create contracts, catalog loader, case loader, and review packet builder**

Use `Decimal` and enums, not `float`.

```python
# src/pipeline/golden/contracts.py
from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from enum import StrEnum


class TruthTier(StrEnum):
    GOLD = "gold"
    SILVER = "silver"


class Applicability(StrEnum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class GoldenCaseRow:
    case_id: str
    accession_no: str
    route: str
    form_type: str
    form_family: str
    cik: str
    ticker: str | None
    accepted_at: datetime
    period_end: date | None
    is_amendment: bool
    amendment_no: int | None
    truth_cutoff_at: datetime
```

```python
# src/pipeline/golden/review_packets.py
def build_review_packet(*, case, subject, truth_rows, candidate_rows) -> dict[str, object]:
    return {
        "case": {
            "case_id": case.case_id,
            "accession_no": case.accession_no,
            "form_type": case.form_type,
            "accepted_at": case.accepted_at.isoformat(),
            "is_amendment": case.is_amendment,
            "amendment_no": case.amendment_no,
            "truth_cutoff_at": case.truth_cutoff_at.isoformat(),
        },
        "subject": {
            "subject_id": subject.subject_id,
            "subject_type": subject.subject_type,
            "subject_key": subject.subject_key,
            "ordinal": subject.ordinal,
            "label": subject.label,
        },
        "truth": [row.as_dict() for row in truth_rows],
        "candidates": [row.as_dict() for row in candidate_rows],
    }
```

Each dataclass in `src/pipeline/golden/contracts.py` must expose an `as_dict()` method for JSON packet serialization, and each persistence-bound dataclass must expose an `as_db_dict()` method for repository writes.

The loader must preserve `accepted_at`, `is_amendment`, `amendment_no`, `truth_cutoff_at`, and `subject_key` exactly from source files.

- [ ] **Step 4: Run the review-packet test and verify it passes**

Run: `pytest tests/unit/test_golden_review_packets.py -q`
Expected: PASS

- [ ] **Step 5: Commit the point-in-time loading layer**

```bash
git add src/pipeline/golden/contracts.py src/pipeline/golden/catalog.py src/pipeline/golden/loaders.py src/pipeline/golden/review_packets.py tests/unit/test_golden_review_packets.py
git commit -m "feat: add point-in-time golden case loading"
```

### Task 4: Implement evaluator and eligible-denominator metrics

**Files:**
- Create: `src/pipeline/golden/metrics.py`
- Create: `src/pipeline/golden/evaluator.py`
- Create: `src/pipeline/golden/artifacts.py`
- Test: `tests/unit/test_golden_metrics.py`
- Test: `tests/unit/test_golden_evaluator.py`

- [ ] **Step 1: Write the failing metric test**

```python
from decimal import Decimal

from src.pipeline.golden.metrics import compute_metrics


def test_gold_metrics_ignore_silver_rows_and_track_subject_misses() -> None:
    rows = [
        {
            "truth_tier": "gold",
            "applicability": "applicable",
            "matched": True,
            "subject_matched": True,
            "metric_bucket": "gold_strict_accuracy",
        },
        {
            "truth_tier": "silver",
            "applicability": "applicable",
            "matched": False,
            "subject_matched": False,
            "metric_bucket": "silver_alignment",
        },
        {
            "truth_tier": "gold",
            "applicability": "not_applicable",
            "matched": True,
            "subject_matched": True,
            "metric_bucket": "not_applicable_precision",
        },
    ]

    metrics = compute_metrics(rows)

    assert metrics["gold_strict_accuracy"] == Decimal("1")
    assert metrics["silver_alignment"] == Decimal("0")
    assert metrics["gold_applicable_total"] == 1
    assert metrics["not_applicable_total"] == 1
```

- [ ] **Step 2: Write the failing evaluator test**

```python
from decimal import Decimal

from src.pipeline.golden.evaluator import evaluate_field


def test_evaluator_flags_wrong_subject_even_when_value_matches() -> None:
    truth = {
        "truth_tier": "gold",
        "applicability": "applicable",
        "subject_id": "proposal:2",
        "field_name": "proposal_votes_for",
        "value_decimal": Decimal("123"),
        "value_text": None,
        "tolerance_basis_points": 0,
    }
    candidate = {
        "subject_id": "proposal:1",
        "field_name": "proposal_votes_for",
        "candidate_status": "ok",
        "value_decimal": Decimal("123"),
        "value_text": None,
    }

    result = evaluate_field(truth_row=truth, best_candidate=candidate)

    assert result.subject_matched is False
    assert result.matched is False
    assert result.failure_code == "WRONG_SUBJECT"
```

- [ ] **Step 3: Run the evaluator tests and verify they fail**

Run: `pytest tests/unit/test_golden_metrics.py tests/unit/test_golden_evaluator.py -q`
Expected: FAIL with missing module errors

- [ ] **Step 4: Implement metric math, evaluator logic, and artifact writer**

Use these rules exactly:

```python
# src/pipeline/golden/metrics.py
from decimal import Decimal


def ratio(hit: int, total: int) -> Decimal:
    return Decimal("0") if total == 0 else Decimal(hit) / Decimal(total)


def compute_metrics(rows: list[dict[str, object]]) -> dict[str, Decimal | int]:
    gold_applicable_total = sum(
        1 for row in rows
        if row["truth_tier"] == "gold" and row["applicability"] == "applicable"
    )
    gold_applicable_hits = sum(
        1 for row in rows
        if row["truth_tier"] == "gold" and row["applicability"] == "applicable" and row["matched"] is True
    )
    silver_total = sum(
        1 for row in rows
        if row["truth_tier"] == "silver" and row["applicability"] == "applicable"
    )
    silver_hits = sum(
        1 for row in rows
        if row["truth_tier"] == "silver" and row["applicability"] == "applicable" and row["matched"] is True
    )
    return {
        "gold_strict_accuracy": ratio(gold_applicable_hits, gold_applicable_total),
        "silver_alignment": ratio(silver_hits, silver_total),
        "gold_applicable_total": gold_applicable_total,
        "silver_applicable_total": silver_total,
        "not_applicable_total": sum(1 for row in rows if row["applicability"] == "not_applicable"),
    }
```

```python
# src/pipeline/golden/evaluator.py
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class EvalDecision:
    matched: bool
    subject_matched: bool
    failure_code: str | None


def evaluate_field(*, truth_row, best_candidate) -> EvalDecision:
    if best_candidate is None or best_candidate["candidate_status"] != "ok":
        return EvalDecision(matched=False, subject_matched=False, failure_code="CANDIDATE_MISSING")
    subject_matched = truth_row["subject_id"] == best_candidate["subject_id"]
    if not subject_matched:
        return EvalDecision(matched=False, subject_matched=False, failure_code="WRONG_SUBJECT")
    if truth_row["value_decimal"] != best_candidate["value_decimal"]:
        return EvalDecision(matched=False, subject_matched=True, failure_code="VALUE_MISMATCH")
    return EvalDecision(matched=True, subject_matched=True, failure_code=None)
```

`src/pipeline/golden/artifacts.py` must write `manifest.json`, `summary.json`, `by_field.json`, `coverage.json`, `mismatches.ndjson`, `silver_alignment.ndjson`, `invariants.ndjson`, and review packet JSON files under `review_packets/`.

Use this exact manifest shape:

```json
{
  "run_id": "run_001",
  "catalog_path": "configs/golden/v2/field_catalog_numeric.yaml",
  "thresholds_path": "configs/golden/v2/metric_thresholds.yaml",
  "sampling_plan_path": "configs/golden/v2/sampling_plan.yaml",
  "filters": {"route": "issuer", "field_name": "total_revenue", "case_id": null},
  "generated_at": "2026-04-08T00:00:00+00:00",
  "git_commit": "optional",
  "artifact_version": 2
}
```

- [ ] **Step 5: Run the evaluator tests and verify they pass**

Run: `pytest tests/unit/test_golden_metrics.py tests/unit/test_golden_evaluator.py -q`
Expected: PASS

- [ ] **Step 6: Commit the evaluator layer**

```bash
git add src/pipeline/golden/metrics.py src/pipeline/golden/evaluator.py src/pipeline/golden/artifacts.py tests/unit/test_golden_metrics.py tests/unit/test_golden_evaluator.py
git commit -m "feat: add strict golden set evaluator"
```

### Task 5: Wire CLI commands and run an end-to-end v2 evaluation

**Files:**
- Modify: `src/cli.py`
- Test: `tests/integration/test_golden_cli_eval.py`

- [ ] **Step 1: Write the failing CLI test**

```python
from typer.testing import CliRunner

from src.cli import app

runner = CliRunner()


def test_golden_validate_catalog_command() -> None:
    result = runner.invoke(
        app,
        [
            "golden-validate-catalog",
            "--catalog",
            "configs/golden/v2/field_catalog_numeric.yaml",
            "--thresholds",
            "configs/golden/v2/metric_thresholds.yaml",
            "--sampling-plan",
            "configs/golden/v2/sampling_plan.yaml",
        ],
    )
    assert result.exit_code == 0
    assert "53 fields" in result.stdout
```

- [ ] **Step 2: Run the CLI test and verify it fails**

Run: `pytest tests/integration/test_golden_cli_eval.py -q`
Expected: FAIL because `golden-validate-catalog` is not registered

- [ ] **Step 3: Add the v2 CLI commands**

Add these Typer commands in `src/cli.py` with concrete success-path behavior.

```python
from pathlib import Path
from typing import Annotated

import typer

from src.pipeline.golden.artifacts import export_review_packets
from src.pipeline.golden.catalog import load_catalog_bundle
from src.pipeline.golden.evaluator import run_golden_eval_v2
from src.pipeline.golden.loaders import load_cases_from_glob


@app.command("golden-validate-catalog")
def golden_validate_catalog(
    catalog: str = typer.Option("configs/golden/v2/field_catalog_numeric.yaml", "--catalog"),
    thresholds: str = typer.Option("configs/golden/v2/metric_thresholds.yaml", "--thresholds"),
    sampling_plan: str = typer.Option("configs/golden/v2/sampling_plan.yaml", "--sampling-plan"),
) -> None:
    bundle = load_catalog_bundle(
        catalog_path=Path(catalog),
        thresholds_path=Path(thresholds),
        sampling_plan_path=Path(sampling_plan),
    )
    typer.echo(f"{len(bundle.fields)} fields")
    typer.echo("subject counts validated")


@app.command("golden-load-v2")
def golden_load_v2(
    catalog: str = typer.Option("configs/golden/v2/field_catalog_numeric.yaml", "--catalog"),
    source_glob: str = typer.Option("configs/golden/v2/cases/**/*.yaml", "--source-glob"),
) -> None:
    bundle = load_catalog_bundle(
        catalog_path=Path(catalog),
        thresholds_path=Path("configs/golden/v2/metric_thresholds.yaml"),
        sampling_plan_path=Path("configs/golden/v2/sampling_plan.yaml"),
    )
    loaded = load_cases_from_glob(source_glob=source_glob, field_catalog=bundle.field_map)
    typer.echo(f"loaded {len(loaded)} cases")


@app.command("golden-eval-v2")
def golden_eval_v2(
    catalog: str = typer.Option("configs/golden/v2/field_catalog_numeric.yaml", "--catalog"),
    thresholds: str = typer.Option("configs/golden/v2/metric_thresholds.yaml", "--thresholds"),
    sampling_plan: str = typer.Option("configs/golden/v2/sampling_plan.yaml", "--sampling-plan"),
    artifacts_dir: str = typer.Option("artifacts/golden", "--artifacts-dir"),
    route: str | None = typer.Option(None, "--route"),
    field_name: str | None = typer.Option(None, "--field"),
    case_id: str | None = typer.Option(None, "--case-id"),
) -> None:
    result = run_golden_eval_v2(
        catalog_path=Path(catalog),
        thresholds_path=Path(thresholds),
        sampling_plan_path=Path(sampling_plan),
        artifacts_dir=Path(artifacts_dir),
        route=route,
        field_name=field_name,
        case_id=case_id,
    )
    typer.echo(f"run_id: {result.run_id}")
    typer.echo(f"gold_strict_accuracy: {result.metrics['gold_strict_accuracy']}")


@app.command("golden-export-review-packets")
def golden_export_review_packets(
    run_id: Annotated[str, typer.Option("--run-id")],
    output_dir: str = typer.Option("artifacts/golden", "--output-dir"),
) -> None:
    exported = export_review_packets(run_id=run_id, output_dir=Path(output_dir))
    typer.echo(f"exported {exported} review packets")
```

`golden-validate-catalog` must print at least `53 fields` and `subject counts validated` on success.

- [ ] **Step 4: Run the CLI integration test and verify it passes**

Run: `pytest tests/integration/test_golden_cli_eval.py -q`
Expected: PASS

- [ ] **Step 5: Run a local end-to-end smoke evaluation**

Run: `python -m src.cli golden-eval-v2 --route issuer --field total_revenue`
Expected: a new `artifacts/golden/<run_id>/` directory with `manifest.json`, `summary.json`, `by_field.json`, and `mismatches.ndjson`

- [ ] **Step 6: Commit the CLI wiring**

```bash
git add src/cli.py tests/integration/test_golden_cli_eval.py
git commit -m "feat: add strict golden set cli workflow"
```

### Task 6: Rewrite `GOLDEN_SET.md` to match the implemented model

**Files:**
- Modify: `GOLDEN_SET.md`

- [ ] **Step 1: Replace the current truth strategy section with strict terminology**

Use this language verbatim near the top of `GOLDEN_SET.md`:

```markdown
## Truth tiers

- **Gold**: manually adjudicated or independently verified raw XML/XBRL truth; this is the only tier used for strict accuracy claims.
- **Silver**: `companyfacts` or `edgartools` object values used for bootstrap coverage and surveillance; silver does not count as gold accuracy.
- **Invariant**: accounting identities and internal consistency checks; invariant pass/fail is reported separately and never treated as truth.
```

- [ ] **Step 2: Add the canonical field-count explanation**

Use this exact clarification:

```markdown
The numeric golden set contains **53 unique fields**. Repeated appearances of the same canonical field on different form families (for example `total_revenue` on both `10-Q` and `S-1`) do not increase the field count.
```

- [ ] **Step 3: Add the point-in-time and entity-granularity rule**

Use this exact clarification:

```markdown
Every golden record is keyed by `case_id + subject_id + field_name`. Filing-level truth is not sufficient for multi-row forms such as Form 4 transactions, 13F positions, proposal vote tables, executive compensation tables, or beneficial ownership holder tables.
```

- [ ] **Step 4: Verify no stale mixed-truth language remains**

Run: `grep -n "A: companyfacts\|B: xml_obj\|C: cross_validate\|D: manual_seed" GOLDEN_SET.md`
Expected: no output

- [ ] **Step 5: Commit the documentation rewrite**

```bash
git add GOLDEN_SET.md
git commit -m "docs: rewrite golden set model around strict truth tiers"
```

---

## 8. Acceptance checklist for the whole project slice

Before calling this work complete, verify all of the following:

- [ ] `configs/golden/v2/field_catalog_numeric.yaml` validates with exactly 53 unique fields
- [ ] `configs/golden/v2/concept_registry_numeric.yaml` preserves concrete legacy XBRL concept candidates and explicit fallback derivations
- [ ] `configs/golden/v2/invariants_numeric.yaml` contains executable formulas for the legacy income-statement, offering, and 13F cross-checks
- [ ] `configs/golden/v2/seed_tickers.yaml` preserves the curated cold-start ticker lists and rationale from the old design
- [ ] Every field has a non-filing `subject_type` where required (`proposal`, `executive`, `holder_row`, `transaction_row`, `holding_position`)
- [ ] New golden tables use `NUMERIC(38,10)` and never `Float`
- [ ] `gold_strict_accuracy` excludes silver and invariant rows
- [ ] `row_selection_accuracy` can fail independently from raw value matching
- [ ] `golden-eval-v2` writes the full artifact contract from Section 5.2
- [ ] Sampling plan includes ADR/20-F, amendment pairs, and multi-row cases
- [ ] `GOLDEN_SET.md` no longer describes invariant checks as truth

---

## 9. Execution notes

- Keep the current legacy numeric/text evaluators intact until `golden-eval-v2` has passed the acceptance checklist.
- Use existing `src/pipeline/golden_10q_numeric_batch.py` experiments only as source material; do not make the new design depend on that file’s current shape.
- Do not migrate production extraction storage (`ExtractedFact`, `ExtractionEvidence`) in this slice; the goal here is a strict validation system, not a full warehouse refactor.
- If a field lacks independent gold truth, store it as silver or invariant and leave `gold` empty rather than inflating gold coverage.
