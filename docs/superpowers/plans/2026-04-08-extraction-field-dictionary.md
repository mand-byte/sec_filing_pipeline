# Extraction Field Dictionary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reshape `EXTRACTION_FIELDS.md` into the single authoritative field-dictionary document so it defines what to extract, not how extraction or strict evaluation works.

**Architecture:** Keep `EXTRACTION_FIELDS.md` as the surviving field-dictionary file and preserve the route-by-route field inventory, field grain, form applicability, semantic aliases, and snippet schemas. Remove or compress method and evaluation detail so the file delegates extraction execution to `EXTRACTION_METHOD.md` and truth/evaluation policy to `GOLDEN_SET.md`.

**Tech Stack:** Markdown, repo docs, grep-based verification

---

## File structure

### Modify
- `EXTRACTION_FIELDS.md` — rewrite into the authoritative field-dictionary document

### Keep for reference during edit only
- `EXTRACTION_METHOD.md` — authority doc for extraction/routing/correctness details
- `GOLDEN_SET.md` — authority doc for truth/evaluation details
- `docs/superpowers/specs/2026-04-08-extraction-field-dictionary-design.md` — approved field-dictionary design

---

### Task 1: Rewrite `EXTRACTION_FIELDS.md` as the field-dictionary authority doc

**Files:**
- Modify: `EXTRACTION_FIELDS.md`
- Reference: `EXTRACTION_METHOD.md`
- Reference: `GOLDEN_SET.md`
- Reference: `docs/superpowers/specs/2026-04-08-extraction-field-dictionary-design.md`

- [ ] **Step 1: Read the current field doc against the authority-doc boundaries**

Read:
- `EXTRACTION_FIELDS.md`
- `EXTRACTION_METHOD.md`
- `GOLDEN_SET.md`
- `docs/superpowers/specs/2026-04-08-extraction-field-dictionary-design.md`

Confirm the future role of `EXTRACTION_FIELDS.md`:
- it answers what fields exist, what they mean, which forms they apply to, and what grain they live at
- it does not own extraction routing, extractor choice, truth tiers, or strict evaluation rules

- [ ] **Step 2: Add an authoritative field-dictionary framing at the top**

Rewrite the opening so it clearly states:
- this is the single authoritative field-dictionary document
- it defines “what to extract,” not “how to extract” or “how to evaluate truth”
- extraction method details belong in `EXTRACTION_METHOD.md`
- truth/evaluation details belong in `GOLDEN_SET.md`

Use wording equivalent to:

```markdown
# Extraction Field Dictionary (Authoritative Specification)

This document is the single authoritative field dictionary for the SEC filing extraction system. It defines canonical fields, field grain, form applicability, semantic meaning, and snippet-output schemas. Extraction routing, extractor selection, correctness engineering, and strict truth/evaluation policy belong in `EXTRACTION_METHOD.md` and `GOLDEN_SET.md`.
```

- [ ] **Step 3: Keep only field-dictionary-safe common conventions**

Preserve and clean up common conventions that belong in a field dictionary, such as:
- common metadata is maintained separately and should not be repeated per field row
- numeric fields are limited to directly storable/monitorable values
- compact schema notation for snippet outputs (`number`, `enum[...]`, `boolean`, etc.)

Do not add method or evaluation commentary here.

- [ ] **Step 4: Preserve the route-by-route numeric and snippet dictionaries**

Keep the major field-dictionary sections, reorganized if needed for clarity:
- issuer route numeric fields
- issuer route snippet fields
- owner route numeric fields
- owner route snippet fields
- holdings route numeric fields
- holdings route snippet fields

For each dictionary table, preserve these kinds of columns/info:
- canonical field name
- grain
- applicable forms
- “possible labels / corresponding wording in filings” or equivalent field semantics
- snippet JSON schema for snippet-type fields

- [ ] **Step 5: Preserve grain definitions, but only as field-grain definitions**

Keep useful grain labels such as:
- `document`
- `security_line`
- `proposal_line`
- `exec_line`
- `holder_line`
- `transaction_line`
- `position_line`

If needed, add a brief field-grain explanation section, but do **not** drift into golden-set subject identity, uniqueness constraints, or strict schema design.

