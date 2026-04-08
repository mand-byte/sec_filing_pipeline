# Text Span Selection Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a compact but actionable text-span selection section to `EXTRACTION_METHOD.md` so snippet-field span sizing and adequacy are documented as method rules rather than informal intuition.

**Architecture:** Extend `EXTRACTION_METHOD.md` with one new section, `## Text span selection rules`, placed after filing-family routing and before runtime flow / QA gate. The new section should stay at the method-spec level: it will define structure-first span selection, candidate generation, scoring, adequacy signals, and retry policy using heuristics and pseudo code, without becoming a full implementation design.

**Tech Stack:** Markdown docs, pseudo code, grep-based verification

---

## File structure

### Modify
- `EXTRACTION_METHOD.md` — add a new “Text span selection rules” section

### Keep for reference during edit only
- `docs/superpowers/specs/2026-04-09-text-span-selection-rules-design.md` — approved design for the new span-rule section

---

### Task 1: Add the text-span selection rules section to `EXTRACTION_METHOD.md`

**Files:**
- Modify: `EXTRACTION_METHOD.md`
- Reference: `docs/superpowers/specs/2026-04-09-text-span-selection-rules-design.md`

- [ ] **Step 1: Read the current method doc and the approved span-rule design**

Read:
- `EXTRACTION_METHOD.md`
- `docs/superpowers/specs/2026-04-09-text-span-selection-rules-design.md`

Confirm the placement target:
- after filing-family routing
- before runtime flow / QA gate

- [ ] **Step 2: Add the new section header and core principle paragraph**

Add a section titled:

```markdown
## Text span selection rules
```

Open with a short paragraph or bullet group that clearly states:
- spans are not selected by fixed character count alone
- spans are chosen from structural anchors (item / section / table neighborhood / paragraph blocks)
- the target is the **minimum sufficient context**
- the default operational model is **0 LLM pre-screen + 1 primary LLM extraction**, with a second attempt only when the result shows the span is too small or too large

- [ ] **Step 3: Add a short structure-first segmentation rule with pseudo code**

Add a brief explanation that the document should first be segmented into reusable blocks such as:
- heading
- paragraph
- table
- footnote
- exhibit block

Add light pseudo code equivalent to:

```python
@dataclass
class Block:
    kind: str
    text: str
    heading_path: list[str]
    start_char: int
    end_char: int
```

Keep it illustrative, not implementation-complete.

- [ ] **Step 4: Add the `SpanPolicy` concept and candidate-generation rules**

Explain that snippet fields can define span policies including:
- anchor headers / items
- min / preferred / max token budget
- expand steps
- must_include / avoid patterns
- max_parallel_targets

Add light pseudo code equivalent to:

```python
@dataclass
class SpanPolicy:
    field_name: str
    anchor_headers: list[str]
    min_tokens: int
    max_tokens: int
    preferred_tokens: tuple[int, int]
    expand_steps: tuple[int, ...]
```

Then describe the flow:
- find anchor blocks
- generate multiple candidate spans
- score candidates
- choose the shortest span that still passes the adequacy bar

- [ ] **Step 5: Add the span-scoring dimensions**

Document the heuristics clearly, including:
- token length inside preferred range
- correct heading/item match
- one target object only
- presence of key terms / units / recommendation / conclusion
- penalties for multiple proposals / multiple events / multiple subjects / too many tables

Do not over-expand into production code; this should remain a method rule set.

- [ ] **Step 6: Add explicit “too small” and “too large” signals**

Add two short subsections or bullet groups:

### Too small
- missing subject identity
- missing key qualifiers / units / negation
- output becomes `unclear`
- low confidence
- missing decisive context

### Too large
- multiple target objects in one span
- multiple proposals / events / tables mixed together
- output includes irrelevant content
- repeated runs become unstable

- [ ] **Step 7: Add adequacy-check and retry policy**

Document the rule that:
- adequacy should be assessed from the first LLM output plus local heuristics
- default is one primary LLM call
- retry only when the output explicitly indicates too-small or too-large context
- the model may return helper fields such as `confidence`, `sufficient_context`, or `multiple_candidate_targets`

Include one short rule sentence equivalent to:

```markdown
Default to one main LLM call. Only expand or shrink the span and retry when the first output clearly indicates insufficient or mixed context.
```

- [ ] **Step 8: Add a short boundary note**

State explicitly that:
- this span-selection section belongs in `EXTRACTION_METHOD.md`
- field definitions remain in `EXTRACTION_FIELDS.md`
- truth/evaluation rules remain in `GOLDEN_SET.md`

Keep it short.

- [ ] **Step 9: Verify the new section remains semi-implementation, not full implementation**

Read the final `EXTRACTION_METHOD.md` and confirm the new section:
- is more concrete than pure prose
- is less detailed than a code implementation spec
- gives enough guidance to build span logic consistently
- does not introduce new modules or file-path commitments

---

### Task 2: Verify the text-span section is present, scoped correctly, and useful

**Files:**
- Verify: `EXTRACTION_METHOD.md`

- [ ] **Step 1: Run focused grep checks**

Run:

```bash
grep -n "Text span selection rules\|minimum sufficient context\|SpanPolicy\|Too small\|Too large\|sufficient_context\|multiple_candidate_targets" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/EXTRACTION_METHOD.md"
```

Expected:
- the new section is present
- the key concepts are explicitly named

- [ ] **Step 2: Do a final doc-quality pass**

Check that the new content:
- fits the document structure
- does not duplicate `EXTRACTION_FIELDS.md`
- does not duplicate `GOLDEN_SET.md`
- does not become a full implementation design
- is concrete enough to guide consistent span selection

If any issue is present, fix it immediately.

- [ ] **Step 3: Commit the span-rule addition**

```bash
git add EXTRACTION_METHOD.md docs/superpowers/specs/2026-04-09-text-span-selection-rules-design.md docs/superpowers/plans/2026-04-09-text-span-selection-rules.md
git commit -m "docs: add text span selection rules"
```

---

## Self-review

Spec coverage check:
- add new text-span section: covered in Task 1 Step 2
- document structure-first span selection: covered in Task 1 Step 3
- add `SpanPolicy` and candidate generation: covered in Task 1 Step 4
- add scoring dimensions: covered in Task 1 Step 5
- add too-small / too-large signals: covered in Task 1 Step 6
- add adequacy/retry policy: covered in Task 1 Step 7
- keep boundaries clear: covered in Task 1 Step 8

Placeholder scan:
- No TBD/TODO placeholders remain.
- All targets and verification commands are explicit.

Type / terminology consistency:
- The new section uses “minimum sufficient context,” `SpanPolicy`, and adequacy terminology consistently.
- `EXTRACTION_FIELDS.md` remains the field dictionary.
- `GOLDEN_SET.md` remains the truth/evaluation doc.
