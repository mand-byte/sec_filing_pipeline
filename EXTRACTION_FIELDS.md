# Extraction Field Dictionary (Authoritative Specification)

This document is the single authoritative **field dictionary** for the SEC filing extraction pipeline. It defines **what to extract** — the canonical fields, their granularity, applicable form families, semantic definitions, and output schemas.

**This document does NOT define:**
- How extraction works (see `EXTRACTION_METHOD.md`)
- How truth is defined or evaluated (see `GOLDEN_SET.md`)

## Document Boundaries

| Document | Purpose |
|---|---|
| `DEMANDS.md` | Project goals, global principles, and roadmap |
| `EXTRACTION_METHOD.md` | Extraction architecture, routing, correctness engineering, cold-start, and review process |
| `EXTRACTION_FIELDS.md` (this doc) | Field dictionary — defines what fields to extract |
| `GOLDEN_SET.md` | Truth tiers, strict schema, evaluation metrics, artifacts, and release gates |

## Common Conventions

- **Public metadata** is maintained once in a common table and not repeated per field: `accession_no`, `cik`, `form_type`, `filed_at`, `accepted_at`, `period_end`, `issuer_name`, `ticker`, `filer_name`, `reported_currency`.
- **Numeric fields** only include fields that can be directly stored, used for factor analysis, or monitored. Dates, IDs, and enums are not included in numeric tables.
- **Schema notation**: compact JSON schema format — `number`, `integer`, `boolean`, `string[]`, `number[0,5]` (bounded), `number|null` (nullable), `number[0,5]|null` (bounded nullable), `enum[...]`.

## Field Granularity Types

| Granularity | Description |
|---|---|
| `document` | Single value per filing |
| `security_line` | Per-security line item (e.g., offering price per security) |
| `proposal_line` | Per-proposal vote row |
| `exec_line` | Per-executive compensation row |
| `holder_line` | Per-holder beneficial ownership row |
| `transaction_line` | Per-transaction row (Form 4/5) |
| `position_line` | Per-holding position row (Form 13F) |
| `derivative_line` | Per derivative security row |
| `filer_line` | Per-filer ownership summary |
| `sale_notice` | Form 144 sale notice row |

---

## Issuer Route: Numeric Field Dictionary

The issuer route covers numeric fields organized by filing subfamily. Fields may be applicable only to certain form types (periodic reports like 10-K/10-Q/20-F, current/event reports like 8-K/6-K, registration/offering statements like S-1/424B4, proxy statements like DEF 14A, and transaction-specific forms like SC TO-I and SC 13E3). Other form types will have empty values.