- [ ] **Step 6: Keep amendment overlay fields only if they still belong in the field dictionary**

If the `/A` overlay fields are still useful as field definitions, keep them as a compact appendix or final section.

If kept, they should be presented only as shared field definitions, not as evaluation or amendment-handling policy.

- [ ] **Step 7: Remove or compress out-of-bound content**

Remove from `EXTRACTION_FIELDS.md` any material that belongs to the method or golden docs, including:
- extractor selection advice
- routing / fallback / QA-gate logic
- truth-source ranking
- Gold / Silver / Invariant descriptions
- strict golden-set schema / metrics / phase gates
- cold-start / review-queue / error-loop explanations

If a sentence mixes field semantics with method detail, keep only the field-semantic part.

- [ ] **Step 8: Add a short document-boundary note**

Add one brief section or note that distinguishes:
- `DEMANDS.md` → total architecture / requirements
- `EXTRACTION_METHOD.md` → extraction execution / routing / correctness engineering
- `EXTRACTION_FIELDS.md` → field dictionary
- `GOLDEN_SET.md` → truth / evaluation

Keep it short and purely as a boundary reminder.

- [ ] **Step 9: Verify the file still works as a field dictionary**

Read the final `EXTRACTION_FIELDS.md` and confirm a reader can answer:
- which fields exist
- what each field means
- what grain each field belongs to
- which forms each field applies to
- what snippet output schema is expected

without needing method/evaluation detail to understand the dictionary itself.

---

### Task 2: Verify that `EXTRACTION_FIELDS.md` no longer acts like a method/eval doc

**Files:**
- Verify: `EXTRACTION_FIELDS.md`
- Reference: `EXTRACTION_METHOD.md`
- Reference: `GOLDEN_SET.md`

- [ ] **Step 1: Run field-dictionary boundary grep checks**

Run:

```bash
grep -n "EXTRACTION_METHOD\.md\|GOLDEN_SET\.md" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/EXTRACTION_FIELDS.md"
grep -n "ObjPathExtractor\|XbrlConceptExtractor\|XmlPathExtractor\|AnchoredTableExtractor\|AnchoredSpanExtractor\|LlmSpanNormalizer\|cold_start_review_gate\|error_code\|golden_case\|patch" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/EXTRACTION_FIELDS.md" || true
grep -n "Gold\|Silver\|Invariant\|truth_tier\|gold_strict_accuracy\|silver_alignment\|invariant_pass_rate\|golden_truth\|golden_eval_run" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/EXTRACTION_FIELDS.md" || true
```

Expected:
- the doc may link to `EXTRACTION_METHOD.md` and `GOLDEN_SET.md`
- method/evaluation implementation terms should not dominate the file
- the file should no longer read like an extraction-method doc or golden-set doc

- [ ] **Step 2: Do a final doc-quality pass**

Check `EXTRACTION_FIELDS.md` for these failures:
- still reads like a method doc
- still reads like an evaluation doc
- lost too much field/grain/form information
- snippet schemas got removed or degraded
- field-grain explanations became schema/evaluation explanations

If any are present, fix them immediately.

- [ ] **Step 3: Commit the field-dictionary consolidation**

```bash
git add EXTRACTION_FIELDS.md docs/superpowers/specs/2026-04-08-extraction-field-dictionary-design.md docs/superpowers/plans/2026-04-08-extraction-field-dictionary.md
git commit -m "docs: clarify extraction field dictionary role"
```

---

## Self-review

Spec coverage check:
- field dictionary becomes authoritative: covered in Task 1 Steps 2 and 9
- preserve canonical field/grain/form/schema content: covered in Task 1 Steps 3-6
- remove method/eval responsibility: covered in Task 1 Step 7
- keep boundaries clear across docs: covered in Task 1 Step 8 and Task 2 Step 1

Placeholder scan:
- No TBD/TODO placeholders remain.
- All targets and verification commands are explicit.

Type / terminology consistency:
- `EXTRACTION_FIELDS.md` remains the field-dictionary authority doc.
- `EXTRACTION_METHOD.md` remains the method doc.
- `GOLDEN_SET.md` remains the truth/evaluation doc.
