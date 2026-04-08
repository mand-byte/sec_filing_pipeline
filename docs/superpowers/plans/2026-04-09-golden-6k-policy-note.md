# Golden Set 6-K Policy Note Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a short policy note to `GOLDEN_SET.md` that explicitly distinguishes generic `6-K` from `6-K-financial` in the strict numeric truth/evaluation model.

**Architecture:** Make a minimal, single-file documentation change in `GOLDEN_SET.md`. Add one concise policy note near the filing-family / source-policy sections so the method doc, field dictionary, and golden-set spec all align on when 6-K cases do or do not enter the statement-style numeric truth path.

**Tech Stack:** Markdown docs, grep-based verification

---

## File structure

### Modify
- `GOLDEN_SET.md` — add a short 6-K policy note

### Keep for reference during edit only
- `EXTRACTION_METHOD.md` — already defines `6-K-financial` as the canonical statement-style 6-K form family
- `EXTRACTION_FIELDS.md` — already uses `6-K-financial` in field applicability
- `docs/superpowers/specs/2026-04-09-golden-6k-policy-note-design.md` — approved design

---

### Task 1: Add the 6-K policy note to `GOLDEN_SET.md`

**Files:**
- Modify: `GOLDEN_SET.md`
- Reference: `EXTRACTION_METHOD.md`
- Reference: `EXTRACTION_FIELDS.md`
- Reference: `docs/superpowers/specs/2026-04-09-golden-6k-policy-note-design.md`

- [ ] **Step 1: Read the current 6-K usage across the three authority docs**

Read:
- `GOLDEN_SET.md`
- `EXTRACTION_METHOD.md`
- `EXTRACTION_FIELDS.md`
- `docs/superpowers/specs/2026-04-09-golden-6k-policy-note-design.md`

Confirm the current gap:
- method and field docs distinguish `6-K-financial`
- `GOLDEN_SET.md` does not yet explicitly state how generic `6-K` vs `6-K-financial` behave in strict numeric truth/evaluation

- [ ] **Step 2: Add one short policy note near the filing-family / source-policy sections**

Add wording equivalent to:

```markdown
**6-K policy note:** `6-K` is not treated as a default periodic numeric-truth filing family. Only `6-K-financial` cases with explicit financial statements or financial exhibits enter the statement-style numeric truth and evaluation path. Event-style `6-K` disclosures remain current-report / narrative cases unless a field is explicitly modeled otherwise.
```

- [ ] **Step 3: Place the note where it naturally clarifies policy**

Insert it near one of these existing sections:
- `Channel types by filing family`
- `Truth source reliability ranking`

The note should feel like a policy clarification, not a new large section.

- [ ] **Step 4: Keep the scope narrow**

Ensure the new note does **not**:
- add 6-K extraction-method detail already owned by `EXTRACTION_METHOD.md`
- add subject-mapping rules already handled elsewhere
- redefine truth tiers
- expand into a new filing-family taxonomy section

- [ ] **Step 5: Verify the ambiguity is reduced**

Read the updated `GOLDEN_SET.md` and confirm a reader can now infer:
- generic `6-K` is not automatically part of the periodic numeric truth path
- `6-K-financial` is the statement-style exception
- event-style `6-K` stays outside that default numeric truth/eval path unless explicitly modeled

---

### Task 2: Verify the 6-K policy note is present and aligned

**Files:**
- Verify: `GOLDEN_SET.md`
- Reference: `EXTRACTION_METHOD.md`
- Reference: `EXTRACTION_FIELDS.md`

- [ ] **Step 1: Run focused grep checks**

Run:

```bash
grep -n "6-K policy note\|6-K-financial\|Event-style `6-K`\|statement-style numeric truth" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/GOLDEN_SET.md"
```

Expected:
- the new note is present
- `6-K-financial` is explicitly named in `GOLDEN_SET.md`

- [ ] **Step 2: Do a final doc-quality pass**

Check that the note:
- is short
- is policy-oriented
- aligns with `EXTRACTION_METHOD.md`
- aligns with `EXTRACTION_FIELDS.md`
- does not overreach into method details

If any issue is present, fix it immediately.

- [ ] **Step 3: Commit the 6-K clarification**

```bash
git add GOLDEN_SET.md docs/superpowers/specs/2026-04-09-golden-6k-policy-note-design.md docs/superpowers/plans/2026-04-09-golden-6k-policy-note.md
git commit -m "docs: clarify 6-K policy in golden set spec"
```

---

## Self-review

Spec coverage check:
- add the 6-K policy note: covered in Task 1 Step 2
- place it near the relevant policy sections: covered in Task 1 Step 3
- keep scope narrow: covered in Task 1 Step 4
- verify ambiguity is reduced: covered in Task 1 Step 5 and Task 2

Placeholder scan:
- No TBD/TODO placeholders remain.
- All targets and verification commands are explicit.

Type / terminology consistency:
- `EXTRACTION_METHOD.md` remains the source of extraction/routing detail.
- `EXTRACTION_FIELDS.md` remains the source of field applicability.
- `GOLDEN_SET.md` remains the truth/evaluation policy doc.
