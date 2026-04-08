# Golden Set Grain-to-Subject Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a short, explicit mapping in `GOLDEN_SET.md` from field-dictionary granularity labels to golden-set subject types so strict row identity is no longer implicit across docs.

**Architecture:** Make a minimal, single-file documentation change in `GOLDEN_SET.md`. Add one short mapping section that bridges `EXTRACTION_FIELDS.md` field-grain labels to the existing golden subject types without introducing new subject types or reopening broader schema/method questions.

**Tech Stack:** Markdown docs, grep-based verification

---

## File structure

### Modify
- `GOLDEN_SET.md` — add a concise field-grain to subject-type mapping section

### Keep for reference during edit only
- `EXTRACTION_FIELDS.md` — source of field-grain labels
- `docs/superpowers/specs/2026-04-09-golden-grain-subject-mapping-design.md` — approved mapping design

---

### Task 1: Add the field-granularity to subject-type mapping in `GOLDEN_SET.md`

**Files:**
- Modify: `GOLDEN_SET.md`
- Reference: `EXTRACTION_FIELDS.md`
- Reference: `docs/superpowers/specs/2026-04-09-golden-grain-subject-mapping-design.md`

- [ ] **Step 1: Read the current subject-type section and the field-granularity list**

Read:
- `GOLDEN_SET.md`
- `EXTRACTION_FIELDS.md`
- `docs/superpowers/specs/2026-04-09-golden-grain-subject-mapping-design.md`

Confirm the two concept sets that need bridging:
- field dictionary grains like `document`, `proposal_line`, `exec_line`, `holder_line`, `transaction_line`, `filer_line`, `sale_notice`, `position_line`, `security_line`, `derivative_line`
- golden-set subject types like `filing`, `proposal`, `executive`, `holder_row`, `transaction_row`, `reporting_person`, `form144_notice`, `holding_position`

- [ ] **Step 2: Add one short mapping table to `GOLDEN_SET.md`**

Add a compact table with mappings equivalent to:

```markdown
## Field-grain to golden-subject mapping

| Field dictionary grain | Golden subject type |
|---|---|
| `document` | `filing` |
| `proposal_line` | `proposal` |
| `exec_line` | `executive` |
| `holder_line` | `holder_row` |
| `transaction_line` | `transaction_row` |
| `filer_line` | `reporting_person` |
| `sale_notice` | `form144_notice` |
| `position_line` | `holding_position` |
```

- [ ] **Step 3: Add one clarifying note for non-one-to-one grains**

Immediately below the table, add a short note with wording equivalent to:

```markdown
`security_line` and `derivative_line` are extraction-grain labels from the field dictionary, not standalone golden subject types. In strict golden-set evaluation they must resolve to the appropriate filing-level or row-level subject identity rather than introducing new subject-type categories.
```

- [ ] **Step 4: Place the new section where it supports strict identity semantics**

Insert the mapping section near:
- `Canonical 53-field freeze and subject-type distribution`, or
- `Strict case/subject schema concepts`

so readers see it as part of strict subject identity, not as a loose appendix note.

- [ ] **Step 5: Verify the new section does not over-expand scope**

Ensure the mapping addition does **not**:
- create new subject types
- redefine extraction method behavior
- introduce 6-K routing rules
- add subject_id construction algorithms

This is only a semantic bridge between two existing docs.

- [ ] **Step 6: Verify the cross-doc ambiguity is reduced**

Read the updated `GOLDEN_SET.md` and confirm a reader can now infer:
- `proposal_line -> proposal`
- `exec_line -> executive`
- `holder_line -> holder_row`
- `transaction_line -> transaction_row`
- `filer_line -> reporting_person`
- `sale_notice -> form144_notice`
- `position_line -> holding_position`
- `document -> filing`

without guessing.

---

### Task 2: Verify the mapping section is present and narrow

**Files:**
- Verify: `GOLDEN_SET.md`

- [ ] **Step 1: Run focused grep checks**

Run:

```bash
grep -n "Field-grain to golden-subject mapping\|proposal_line\|exec_line\|holder_line\|transaction_line\|filer_line\|sale_notice\|position_line\|security_line\|derivative_line" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/GOLDEN_SET.md"
```

Expected:
- the mapping section is present
- the bridge mappings are explicit
- `security_line` / `derivative_line` clarification is present

- [ ] **Step 2: Do a final doc-quality pass**

Check that the new addition:
- removes ambiguity without becoming an implementation spec
- does not conflict with `EXTRACTION_FIELDS.md`
- does not create new subject types or naming drift
- stays short and policy-oriented

If any issue is present, fix it immediately.

- [ ] **Step 3: Commit the mapping clarification**

```bash
git add GOLDEN_SET.md docs/superpowers/specs/2026-04-09-golden-grain-subject-mapping-design.md docs/superpowers/plans/2026-04-09-golden-grain-subject-mapping.md
git commit -m "docs: clarify golden subject mapping"
```

---

## Self-review

Spec coverage check:
- add explicit mapping table: covered in Task 1 Step 2
- clarify `security_line` / `derivative_line`: covered in Task 1 Step 3
- keep change minimal and policy-oriented: covered in Task 1 Steps 4-5
- verify ambiguity is reduced: covered in Task 1 Step 6 and Task 2

Placeholder scan:
- No TBD/TODO placeholders remain.
- All targets and verification commands are explicit.

Type / terminology consistency:
- `EXTRACTION_FIELDS.md` remains the source of field-grain labels.
- `GOLDEN_SET.md` remains the source of strict subject identity semantics.
