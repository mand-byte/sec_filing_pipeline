# Documentation Cleanup Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the remaining documentation cleanup by renaming the field-dictionary authority file, removing obsolete local worktree noise, and tightening a few remaining field-definition semantics.

**Architecture:** Treat this as a bundled cleanup with three tightly related parts: (1) rename the authority field-dictionary doc from `EXTRACTION_FIELDS.md` to `EXTRACTION_FIELDS.md` and update all live references, (2) remove obsolete `.claude/worktrees` snapshots that pollute searches, and (3) make a few semantic edits in the field dictionary so definitions read like field definitions rather than normalization logic. Keep the existing four-document architecture intact.

**Tech Stack:** Markdown docs, repo file renames, filesystem cleanup, grep-based verification

---

## File structure

### Modify
- `DEMANDS.md` — update the field-dictionary reference to the renamed file
- `EXTRACTION_FIELDS.md` — the renamed field-dictionary authority doc, with minor semantic tightening

### Rename
- `EXTRACTION_FIELDS.md` → `EXTRACTION_FIELDS.md`

### Remove
- `.claude/worktrees/agent-af5daa96/`
- `.claude/worktrees/agent-a30b8e49/`

### Keep for reference during edit only
- `EXTRACTION_METHOD.md`
- `GOLDEN_SET.md`
- `docs/superpowers/specs/2026-04-08-doc-cleanup-bundle-design.md`

---

### Task 1: Rename the field-dictionary authority doc and update live references

**Files:**
- Rename: `EXTRACTION_FIELDS.md` → `EXTRACTION_FIELDS.md`
- Modify: `DEMANDS.md`
- Modify: `EXTRACTION_FIELDS.md`

- [ ] **Step 1: Verify the current field-dictionary authority file exists before renaming**

Run:

```bash
ls "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/EXTRACTION_FIELDS.md"
```

Expected: the file exists.

- [ ] **Step 2: Rename the field-dictionary file**

Run:

```bash
mv "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/EXTRACTION_FIELDS.md" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/EXTRACTION_FIELDS.md"
```

Expected: old path no longer exists; new path exists.

- [ ] **Step 3: Update `DEMANDS.md` to point to the renamed field-dictionary doc**

Change this line:

```markdown
- **目标清单与字段**：本期重点突破核心的 53 个确定性数值字段以及特定锚区中的大段文本。详见 [EXTRACTION_FIELDS.md](./EXTRACTION_FIELDS.md)。
```

To this:

```markdown
- **目标清单与字段**：本期重点突破核心的 53 个确定性数值字段以及特定锚区中的大段文本。详见 [EXTRACTION_FIELDS.md](./EXTRACTION_FIELDS.md)。
```

- [ ] **Step 4: Update the renamed field-dictionary doc’s self-reference and boundary table**

In `EXTRACTION_FIELDS.md`, update:
- the title if needed so it no longer refers to `EXTRACTION_FIELDS.md`
- the boundary table row to use `EXTRACTION_FIELDS.md` as the field-dictionary authority doc
- any remaining internal self-references or wording that still says `EXTRACTION_FIELDS.md`

Use wording equivalent to:

```markdown
| `EXTRACTION_FIELDS.md` (this doc) | Field dictionary — defines what fields to extract |
```

- [ ] **Step 5: Verify all live references now use the new filename**

Run:

```bash
grep -n "EXTRACTION_FILED\.md\|EXTRACTION_FIELDS\.md" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline"/*.md
```

Expected:
- root shipped docs reference `EXTRACTION_FIELDS.md`
- no root shipped docs still reference `EXTRACTION_FIELDS.md`

---

### Task 2: Tighten the remaining field-definition semantics in `EXTRACTION_FIELDS.md`

**Files:**
- Modify: `EXTRACTION_FIELDS.md`

- [ ] **Step 1: Read the renamed field-dictionary doc and identify the few remaining semantics to tighten**

Focus on the known weak spots:
- `filing_delay_days`
- `proposal_votes_against`
- any entries that still read like a derivation rule rather than a field definition

- [ ] **Step 2: Keep the schema-notation section aligned with actual notation usage**

Ensure the “Schema notation” line still explicitly covers the notation used in the file, including:
- `number`
- `integer`
- `boolean`
- `string[]`
- `number[0,5]`
- `number|null`
- `number[0,5]|null`
- `enum[...]`

- [ ] **Step 3: Keep `filing_delay_days` as a field definition, not an extraction recipe**

Ensure the `filing_delay_days` row uses wording equivalent to:

```markdown
Days between statutory deadline and expected filing date per delay notification
```

Do not let this cell drift back into derivation/extraction instructions.