| Field Name | Granularity | Applicable Forms | Document Field Variants |
|---|---|---|---|
| `total_revenue` | document | 10-K, 10-Q, 20-F, 6-K-financial, S-1, 424B4 | `Revenue`; `Net sales`; `Sales`; `Total revenues` |
| `operating_income` | document | 10-K, 10-Q, 20-F, 6-K-financial, S-1, 424B4 | `Operating income`; `Income from operations`; `Operating profit` |
| `net_income` | document | 10-K, 10-Q, 20-F, 6-K-financial, S-1, 424B4 | `Net income`; `Net earnings`; `Profit for the period/year` |
| `diluted_eps` | document | 10-K, 10-Q, 20-F, 6-K-financial, S-1, 424B4 | `Diluted EPS`; `Earnings per share-diluted`; `Basic and diluted earnings per share` |
| `cash_and_equivalents` | document | 10-K, 10-Q, 20-F, S-1, 424B4 | `Cash and cash equivalents`; `Cash` |
| `total_debt` | document | 10-K, 10-Q, 20-F, S-1, 424B4 | Total short-term and long-term debt obligations as reported in filing |
| `operating_cash_flow` | document | 10-K, 10-Q, 20-F, S-1, 424B4 | `Net cash provided by operating activities` |
| `capex` | document | 10-K, 10-Q, 20-F, S-1, 424B4 | `Capital expenditures`; `Purchases of property and equipment`; `Additions to PP&E` |
| `shares_outstanding` | document | 10-K, 10-Q, 20-F, S-1, 424B4, DEF 14A | `Shares outstanding`; `Common stock outstanding`; `Ordinary shares outstanding` |
| `filing_delay_days` | document | NT 10-Q, NT 10-K | Days between statutory deadline and expected filing date per delay notification |
| `gross_proceeds` | document | S-1, 424B4 | `Aggregate offering price`; `Gross proceeds`; `Total offering amount` |
| `net_proceeds` | document | S-1, 424B4 | `Net proceeds`; `Estimated net proceeds` |
| `offering_price_per_share` | security_line | S-1, 424B4 | `Public offering price`; `Price to public`; `Initial offering price` |
| `securities_offered_qty` | security_line | S-1, 424B4 | `Shares offered`; `Units offered`; `Over-allotment option shares` |
| `underwriter_discount_total` | document | S-1, 424B4 | `Underwriting discounts and commissions` |
| `deal_value` | document | 8-K, 6-K, SC TO-I, SC 13E3 | `Aggregate consideration`; `Transaction value`; `Purchase price`; `Merger consideration` |
| `offer_price_per_share` | security_line | SC TO-I, SC 13E3, 8-K (transaction terms) | `Offer price`; `Cash consideration per share`; `Merger consideration per share` |
| `tender_shares_sought` | security_line | SC TO-I | `Number of shares sought`; `Maximum number of shares`; `Shares accepted for purchase` |
| `financing_commitment_amount` | document | 8-K, SC TO-I, SC 13E3, S-1 | `Financing commitment`; `Backstop amount`; `Debt financing`; `Equity commitment` |
| `termination_fee` | document | 8-K, SC TO-I, SC 13E3 | `Termination fee`; `Break-up fee`; `Reverse termination fee` |
| `exec_total_comp` | exec_line | DEF 14A, S-1 | `Total` from `Summary Compensation Table` |
| `holder_beneficial_ownership_shares` | holder_line | DEF 14A, S-1, 424B4 | `Amount and nature of beneficial ownership`; `Shares beneficially owned` |
| `holder_beneficial_ownership_pct` | holder_line | DEF 14A, S-1, 424B4 | `Percent of class`; `Percentage of shares beneficially owned` |
| `proposal_votes_for` | proposal_line | 8-K (Item 5.07) | `Votes For` |
| `proposal_votes_against` | proposal_line | 8-K (Item 5.07) | `Votes Against` (normalization may include Withheld votes where SEC rules treat them as Against) |
| `proposal_votes_abstain` | proposal_line | 8-K (Item 5.07) | `Abstentions` |
| `proposal_broker_non_votes` | proposal_line | 8-K (Item 5.07) | `Broker non-votes` |

---

## Issuer Route: Snippet Field Dictionary

| Snippet Name | Applicable Forms | Typical Source Section | LLM Output Schema |
|---|---|---|---|
| `mdna_outlook_quant` | 10-K, 10-Q, 20-F, 6-K-financial, S-1, 424B4 | `MD&A`; `Operating and Financial Review`; `Prospects` | `{"revenue_direction":"enum[up,flat,down,unclear]","margin_direction":"enum[up,flat,down,unclear]","demand_score":"number[-2,2]","liquidity_stress_score":"number[0,5]","capex_direction":"enum[up,flat,down,unclear]","confidence":"number[0,1]"}` |
| `risk_factor_quant` | 10-K, 10-Q, 20-F, S-1, 424B4, SC TO-I, SC 13E3 | `Risk Factors`; `Risk Considerations` | `{"categories":"string[]","severity_score":"number[0,5]","probability_score":"number[0,1]","horizon":"enum[lt12m,1to3y,gt3y,unclear]","delta_vs_prior":"enum[up,flat,down,unclear]"}` |
| `current_event_quant` | 8-K, 6-K | Item body; press release exhibit | `{"event_type":"enum[earnings,m&a,financing,leadership,bankruptcy,litigation,regulatory,vote,other]","materiality_score":"number[0,5]","cash_impact_usd":"number|null","dilution_pct":"number|null","one_time_cost_usd":"number|null","recurrence":"enum[one_off,ongoing,unclear]"}` |
| `delay_reason_quant` | NT 10-Q, NT 10-K | Delay reason explanation | `{"delay_reason_type":"enum[audit,internal_control,transaction,valuation,system,other]","severity_score":"number[0,5]","expected_days_to_file":"integer|null","restatement_flag":"boolean","auditor_issue_flag":"boolean"}` |
| `use_of_proceeds_quant` | S-1, 424B4 | `Use of Proceeds` | `{"debt_repayment_pct":"number[0,100]","capex_pct":"number[0,100]","acquisition_pct":"number[0,100]","working_capital_pct":"number[0,100]","general_corporate_pct":"number[0,100]","secondary_sale_pct":"number[0,100]"}` |
| `proxy_proposal_quant` | DEF 14A | Each proposal section | `{"proposal_type":"enum[election,say_on_pay,equity_plan,capital_structure,auditor,shareholder_proposal,other]","board_recommendation":"enum[for,against,neutral]","governance_impact_score":"number[0,5]","estimated_dilution_pct":"number|null","pay_alignment_score":"number[0,5]|null"}` |
| `comp_policy_quant` | DEF 14A, S-1 | `CD&A`; executive compensation narrative | `{"pay_for_performance_score":"number[0,5]","fixed_pay_pct":"number[0,100]","variable_pay_pct":"number[0,100]","equity_pay_pct":"number[0,100]","one_time_award_flag":"boolean","change_in_control_richness_score":"number[0,5]"}` |
| `tender_going_private_quant` | SC TO-I, SC 13E3 | Summary term sheet; special factors; fairness discussion | `{"transaction_type":"enum[self_tender,exchange_offer,cash_merger,stock_merger,reverse_split,other]","premium_pct":"number|null","cash_mix_pct":"number[0,100]|null","fairness_conclusion":"enum[fair,not_fair,mixed,na]","close_probability":"number[0,1]","financing_risk_score":"number[0,5]","valuation_range_low":"number|null","valuation_range_high":"number|null"}` |

