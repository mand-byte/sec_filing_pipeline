# Golden Set Documentation Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate `GOLDEN_SET.md` and `GOLDEN_SET_PLAN.md` into a single strict golden-set authority document that includes document-type/channel boundaries and invariant-based validation guidance.

**Architecture:** Rewrite `GOLDEN_SET.md` as the single normative document using the strict-v2 model from `GOLDEN_SET_PLAN.md` plus the durable field/concept/invariant knowledge from the old `GOLDEN_SET.md`. Update inbound references to point to `GOLDEN_SET.md`, then remove `GOLDEN_SET_PLAN.md` so the repository ends with one golden-set document only.

**Tech Stack:** Markdown, repo docs, grep-based verification

---

## File structure

### Modify
- `GOLDEN_SET.md` — rewrite into the single authoritative strict golden-set document
- `DEMANDS.md` — update the golden-set reference from `GOLDEN_SET_PLAN.md` to `GOLDEN_SET.md`

### Delete
- `GOLDEN_SET_PLAN.md` — remove after all relevant content has been merged into `GOLDEN_SET.md`

### Keep for reference during rewrite only
- `docs/superpowers/specs/2026-04-08-golden-set-doc-consolidation-design.md` — approved consolidation design

---

### Task 1: Rewrite `GOLDEN_SET.md` as the single authority document

**Files:**
- Modify: `GOLDEN_SET.md`
- Reference: `docs/superpowers/specs/2026-04-08-golden-set-doc-consolidation-design.md`

- [ ] **Step 1: Read the approved consolidation design and the current golden-set doc side by side**

Read:
- `docs/superpowers/specs/2026-04-08-golden-set-doc-consolidation-design.md`
- `GOLDEN_SET.md`

Verify the rewrite must include:
- strict truth tiers
- document-type × channel mapping
- edgartools source reliability ranking
- 53-field canonical inventory explanation
- case/subject grain
- cross-check / accounting-identity methods
- core schema / metrics / artifacts / phase gates

- [ ] **Step 2: Replace the top-level framing with strict terminology**

Write the opening section so it includes this exact language:

```markdown
## Truth tiers

- **Gold**: manually adjudicated or independently verified raw XML/XBRL truth; this is the only tier used for strict accuracy claims.
- **Silver**: `companyfacts` or `edgartools` object values used for bootstrap coverage and surveillance; silver does not count as gold accuracy.
- **Invariant**: accounting identities and internal consistency checks; invariant pass/fail is reported separately and never treated as truth.
```

Also include this exact clarification nearby:

```markdown
The numeric golden set contains **53 unique fields**. Repeated appearances of the same canonical field on different form families (for example `total_revenue` on both `10-Q` and `S-1`) do not increase the field count.
```

And this exact grain rule:

```markdown
Every golden record is keyed by `case_id + subject_id + field_name`. Filing-level truth is not sufficient for multi-row forms such as Form 4 transactions, 13F positions, proposal vote tables, executive compensation tables, or beneficial ownership holder tables.
```

- [ ] **Step 3: Add the document-type × channel mapping section**

Add a section in `GOLDEN_SET.md` with content equivalent to this structure:

```markdown
## Channel types by filing family

### XBRL-first
Use for filing families where the primary high-confidence numeric source is filing-level XBRL facts.

- `10-K`
- `10-Q`
- `20-F`
- selected financial exhibits where filing XBRL is actually present

### Object/XML-first
Use where edgartools exposes typed filing objects or XML-backed structured parsing and the primary trust source is raw XML/object data, not XBRL.

- `3`
- `4`
- `5`
- `13D`
- `13G`
- `13F-HR`
- `144`

### HTML / anchored-table-first
Use where the relevant truth is primarily embedded in HTML tables, proposal sections, ownership tables, or narrative sections.

- `DEF 14A`
- parts of `8-K`
- parts of `S-1`
- parts of `424B4`
- parts of `SC TO-I`
- parts of `SC 13E3`

### Filing-family routing notes
- `8-K`: default to `filing.obj()` / item-aware / exhibit-aware parsing; only use XBRL locally if a financial exhibit truly provides it.
- `DEF 14A`: default to HTML/table anchoring for proposals and beneficial ownership; use structured sources only for fields that genuinely have them.
- `S-1` / `424B4` / `SC TO-I` / `SC 13E3`: route by field; some fields can use raw XBRL or structured data, while offering / transaction terms often require anchored parsing plus review.
```

