# Spec/Plan Filename Reference Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update spec/plan history docs so they use `EXTRACTION_FIELDS.md` whenever they refer to the current field-dictionary authority filename, without changing the underlying historical narrative.

**Architecture:** This is a narrow historical-reference cleanup. Touch only `docs/superpowers/specs/*.md` and `docs/superpowers/plans/*.md` entries that still present `EXTRACTION_FIELDS.md` as the current authority doc name. Do not reopen broader wording, and do not touch unrelated historical references like `EXTRACTOR_CORRECTNESS.md` or `GOLDEN_SET_PLAN.md`.

**Tech Stack:** Markdown docs, grep-based verification

---

## File structure

### Modify
- `docs/superpowers/specs/2026-04-08-extraction-field-dictionary-design.md`
- `docs/superpowers/specs/2026-04-08-doc-cleanup-bundle-design.md`
- `docs/superpowers/specs/2026-04-08-repo-doc-boundary-audit-design.md`
- `docs/superpowers/plans/2026-04-08-extraction-field-dictionary.md`
- `docs/superpowers/plans/2026-04-08-doc-cleanup-bundle.md`
- `docs/superpowers/plans/2026-04-08-repo-doc-boundary-audit.md`

### Do not modify
- Root shipped docs (`DEMANDS.md`, `EXTRACTION_METHOD.md`, `EXTRACTION_FIELDS.md`, `GOLDEN_SET.md`)
- Historical references to other removed docs unless they are about the field-dictionary filename specifically

---

### Task 1: Update spec/plan references from `EXTRACTION_FIELDS.md` to `EXTRACTION_FIELDS.md`

**Files:**
- Modify: `docs/superpowers/specs/2026-04-08-extraction-field-dictionary-design.md`
- Modify: `docs/superpowers/specs/2026-04-08-doc-cleanup-bundle-design.md`
- Modify: `docs/superpowers/specs/2026-04-08-repo-doc-boundary-audit-design.md`
- Modify: `docs/superpowers/plans/2026-04-08-extraction-field-dictionary.md`
- Modify: `docs/superpowers/plans/2026-04-08-doc-cleanup-bundle.md`
- Modify: `docs/superpowers/plans/2026-04-08-repo-doc-boundary-audit.md`

- [ ] **Step 1: Find all residual old-name references in specs/plans**

Run:

```bash
grep -n "EXTRACTION_FILED\.md" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/docs/superpowers"/**/*.md
```

Expected: matches appear only in specs/plans and represent old references to the field-dictionary authority filename.

- [ ] **Step 2: Update the extraction-field-dictionary design spec**

In `docs/superpowers/specs/2026-04-08-extraction-field-dictionary-design.md`, replace references that present the field-dictionary authority doc as `EXTRACTION_FIELDS.md` with `EXTRACTION_FIELDS.md`.

Examples to update:
- title line
- goal section
- boundary section
- acceptance criteria

Preserve historical meaning; only modernize the authority filename.

- [ ] **Step 3: Update the cleanup-bundle design spec**

In `docs/superpowers/specs/2026-04-08-doc-cleanup-bundle-design.md`, replace old-name references where the spec discusses the current field-dictionary authority doc or the rename target.

Keep the historical narrative intact, but make the current target name consistent with `EXTRACTION_FIELDS.md`.

- [ ] **Step 4: Update the repo-boundary audit design spec**

In `docs/superpowers/specs/2026-04-08-repo-doc-boundary-audit-design.md`, replace any old-name references that describe the present authority-doc set.

For example, if it lists the four current authority docs, it should now list `EXTRACTION_FIELDS.md` instead of `EXTRACTION_FIELDS.md`.

- [ ] **Step 5: Update the extraction-field-dictionary implementation plan**

In `docs/superpowers/plans/2026-04-08-extraction-field-dictionary.md`, replace old-name references so the plan reflects the final authority filename as `EXTRACTION_FIELDS.md`.

Keep the plan’s history readable; only modernize the filename.

- [ ] **Step 6: Update the cleanup-bundle implementation plan**

In `docs/superpowers/plans/2026-04-08-doc-cleanup-bundle.md`, replace old-name references so the plan no longer presents `EXTRACTION_FIELDS.md` as the current authority doc.

This includes:
- rename descriptions
- command examples if they should now refer to the already-renamed current file
- acceptance criteria

When an old command is shown purely as a historical step in the rename, keep the history understandable but do not leave ambiguity about the current filename.

- [ ] **Step 7: Update the repo-boundary audit plan**

In `docs/superpowers/plans/2026-04-08-repo-doc-boundary-audit.md`, replace old-name references when the plan is describing the present authority-doc set or current naming issues.

- [ ] **Step 8: Verify no spec/plan still presents the old filename as current**

Run:

```bash
grep -n "EXTRACTION_FILED\.md" "/Users/weihu/Coding/QuantSystem/sec_filing-pipeline/docs/superpowers"/**/*.md || true
```

Expected:
- either no matches remain
- or only narrowly justified historical command/context lines remain, with no ambiguity that `EXTRACTION_FIELDS.md` is the current filename

---

### Task 2: Verify that live authority docs remain untouched and the cleanup stayed narrow

**Files:**
- Verify: `DEMANDS.md`
- Verify: `EXTRACTION_FIELDS.md`
- Verify: `EXTRACTION_METHOD.md`
- Verify: `GOLDEN_SET.md`

- [ ] **Step 1: Confirm the live authority docs were not changed by this cleanup**

Run:

```bash
grep -n "EXTRACTION_FIELDS\.md\|EXTRACTION_FILED\.md" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline"/*.md
```

Expected:
- root shipped docs still show the already-correct current references
- no new drift was introduced into shipped docs

- [ ] **Step 2: Do a final quality pass on the specs/plans**

Check for these failures:
- history became inaccurate or confusing
- old filename still appears as if current
- changed wording accidentally implies more than a filename cleanup
- unrelated legacy docs were altered even though they were out of scope

If any are present, fix them immediately.

- [ ] **Step 3: Commit the spec/plan filename-reference cleanup**

```bash
git add docs/superpowers/specs/2026-04-08-extraction-field-dictionary-design.md docs/superpowers/specs/2026-04-08-doc-cleanup-bundle-design.md docs/superpowers/specs/2026-04-08-repo-doc-boundary-audit-design.md docs/superpowers/plans/2026-04-08-extraction-field-dictionary.md docs/superpowers/plans/2026-04-08-doc-cleanup-bundle.md docs/superpowers/plans/2026-04-08-repo-doc-boundary-audit.md
git commit -m "docs: update historical field dictionary references"
```

---

## Self-review

Spec coverage check:
- update old filename references in specs/plans: covered in Task 1
- keep historical meaning intact: covered in Task 1 Steps 2-7 and Task 2 Step 2
- do not touch live authority docs unnecessarily: covered in Task 2 Step 1

Placeholder scan:
- No TBD/TODO placeholders remain.
- All targets and verification commands are explicit.

Type / terminology consistency:
- `EXTRACTION_FIELDS.md` is the current authority filename throughout.
- `EXTRACTION_FIELDS.md` should no longer appear as the current authority doc name after cleanup.