---

## Owner Route: Numeric Field Dictionary

The owner route covers ownership-related disclosures. Form 3 provides initial beneficial ownership, Form 4 reports changes, and Form 5 provides annual summaries. Forms 13D and 13G are for beneficial ownership reporting.

| Field Name | Granularity | Applicable Forms | Document Field Variants |
|---|---|---|---|
| `non_derivative_shares_owned` | holder_line | 3, 4, 5 | `Amount of Securities Beneficially Owned` |
| `derivative_underlying_shares` | derivative_line | 3, 4, 5 | `Number of Derivative Securities Beneficially Owned`; `Amount or Number of Shares Underlying Derivative Security` |
| `shares_acquired_or_disposed` | transaction_line | 4, 5 | `Amount of Securities Acquired (A) or Disposed of (D)` |
| `transaction_price_per_share` | transaction_line | 4, 5 | `Price(s)` |
| `shares_owned_following_txn` | transaction_line | 4, 5 | `Amount of Securities Beneficially Owned Following Reported Transaction(s)` |
| `exercise_or_conversion_price` | derivative_line | 3, 4, 5 | `Conversion or Exercise Price of Derivative Security` |
| `beneficially_owned_shares` | filer_line | 13D, 13G | `Aggregate Amount Beneficially Owned by Each Reporting Person` |
| `beneficial_ownership_pct` | filer_line | 13D, 13G | `Percent of Class Represented by Amount` |
| `sole_voting_power` | filer_line | 13D, 13G | `Sole power to vote` |
| `shared_voting_power` | filer_line | 13D, 13G | `Shared power to vote` |
| `sole_dispositive_power` | filer_line | 13D, 13G | `Sole power to dispose` |
| `shared_dispositive_power` | filer_line | 13D, 13G | `Shared power to dispose` |
| `aggregate_purchase_price` | filer_line | 13D | `Aggregate purchase price`; `Total funds used` |
| `source_of_funds_amount` | filer_line | 13D | `Source and amount of funds or other consideration` |
| `proposed_sale_shares` | sale_notice | 144 | `Number of shares or other units to be sold` |
| `proposed_sale_market_value` | sale_notice | 144 | `Aggregate market value` |
| `shares_sold_past_3m` | sale_notice | 144 | `Number of shares sold during the past 3 months` |
| `market_value_sold_past_3m` | sale_notice | 144 | `Aggregate market value sold during the past 3 months` |

---

## Owner Route: Snippet Field Dictionary