- [ ] **Step 4: Keep `proposal_votes_against` semantically safe**

Ensure the `proposal_votes_against` row does not imply that `Withheld` is universally identical to `Against` without qualification.

Use wording equivalent to:

```markdown
`Votes Against` (normalized from Against + Withheld where applicable)
```

Or an equally safe/explicit caveat.

- [ ] **Step 5: Keep the 6-K naming aligned with the method doc**

In `EXTRACTION_FIELDS.md`, ensure the financial-statement-style 6-K rows use `6-K-financial` consistently where applicable, so they remain aligned with `EXTRACTION_METHOD.md`.

- [ ] **Step 6: Verify the file still reads as a field dictionary**

Read `EXTRACTION_FIELDS.md` and confirm it still answers:
- what fields exist
- what they mean
- which forms they apply to
- what grain they use
- what snippet schemas they emit

and does not drift back into method or evaluation responsibility.

---

### Task 3: Remove obsolete local worktree noise

**Files:**
- Remove: `.claude/worktrees/agent-af5daa96/`
- Remove: `.claude/worktrees/agent-a30b8e49/`

- [ ] **Step 1: Verify the two worktree directories exist and are obsolete**

Run:

```bash
ls -d "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/.claude/worktrees/agent-af5daa96" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/.claude/worktrees/agent-a30b8e49"
```

Confirm they exist and that their relevant doc changes have already been reflected in the main working tree before deleting them.

- [ ] **Step 2: Remove the obsolete worktree directories**

Run:

```bash
rm -rf "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/.claude/worktrees/agent-af5daa96" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/.claude/worktrees/agent-a30b8e49"
```

Expected: both directories are gone.

- [ ] **Step 3: Verify search noise is reduced**

Run:

```bash
grep -n "EXTRACTOR_CORRECTNESS\.md\|GOLDEN_SET_PLAN\.md" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/.claude/worktrees"/**/*.md || true
```

Expected: no matches, or the directory itself no longer exists.

---

### Task 4: Run final bundled verification

**Files:**
- Verify: `DEMANDS.md`
- Verify: `EXTRACTION_FIELDS.md`
- Verify: `.claude/worktrees/`

- [ ] **Step 1: Run final reference and boundary checks**

Run:

```bash
grep -n "EXTRACTION_FILED\.md\|EXTRACTION_FIELDS\.md" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline"/*.md
grep -n "ObjPathExtractor\|XbrlConceptExtractor\|XmlPathExtractor\|AnchoredTableExtractor\|AnchoredSpanExtractor\|LlmSpanNormalizer\|cold_start_review_gate\|error_code\|golden_case\|patch" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/EXTRACTION_FIELDS.md" || true
grep -n "Gold\|Silver\|Invariant\|truth_tier\|gold_strict_accuracy\|silver_alignment\|invariant_pass_rate\|golden_truth\|golden_eval_run" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/EXTRACTION_FIELDS.md" || true
```

Expected:
- root shipped docs reference `EXTRACTION_FIELDS.md`, not `EXTRACTION_FIELDS.md`
- `EXTRACTION_FIELDS.md` still does not read like a method/eval doc

- [ ] **Step 2: Do a final doc-quality pass**

Check for these failures:
- the renamed file still contains the old filename in self-references
- field-dictionary semantics became weaker or less clear after renaming
- worktree noise still dominates searches
- the rename broke document-boundary clarity

If any are present, fix them immediately.

- [ ] **Step 3: Commit the bundled cleanup**

```bash
git add DEMANDS.md EXTRACTION_FIELDS.md docs/superpowers/specs/2026-04-08-doc-cleanup-bundle-design.md docs/superpowers/plans/2026-04-08-doc-cleanup-bundle.md
git rm EXTRACTION_FIELDS.md
rm -rf .claude/worktrees/agent-af5daa96 .claude/worktrees/agent-a30b8e49
git commit -m "docs: finalize documentation cleanup bundle"
```

---

## Self-review

Spec coverage check:
- rename field-dictionary file: covered in Task 1
- update live references: covered in Task 1 Steps 3-5
- clean worktree noise: covered in Task 3
- tighten semantic field definitions: covered in Task 2
- preserve overall four-doc architecture: covered in Task 4 Step 2

Placeholder scan:
- No TBD/TODO placeholders remain.
- All targets and verification commands are explicit.

Type / terminology consistency:
- The renamed field-dictionary authority doc is `EXTRACTION_FIELDS.md` throughout.
- `EXTRACTION_METHOD.md` remains the method doc.
- `GOLDEN_SET.md` remains the truth/evaluation doc.