- [ ] **Step 4: Add the truth-source reliability ranking section**

Add a section in `GOLDEN_SET.md` with this ordering and explanation:

```markdown
## Truth source reliability ranking

### Financial-statement filings
1. `xbrl-querying` ≈ `getting-xbrl`
2. `extract-statements`
3. `company-facts`

`xbrl-querying` and `getting-xbrl` are closest to the single-filing raw XBRL facts and are the preferred basis for strict gold truth. `extract-statements` is a high-quality statement abstraction over filing XBRL but is still one layer more abstract than raw fact querying. `company-facts` is SEC-aggregated entity-level data and is therefore silver/bootstrap/surveillance data, not strict gold truth.

### XML / object filings
1. `raw_xml`
2. `filing.obj()` / typed object
3. anchored HTML/XML parsing
4. manual adjudication

For `3`/`4`/`5`, `13D`/`13G`, `13F-HR`, and `144`, the primary trust source is raw XML plus object-backed parsing rather than XBRL.
```

- [ ] **Step 5: Replace mixed-truth strategy prose with invariant-based validation methods**

Add a section in `GOLDEN_SET.md` that groups validation methods into explicit invariant categories. Use these formulas and interpretations:

```markdown
## Cross-checks and accounting invariants

Cross-checks validate internal consistency. They are stored and reported as invariants, not as truth.

### Financial statement invariants
- `total_revenue >= operating_income`
- `diluted_eps ≈ net_income / shares_outstanding`
- `cash_and_equivalents >= 0`
- `total_debt >= 0`

### Offering / IPO invariants
- `gross_proceeds ≈ offering_price_per_share × securities_offered_qty`
- `net_proceeds ≈ gross_proceeds - underwriter_discount_total`
- `underwriter_discount_total > 0`
- `offering_price_per_share > 0`

### Ownership / transaction invariants
- `shares_owned_following_txn == prior_balance + shares_acquired_or_disposed`
- `transaction_price_per_share > 0`
- `beneficial_ownership_pct ∈ [0,100]`
- `sole_voting_power + shared_voting_power >= beneficially_owned_shares` (usually)

### 13F invariants
- `sum(position_value_usd) ≈ info_table_value_total_usd`
- `count(positions) == info_table_entry_total`
- `sole_voting_auth_shares + shared_voting_auth_shares + none_voting_auth_shares == shares_or_principal_amount`

Invariant failures trigger review and mismatch artifacts. Invariant passes improve confidence but never become gold truth by themselves.
```

- [ ] **Step 6: Preserve the strict-v2 core and remove execution-manual content**

Keep in `GOLDEN_SET.md`:
- the 53-field freeze and subject-type counts
- strict case/subject schema concepts
- core table names (`golden_case`, `golden_subject`, `golden_truth`, `golden_invariant_result`, `golden_candidate`, `golden_eval_run`, `golden_eval_result`, `golden_review_packet`)
- metric definitions (`gold_strict_accuracy`, `gold_coverage`, `row_selection_accuracy`, `not_applicable_precision`, `silver_alignment`, `invariant_pass_rate`)
- artifact contract and stable phase gates
- concept-registry and seed-ticker rationale where it clarifies durable domain rules

Remove from `GOLDEN_SET.md`:
- `A: companyfacts / B: xml_obj / C: cross_validate / D: manual_seed`
- any text treating invariants as truth
- any text treating `companyfacts` or `edgartools_obj` as gold truth
- step-by-step task lists, pytest commands, expected failures, commit-message templates, and day-by-day schedule prose

- [ ] **Step 7: Verify the rewrite reads as one self-contained document**

Read `GOLDEN_SET.md` and confirm a reader can understand:
- what the golden set is
- which sources qualify as gold vs silver vs invariant
- which channel applies to which filing family
- how the system validates extracted values
- what grain/schema/metrics/artifacts exist

No section should require opening `GOLDEN_SET_PLAN.md` to make sense.

---

### Task 2: Update references and remove the second golden-set document

**Files:**
- Modify: `DEMANDS.md`
- Delete: `GOLDEN_SET_PLAN.md`

- [ ] **Step 1: Write the reference update in `DEMANDS.md`**

Change this line:

```markdown
2. **严谨的基准集 (Golden Set V2)**：摒弃混合真值的统计方法。构建独立可审计的 Gold、Silver 和 Invariant 数据集与点对点的精准打标库，用确切的 SQL Denominators 计算提取正确率。所有具体的概念（Concepts）、公式、测试用例都必须以版本化配置（YAML）沉淀。详见 [GOLDEN_SET_PLAN.md](./GOLDEN_SET_PLAN.md)。
```

