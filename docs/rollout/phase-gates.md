# Phase Gates

This document records the current executable rollout posture for the
`sec_filing_pipeline` repository.

## Current Verified Baseline

- `uv run pytest -q`
- `uv build`
- `uv run python main.py strict-v2-eval --min-pass-rate 1.0 --artifacts-dir /tmp/sec-filing-strict-v2-artifacts`

These checks are the minimum release proof for the current tranche.

## Phase-1 Deterministic Gate

The default strict-v2 assets now cover a fifteen-case deterministic slice:

- issuer
  - `current_event_quant`
  - `delay_reason_quant`
  - `mdna_outlook_quant`
  - `risk_factor_quant`
  - `use_of_proceeds_quant`
  - `tender_going_private_quant`
  - `proxy_proposal_quant`
  - `comp_policy_quant`
- owner
  - `beneficial_ownership_intent_quant`
  - `source_of_funds_quant`
  - `insider_role_ownership_structure_quant`
  - `insider_transaction_quant`
  - `rule144_sale_plan_quant`
- holding
  - `manager_structure_quant`
  - `amendment_scope_quant`

Expected gate result:

- `passed = 15`
- `failed = 0`
- `gold_strict_accuracy = 1.0000`

Route distribution in the checked-in strict-v2 seed:

- `issuer = 8`
- `owner = 5`
- `holding = 2`

## Fix-Once Gate

Use:

```bash
uv run python main.py release-gate --output-dir artifacts/release_gate
```

Pass condition:

- no open review tasks
- every non-accept review decision has a `GoldenReviewPacket`
- regression packet exports are emitted under `artifacts/release_gate/review_regressions`

## Deployment Notes

- Apply `src/db/migrations/20260411_add_evidence_locator_and_filing_attempt.sql`
  before deploying the richer evidence metadata / filing-attempt code to an
  existing PostgreSQL database.
- `CH_DSN` is now materially used by `load_security_universe` as the first
  universe-source path, with safe fallback to SQLAlchemy / `SecurityMaster`.
- The runtime env contract lives in `.env.example` and `configs/runtime/README.md`;
  prefer `PG_DSN` / `CH_DSN` / `START_DATE` over legacy split connection vars.