| Snippet Name | Applicable Forms | Typical Source Section | LLM Output Schema |
|---|---|---|---|
| `insider_transaction_quant` | 4, 5 | Transaction footnote; remarks | `{"transaction_type":"enum[buy,sell,exercise,award,withholding,gift,conversion,other]","economic_exposure_change":"enum[increase,decrease,neutral]","size_bucket":"enum[small,medium,large]","price_signal":"enum[bullish,bearish,neutral,na]","rule_10b5_1_flag":"boolean|null","related_derivative_flag":"boolean"}` |
| `insider_role_ownership_structure_quant` | 3, 4, 5 | Cover page + ownership footnote | `{"is_director":"boolean","is_officer":"boolean","is_ten_percent_holder":"boolean","direct_holding_flag":"boolean","indirect_holding_flag":"boolean","vehicle_types":"string[]"}` |
| `beneficial_ownership_intent_quant` | 13D, 13G | `Item 4 Purpose of Transaction`; cover items | `{"stance":"enum[passive,engaged,activist,control]","board_seat_seek":"boolean","solicitation_or_proxy_fight":"boolean","strategic_alternatives":"boolean","m&a_interest":"boolean","group_flag":"boolean","time_horizon":"enum[short,medium,long,unclear]"}` |
| `source_of_funds_quant` | 13D | `Item 3 Source and Amount of Funds` | `{"cash_on_hand_pct":"number[0,100]","margin_loan_pct":"number[0,100]","other_debt_pct":"number[0,100]","seller_financing_pct":"number[0,100]","financing_complexity_score":"number[0,5]"}` |
| `rule144_sale_plan_quant` | 144 | Sale plan / remarks | `{"sale_reason":"enum[liquidity,diversification,tax,estate,pledge_release,other]","planned_sale_pct_of_holdings":"number|null","broker_involved":"boolean","control_person_flag":"boolean","related_pledge_or_margin_flag":"boolean"}` |

---

## Holdings Route: Numeric Field Dictionary

The holdings route covers institutional investment manager position reports (Form 13F). Positions are defined at the issuer/class level with shares and fair market value. Per SEC's 13F FAQ and XML info table, the `VALUE` field represents near-market value.

| Field Name | Granularity | Applicable Forms | Document Field Variants |
|---|---|---|---|
| `position_value_usd` | position_line | 13F-HR | `VALUE` |
| `shares_or_principal_amount` | position_line | 13F-HR | `SHRS OR PRN AMT` |
| `sole_voting_auth_shares` | position_line | 13F-HR | `Voting Authority Sole` |
| `shared_voting_auth_shares` | position_line | 13F-HR | `Voting Authority Shared` |
| `none_voting_auth_shares` | position_line | 13F-HR | `Voting Authority None` |
| `other_included_managers_count` | document | 13F-HR | `Number of Other Included Managers` |
| `info_table_entry_total` | document | 13F-HR | `Form 13F Information Table Entry Total` |
| `info_table_value_total_usd` | document | 13F-HR | `Form 13F Information Table Value Total` |

---

## Holdings Route: Snippet Field Dictionary

| Snippet Name | Applicable Forms | Typical Source Section | LLM Output Schema |
|---|---|---|---|
| `manager_structure_quant` | 13F-HR | Cover page; summary; additional information | `{"report_type":"enum[holdings,notice,combination]","other_included_managers_count":"integer","shared_discretion_flag":"boolean","confidential_treatment_flag":"boolean","signer_capacity":"enum[manager,authorized_person,other]"}` |
| `amendment_scope_quant` | 13F-HR/A | Amendment note; header | `{"amendment_kind":"enum[correction,restatement,additions,deletions,other]","restatement_flag":"boolean","position_count_delta":"integer|null","value_delta_usd":"number|null"}` |

---

## Non-Numeric Position Dimensions (13F)

These position dimensions must be retained but are not numeric:

- `name_of_issuer`
- `title_of_class`
- `cusip_or_figi`
- `put_call`
- `investment_discretion`

---

## Amendment Overlay Fields

All `/A` (amendment) filings should uniformly include these 4 common overlay fields:

| Field Name | Description |
|---|---|
| `amendment_no` | Amendment sequence number |
| `is_full_restatement` | Whether this is a full restatement |
| `amended_sections` | List of sections amended |
| `amendment_reason_quant` | Reason for amendment |

`amendment_reason_quant` schema:

```json
{
  "amendment_type": "enum[correction,update,restatement,supplement,other]",
  "scope": "enum[partial,full]",
  "materiality_score": "number[0,5]",
  "affects_numeric_values": "boolean",
  "affected_tables": "string[]"
}
```