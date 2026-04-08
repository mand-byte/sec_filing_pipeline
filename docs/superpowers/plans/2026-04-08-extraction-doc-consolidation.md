# Extraction Documentation Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate extraction-method documentation so `EXTRACTION_METHOD.md` becomes the single authoritative extraction document and `EXTRACTOR_CORRECTNESS.md` is removed.

**Architecture:** Keep `EXTRACTION_METHOD.md` as the surviving document, merge in the durable correctness-engineering content from `EXTRACTOR_CORRECTNESS.md`, and trim overlap with `DEMANDS.md` and `GOLDEN_SET.md`. Then update references and remove `EXTRACTOR_CORRECTNESS.md` so extraction guidance lives in one place only.

**Tech Stack:** Markdown, repo docs, grep-based verification

---

## File structure

### Modify
- `EXTRACTION_METHOD.md` — rewrite into the single extraction-method authority doc
- `DEMANDS.md` — update extraction-doc references so it points only to `EXTRACTION_METHOD.md`

### Delete
- `EXTRACTOR_CORRECTNESS.md` — remove after its durable content has been merged into `EXTRACTION_METHOD.md`

### Keep for reference during rewrite only
- `docs/superpowers/specs/2026-04-08-extraction-doc-consolidation-design.md` — approved consolidation design
- `GOLDEN_SET.md` — boundary reference for what must stay out of the extraction-method doc

---

### Task 1: Rewrite `EXTRACTION_METHOD.md` as the single extraction authority doc

**Files:**
- Modify: `EXTRACTION_METHOD.md`
- Reference: `EXTRACTOR_CORRECTNESS.md`
- Reference: `GOLDEN_SET.md`
- Reference: `docs/superpowers/specs/2026-04-08-extraction-doc-consolidation-design.md`

- [ ] **Step 1: Read the current extraction docs and boundary doc together**

Read:
- `EXTRACTION_METHOD.md`
- `EXTRACTOR_CORRECTNESS.md`
- `GOLDEN_SET.md`
- `docs/superpowers/specs/2026-04-08-extraction-doc-consolidation-design.md`

Confirm the merged doc must preserve:
- field registry design
- 6 extractor types
- filing-family routing
- runtime flow / QA gate / anti-bloat rules
- Tier 1 / Tier 2 / Tier 3 correctness boundaries
- cold-start phases and representative review-gate logic
- `error_code + golden_case + patch` correction loop
- why spaCy is out of scope

- [ ] **Step 2: Replace the opening with a single authoritative framing**

Rewrite the top of `EXTRACTION_METHOD.md` so it states, in one compact opening section:
- this is the single authoritative extraction-method document
- it covers extraction architecture, routing, correctness engineering, cold start, and review/error loops
- strict truth tiers and strict evaluation belong in `GOLDEN_SET.md`

Use wording equivalent to:

```markdown
# Extraction Method (Authoritative Specification)

This document is the single authoritative specification for extraction method design. It defines field registry structure, extractor routing, correctness boundaries, cold-start policy, QA/review gates, and the fix-once regression loop. Gold/Silver/Invariant truth policy and strict evaluation rules belong in `GOLDEN_SET.md`.
```

- [ ] **Step 3: Keep one consolidated core-architecture section**

Preserve exactly one place that states the core hierarchy:

```markdown
edgartools (obj/xbrl) > XML/xpath > anchored regex > LLM normalization
```

And exactly one place that states:
- spaCy is out of scope
- the core system is `edgartools + declarative registry + QA/review gate`

Delete duplicate restatements of the same conclusion elsewhere in the file.

- [ ] **Step 4: Keep the field-registry and six-extractor design as the “how we extract” core**

Ensure the doc preserves and organizes:
- declarative field-registry examples
- `ObjPathExtractor`
- `XbrlConceptExtractor`
- `XmlPathExtractor`
- `AnchoredTableExtractor`
- `AnchoredSpanExtractor`
- `LlmSpanNormalizer`

The section should answer “how the system extracts values” without drifting into golden-set truth policy.

- [ ] **Step 5: Merge in the correctness-engineering sections from `EXTRACTOR_CORRECTNESS.md`**

Add or preserve a section equivalent to:

```markdown
## Correctness boundaries by tier

### Tier 1: Deterministic extraction
- `ObjPathExtractor`
- `XbrlConceptExtractor`
- `XmlPathExtractor`
- high-confidence deterministic sources
- failure modes: API drift, wrong concept/context selection, missing object support

### Tier 2: Semi-structured extraction
- `AnchoredTableExtractor`
- `AnchoredSpanExtractor`
- risks: layout variance, missing aliases, broken anchoring, unit ambiguity

### Tier 3: LLM normalization
- only pre-cut span in, structured schema out
- risks: hallucination, schema violations, inconsistency
- mitigations: short spans, strict schema, temperature 0, consistency checks
```

Also preserve the rationale for why each tier is trusted differently and the matching mitigation patterns.

- [ ] **Step 6: Preserve filing-family routing, but trim overlap with `GOLDEN_SET.md`**

Keep practical routing guidance for:
- `10-K / 10-Q / 20-F / some 6-K`
- `8-K / 6-K events`
- `DEF 14A`
- `3 / 4 / 5`
- `13D / 13G`
- `144`
- `13F`

But rewrite it as extraction-execution guidance, not truth-tier policy. In other words:
- explain which extractor/channel to try first
- do not restate `Gold / Silver / Invariant`
- do not restate strict source-reliability ranking from `GOLDEN_SET.md` in full

- [ ] **Step 7: Preserve runtime flow, QA gate, and anti-bloat rules**

Keep:
- the `extract_field()` pseudocode or equivalent
- evidence/lineage expectations (`accession_no`, `locator_kind`, object path / concept / xpath / section, raw value, normalized value)
- anti-bloat rules such as locator-count limit, alias-count limit, short LLM spans, and “new rules must come from regression cases”

- [ ] **Step 8: Merge cold-start and review-gate content**

Bring in the durable cold-start policy from `EXTRACTOR_CORRECTNESS.md`, including:
- Phase 0 / 1 / 2 / 3 cold-start progression
- Tier 1 only first, then Tier 2, then LLM
- representative `cold_start_review_gate()` logic for:
  - first-seen issuer/field
  - first-seen template
  - major outlier vs history

The section should clearly answer: “How do we keep early automatic extraction safe?”

- [ ] **Step 9: Merge the correction loop and fix-once policy**

Add or preserve a section equivalent to:

```markdown
## Fix-once correction loop

Every manual correction must produce:
- `error_code`
- `golden_case`
- `patch`

Only generalize a fix into product logic when the error is repeated, generalizable, and low-risk. Otherwise keep it as a one-off override.
```

Also preserve the explanation of how these feed regression testing and prevent repeat failures.

- [ ] **Step 10: Add an explicit document-boundary section**

Add a short section that distinguishes:
- `DEMANDS.md` → project goals, global principles, roadmap
- `EXTRACTION_METHOD.md` → extraction architecture, routing, correctness engineering, cold start, review/error loops
- `GOLDEN_SET.md` → truth tiers, strict golden schema, evaluation, artifact contract, release gates

This section exists to prevent future doc drift.

- [ ] **Step 11: Remove duplicated or out-of-bound content**

Remove from `EXTRACTION_METHOD.md`:
- repeated copies of the same priority summary
- repeated “why not spaCy” explanations if the same point appears twice
- material that duplicates `GOLDEN_SET.md` truth-tier / strict-eval logic
- material that duplicates `DEMANDS.md` roadmap or project-goal sections

- [ ] **Step 12: Read the merged doc for self-containment**

Read `EXTRACTION_METHOD.md` and confirm a reader can answer:
- how extraction is configured
- which extractor classes exist
- how filing families route to extractors
- what each tier’s correctness boundary is
- how cold start and review gates work
- how manual corrections get folded back into regression protection

---

### Task 2: Update references and remove `EXTRACTOR_CORRECTNESS.md`

**Files:**
- Modify: `DEMANDS.md`
- Delete: `EXTRACTOR_CORRECTNESS.md`

- [ ] **Step 1: Update `DEMANDS.md` to reference only the surviving extraction doc**

Change this line in `DEMANDS.md`:

```markdown
1. **分层抽取策略**：`edgartools` (XBRL / Obj) 为绝对优先 (Tier 1) -> 定向 XML/HTML 解析次之 (Tier 2) -> 局部正则锚点兜底 -> LLM 仅作末端 JSON 序列化。禁止大模型在全文中盲猜找值，**不需要使用 spaCy**。详见 [EXTRACTION_METHOD.md](./EXTRACTION_METHOD.md) 与 [EXTRACTOR_CORRECTNESS.md](./EXTRACTOR_CORRECTNESS.md)。
```

To this:

```markdown
1. **分层抽取策略**：`edgartools` (XBRL / Obj) 为绝对优先 (Tier 1) -> 定向 XML/HTML 解析次之 (Tier 2) -> 局部正则锚点兜底 -> LLM 仅作末端 JSON 序列化。禁止大模型在全文中盲猜找值，**不需要使用 spaCy**。详见 [EXTRACTION_METHOD.md](./EXTRACTION_METHOD.md)。
```

- [ ] **Step 2: Delete `EXTRACTOR_CORRECTNESS.md`**

Remove the file entirely after confirming its durable content has been merged into `EXTRACTION_METHOD.md`.

- [ ] **Step 3: Search for stale references**

Run:

```bash
grep -n "EXTRACTOR_CORRECTNESS\.md" DEMANDS.md EXTRACTION_METHOD.md GOLDEN_SET.md || true
```

Expected:
- no remaining shipped-doc references to `EXTRACTOR_CORRECTNESS.md`

---

### Task 3: Verify the final extraction-doc consolidation

**Files:**
- Verify: `EXTRACTION_METHOD.md`
- Verify: `DEMANDS.md`

- [ ] **Step 1: Run final grep checks**

Run:

```bash
grep -n "EXTRACTOR_CORRECTNESS\.md" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline"/*.md || true
grep -n "Gold\|Silver\|Invariant" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/EXTRACTION_METHOD.md" || true
grep -n "cold_start_review_gate\|error_code\|golden_case\|patch" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/EXTRACTION_METHOD.md"
grep -n "ObjPathExtractor\|XbrlConceptExtractor\|XmlPathExtractor\|AnchoredTableExtractor\|AnchoredSpanExtractor\|LlmSpanNormalizer" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/EXTRACTION_METHOD.md"
```

Expected:
- no root shipped docs reference `EXTRACTOR_CORRECTNESS.md`
- `EXTRACTION_METHOD.md` still contains the cold-start / fix-once / extractor sections
- `EXTRACTION_METHOD.md` does not become a second `GOLDEN_SET.md`

- [ ] **Step 2: Do a final doc-quality pass**

Check `EXTRACTION_METHOD.md` for these failures:
- duplicated intro/priority sections
- duplicated spaCy rationale sections
- repeated extractor lists carried over from both docs
- too much golden-set truth-policy duplication
- loss of the correction-loop or cold-start guidance

If any are present, fix them immediately.

- [ ] **Step 3: Commit the extraction-doc consolidation**

```bash
git add EXTRACTION_METHOD.md DEMANDS.md docs/superpowers/specs/2026-04-08-extraction-doc-consolidation-design.md docs/superpowers/plans/2026-04-08-extraction-doc-consolidation.md
git rm EXTRACTOR_CORRECTNESS.md
git commit -m "docs: consolidate extraction method documentation"
```

---

## Self-review

Spec coverage check:
- single authoritative extraction doc: covered in Tasks 1-2
- preserve registry / 6 extractors / routing / runtime flow: covered in Task 1 Steps 4, 6, 7
- merge correctness engineering / cold start / review loop: covered in Task 1 Steps 5, 8, 9
- avoid overlap with `GOLDEN_SET.md` and `DEMANDS.md`: covered in Task 1 Steps 6, 10, 11
- update references and remove second doc: covered in Task 2

Placeholder scan:
- No TBD/TODO placeholders remain.
- All edit targets and grep checks are explicit.

Type / terminology consistency:
- The surviving authority doc is always `EXTRACTION_METHOD.md`.
- The removed file is always `EXTRACTOR_CORRECTNESS.md`.
- The extractor names and correction-loop terms are consistent throughout.
