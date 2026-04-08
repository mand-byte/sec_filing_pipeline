# Repository-Wide Documentation Boundary Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a structured, report-only documentation-boundary audit for the repository so the user can see the remaining naming, boundary, reference, and noise issues without changing any files.

**Architecture:** Audit the current top-level authority docs first, then inspect secondary noise sources such as specs, plans, worktrees, and cache docs to separate real issues from audit noise. The final output should be a concise issue list grouped by category with location, impact, recommendation, and whether action is actually needed.

**Tech Stack:** Markdown docs, grep/glob/read, report-only analysis

---

## File structure

### Read / inspect
- `DEMANDS.md`
- `EXTRACTION_METHOD.md`
- `EXTRACTION_FIELDS.md`
- `GOLDEN_SET.md`
- `docs/superpowers/specs/*.md`
- `docs/superpowers/plans/*.md`
- `.claude/worktrees/**/*.md`
- `.pytest_cache/README.md`

### No file modifications
- This audit is report-only. Do not edit, create, delete, or rename repository files as part of the audit itself.

---

### Task 1: Audit the four primary authority docs for real boundary issues

**Files:**
- Verify: `DEMANDS.md`
- Verify: `EXTRACTION_METHOD.md`
- Verify: `EXTRACTION_FIELDS.md`
- Verify: `GOLDEN_SET.md`

- [ ] **Step 1: Read the four authority docs in full**

Read:
- `DEMANDS.md`
- `EXTRACTION_METHOD.md`
- `EXTRACTION_FIELDS.md`
- `GOLDEN_SET.md`

Capture for each doc:
- current role
- current boundary statement (if any)
- what it does well
- any remaining overlaps with the other three docs

- [ ] **Step 2: Check naming consistency across the four authority docs**

Inspect for:
- filename issues (especially whether `EXTRACTION_FIELDS.md` looks like a legacy typo)
- inconsistent route / field / form-family naming
- same concept described with multiple names in different docs

Output should identify only real inconsistencies, not stylistic differences with no maintenance impact.

- [ ] **Step 3: Check document-boundary clarity across the four authority docs**

Evaluate whether:
- `DEMANDS.md` still contains too much method or evaluation detail
- `EXTRACTION_METHOD.md` still contains too much field-dictionary or truth/evaluation detail
- `EXTRACTION_FIELDS.md` still contains too much method/evaluation content
- `GOLDEN_SET.md` still contains too much implementation-method detail

For each issue found, record exact lines/sections and explain why it is a boundary problem.

- [ ] **Step 4: Check for real stale references among shipped root docs**

Run focused searches across the root markdown docs for:
- deleted / retired docs such as `EXTRACTOR_CORRECTNESS.md` and `GOLDEN_SET_PLAN.md`
- links that should point to authority docs but still point elsewhere

Only flag references in shipped root docs (`*.md` at repo root). Do not count spec/plan history as shipped-doc errors.

- [ ] **Step 5: Summarize real issues from the authority-doc pass**

Prepare a categorized draft under:
- Naming inconsistencies
- Boundary blur
- Stale references

For each item include:
- location
- why it matters
- whether action is recommended
- suggested next move

---

### Task 2: Audit non-authority docs as noise sources, not as primary errors

**Files:**
- Verify: `docs/superpowers/specs/*.md`
- Verify: `docs/superpowers/plans/*.md`
- Verify: `.claude/worktrees/**/*.md`
- Verify: `.pytest_cache/README.md`

- [ ] **Step 1: Identify audit-noise sources that can confuse grep/glob results**

Inspect whether these sources can pollute future searches or human reading:
- `.claude/worktrees/**/*.md`
- `docs/superpowers/specs/*.md`
- `docs/superpowers/plans/*.md`
- `.pytest_cache/README.md`

Do not treat historical references in specs/plans as shipped-doc failures by default.

- [ ] **Step 2: Separate “expected history” from “confusing noise”**

Classify findings into:
- expected and acceptable history (for example, spec/plan documents mentioning removed docs)
- confusing noise that could affect future maintenance (for example, worktree copies showing removed docs and inflating grep results)

- [ ] **Step 3: Record temporary-view pollution findings**

Create a short issue list for:
- `.claude/worktrees/**` residual copies affecting search results
- any cache/readme files that show up in doc searches but are not relevant
- spec/plan history that is benign but should not be mistaken for live-doc errors

These should be reported as audit-noise items, not as primary documentation failures.

---

### Task 3: Produce the final structured issue report

**Files:**
- Input: findings from Tasks 1-2
- Output: final response only (no file write required)

- [ ] **Step 1: Organize findings into the five agreed categories**

Final report sections:
- Naming inconsistencies
- Boundary blur
- Stale references
- Temporary / worktree view pollution
- Optional cleanup items

- [ ] **Step 2: Keep the report concise and decision-oriented**

For each issue include:
- what the issue is
- where it is
- why it counts as a problem
- whether it should actually be fixed
- recommended action

Do not include speculative complaints or historical references that are not actionable.

- [ ] **Step 3: Explicitly distinguish real doc issues from audit noise**

The final report must make clear:
- which items are real problems in authority/shipped docs
- which items are expected history or worktree/search noise

- [ ] **Step 4: Deliver the report without modifying any files**

Return the report directly to the user. Do not edit, delete, or create files as part of the audit output.

---

## Self-review

Spec coverage check:
- report-only scope: covered in file structure and Task 3 Step 4
- authority docs audited first: covered in Task 1
- specs/plans/worktrees treated as noise sources: covered in Task 2
- five-category output: covered in Task 3 Step 1
- each issue includes location/impact/recommendation: covered in Task 1 Step 5 and Task 3 Step 2

Placeholder scan:
- No TBD/TODO placeholders remain.
- All audit targets and output requirements are explicit.

Type / terminology consistency:
- “authority docs” refers only to `DEMANDS.md`, `EXTRACTION_METHOD.md`, `EXTRACTION_FIELDS.md`, and `GOLDEN_SET.md`.
- “audit noise” refers to specs, plans, worktrees, and cache docs unless a real shipped-doc issue is found there.