To this:

```markdown
2. **严谨的基准集 (Golden Set V2)**：摒弃混合真值的统计方法。构建独立可审计的 Gold、Silver 和 Invariant 数据集与点对点的精准打标库，用确切的 SQL Denominators 计算提取正确率。所有具体的概念（Concepts）、公式、测试用例都必须以版本化配置（YAML）沉淀。详见 [GOLDEN_SET.md](./GOLDEN_SET.md)。
```

- [ ] **Step 2: Delete `GOLDEN_SET_PLAN.md` once the merge is complete**

Remove the file entirely after verifying `GOLDEN_SET.md` already contains the durable content that used to require it.

- [ ] **Step 3: Search for stale references and mixed-truth language**

Run:

```bash
grep -n "GOLDEN_SET_PLAN\.md" DEMANDS.md GOLDEN_SET.md || true
grep -n "A: companyfacts\|B: xml_obj\|C: cross_validate\|D: manual_seed" GOLDEN_SET.md || true
grep -n "companyfacts.*gold\|edgartools_obj.*gold\|invariant.*truth" GOLDEN_SET.md || true
```

Expected:
- no references to `GOLDEN_SET_PLAN.md` in shipped docs
- no legacy A/B/C/D truth-strategy labels in `GOLDEN_SET.md`
- no wording that promotes silver or invariants to gold truth

- [ ] **Step 4: Read the final document set for consistency**

Read:
- `GOLDEN_SET.md`
- `DEMANDS.md`

Verify:
- `DEMANDS.md` now points to `GOLDEN_SET.md`
- `GOLDEN_SET.md` is the only golden-set authority doc in the repo root
- terminology is consistent between the two files

---

### Task 3: Verify the consolidation outcome

**Files:**
- Verify: `GOLDEN_SET.md`
- Verify: `DEMANDS.md`

- [ ] **Step 1: Run the final grep checks**

Run:

```bash
grep -n "GOLDEN_SET_PLAN\.md" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline"/*.md || true
grep -n "A: companyfacts\|B: xml_obj\|C: cross_validate\|D: manual_seed" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/GOLDEN_SET.md" || true
grep -n "xbrl-querying\|getting-xbrl\|extract-statements\|company-facts" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/GOLDEN_SET.md"
grep -n "Cross-checks and accounting invariants\|13F invariants\|Ownership / transaction invariants" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/GOLDEN_SET.md"
```

Expected:
- no shipped root markdown file references `GOLDEN_SET_PLAN.md`
- no old A/B/C/D mixed-truth section remains in `GOLDEN_SET.md`
- the reliability-ranking section is present
- the invariant section is present

- [ ] **Step 2: Do a final doc-quality pass**

Check `GOLDEN_SET.md` for these failures:
- duplicated sections carried over from both old docs
- contradictory claims about gold/silver/invariant
- channel guidance that assigns all filings to XBRL
- task/checklist/test-command residue from the old plan
- missing mention of multi-row subject grain

If any are present, fix them immediately in the doc.

- [ ] **Step 3: Commit the doc consolidation**

```bash
git add GOLDEN_SET.md DEMANDS.md docs/superpowers/specs/2026-04-08-golden-set-doc-consolidation-design.md docs/superpowers/plans/2026-04-08-golden-set-doc-consolidation.md
git rm GOLDEN_SET_PLAN.md
git commit -m "docs: consolidate golden set documentation"
```

---

## Self-review

Spec coverage check:
- single authority doc: covered in Tasks 1-2
- document-type × channel mapping: covered in Task 1 Step 3
- edgartools reliability ranking: covered in Task 1 Step 4
- cross-check / accounting-identity methods: covered in Task 1 Step 5
- remove ambiguous mixed-truth language: covered in Task 1 Step 6 and Task 2 Step 3
- remove second doc: covered in Task 2 Step 2 and Task 3 Step 1

Placeholder scan:
- No TBD/TODO placeholders remain.
- All edit targets, grep checks, and replacement text are explicit.

Type / terminology consistency:
- Uses `Gold`, `Silver`, `Invariant` consistently.
- Uses `GOLDEN_SET.md` as the final authority doc everywhere.
- Uses the same channel labels throughout: `XBRL-first`, `Object/XML-first`, `HTML / anchored-table-first`.
