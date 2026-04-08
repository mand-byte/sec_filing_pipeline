# Golden Set Versioned-Config Rule Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore an explicit hard rule in `GOLDEN_SET.md` requiring executable golden-set knowledge to live in versioned config and tests rather than only in narrative docs.

**Architecture:** Make a minimal, single-file documentation change to `GOLDEN_SET.md`. Add one short normative section or hard rule that clearly states which rule surfaces must be stored in versioned config/tests, while preserving the existing four-doc architecture and avoiding broader content changes.

**Tech Stack:** Markdown docs, grep-based verification

---

## File structure

### Modify
- `GOLDEN_SET.md` — restore the explicit versioned-config hard rule

### Keep for reference during edit only
- `docs/superpowers/specs/2026-04-09-golden-versioned-config-rule-design.md` — approved design for this small restoration

---

### Task 1: Restore the versioned-config hard rule in `GOLDEN_SET.md`

**Files:**
- Modify: `GOLDEN_SET.md`
- Reference: `docs/superpowers/specs/2026-04-09-golden-versioned-config-rule-design.md`

- [ ] **Step 1: Read the current `GOLDEN_SET.md` and the approved design**

Read:
- `GOLDEN_SET.md`
- `docs/superpowers/specs/2026-04-09-golden-versioned-config-rule-design.md`

Confirm what needs to be restored:
- concept candidates must be versioned
- fallback derivations must be versioned
- executable invariants must be versioned
- curated seed ticker sets/rationale must be versioned
- regression / validation cases must live in tests or structured fixtures
- narrative docs are explanatory, not the authoritative executable source

- [ ] **Step 2: Add one short hard-rule section to `GOLDEN_SET.md`**

Add a compact section or hard rule with wording equivalent to:

```markdown
## Versioned rule sources

Narrative documentation is not the authoritative source for executable golden-set rules. The following must live in versioned config and tests:

- XBRL concept candidates and source priorities
- Fallback derivation formulas and required inputs
- Executable invariants and tolerances
- Curated seed-ticker sets and their rationale
- Regression / validation cases used to prevent repeat failures

`GOLDEN_SET.md` explains the model, but the enforceable rule surface must be stored in versioned config and test artifacts.
```

Keep it normative, not suggestive.

- [ ] **Step 3: Place the new rule where it reads as a core requirement**

Insert it in a clearly normative part of the document, for example:
- near other hard-rule / governance sections, or
- just before / after concept-registry and seed-ticker guidance,

as long as the section reads like a requirement and not an appendix note.

- [ ] **Step 4: Verify the wording does not over-expand scope**

Ensure the new text does **not**:
- introduce new file paths
- add implementation-plan detail
- reopen schema design
- duplicate `DEMANDS.md` or `EXTRACTION_METHOD.md`

This is a hard-rule restoration, not a broader rewrite.

- [ ] **Step 5: Verify the restored rule now covers the missing requirement strength**

Read the final `GOLDEN_SET.md` and confirm a reader can now clearly infer that these are not optional narrative ideas:
- concepts
- derivations
- invariants
- seed sets/rationale
- regression / validation cases

must be represented in versioned config/tests.

---

### Task 2: Verify the restored rule is present and scoped correctly

**Files:**
- Verify: `GOLDEN_SET.md`

- [ ] **Step 1: Run focused grep checks**

Run:

```bash
grep -n "Versioned rule sources\|versioned config\|Fallback derivation\|Executable invariants\|Curated seed-ticker\|Regression / validation cases" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/GOLDEN_SET.md"
```

Expected:
- the new hard-rule section is present
- the listed rule surfaces are explicitly named

- [ ] **Step 2: Do a final doc-quality pass**

Check that the new addition:
- strengthens the requirement rather than merely repeating existing prose
- does not duplicate the whole concept-registry section
- does not pull implementation-plan detail back into the doc
- remains consistent with the rest of `GOLDEN_SET.md`

If any issue is present, fix it immediately.

- [ ] **Step 3: Commit the hard-rule restoration**

```bash
git add GOLDEN_SET.md docs/superpowers/specs/2026-04-09-golden-versioned-config-rule-design.md docs/superpowers/plans/2026-04-09-golden-versioned-config-rule.md
git commit -m "docs: restore versioned config rule in golden set spec"
```

---

## Self-review

Spec coverage check:
- restore hard-rule strength: covered in Task 1 Steps 2-5
- keep scope narrow: covered in Task 1 Steps 3-4
- verify the requirement is now explicit: covered in Task 2

Placeholder scan:
- No TBD/TODO placeholders remain.
- All targets and verification commands are explicit.

Type / terminology consistency:
- `GOLDEN_SET.md` remains the only modified authority doc.
- The restored rule consistently uses “versioned config and tests” as the authoritative executable source.
