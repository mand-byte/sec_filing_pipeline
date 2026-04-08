# DEMANDS.md Deduplication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lightly deduplicate `DEMANDS.md` so it stays the total architecture / total requirements document while delegating extraction-method and golden-set detail to their authority docs.

**Architecture:** Keep the existing `DEMANDS.md` section structure and project-level role intact. Compress only the parts that now overlap with `EXTRACTION_METHOD.md` and `GOLDEN_SET.md`, turning them into project-level principles plus links, and leave data-source, scheduler, UI, and roadmap content in place.

**Tech Stack:** Markdown, repo docs, grep-based verification

---

## File structure

### Modify
- `DEMANDS.md` — lightly deduplicate overlapping extraction/golden-set detail while keeping its total-architecture role

### Keep for reference during edit only
- `EXTRACTION_METHOD.md` — authority doc for extraction method details
- `GOLDEN_SET.md` — authority doc for truth/evaluation details
- `docs/superpowers/specs/2026-04-08-demands-dedup-design.md` — approved dedup design

---

### Task 1: Lightly deduplicate `DEMANDS.md` while preserving its role

**Files:**
- Modify: `DEMANDS.md`
- Reference: `EXTRACTION_METHOD.md`
- Reference: `GOLDEN_SET.md`
- Reference: `docs/superpowers/specs/2026-04-08-demands-dedup-design.md`

- [ ] **Step 1: Read the current `DEMANDS.md` against the two authority docs**

Read:
- `DEMANDS.md`
- `EXTRACTION_METHOD.md`
- `GOLDEN_SET.md`
- `docs/superpowers/specs/2026-04-08-demands-dedup-design.md`

Confirm which content must remain in `DEMANDS.md`:
- project goal
- architecture principles at project level
- data-source/storage boundary
- scheduler/state model
- UI/UX requirement
- roadmap

And which content should be reduced to principle + link:
- extraction-method detail now owned by `EXTRACTION_METHOD.md`
- golden-set truth/evaluation detail now owned by `GOLDEN_SET.md`

- [ ] **Step 2: Keep the overall section structure intact**

Do not rewrite the whole file. Keep these sections present:
- 任务总目标
- 架构选型与核心原则
- 目标集合与数据存储来源
- 程序调度与系统入口
- 提取对象与特征读取规则
- 人工审核产品交互刚需
- 研发里程碑与大包规划

- [ ] **Step 3: Compress the extraction-principles line into project-level guidance**

Keep the first architecture principle short and project-level. It should still say, in one concise line, that:
- the extraction stack is layered: `edgartools (XBRL / Obj) -> XML/HTML -> anchored regex -> LLM`
- spaCy is not part of the plan
- details live in `EXTRACTION_METHOD.md`

Do **not** add extractor-level, routing-level, cold-start, or QA-gate detail back into `DEMANDS.md`.

- [ ] **Step 4: Compress the Golden Set principle into project-level guidance**

Keep the second architecture principle short and project-level. It should still say, in one concise line, that:
- Golden Set V2 rejects mixed truth
- evaluation is based on auditable gold/silver/invariant data and versioned config
- details live in `GOLDEN_SET.md`

Do **not** restate truth tiers, strict denominator metrics, schema, artifact contract, or phase gates here.

- [ ] **Step 5: Keep project-only content untouched or nearly untouched**

Preserve content that belongs in `DEMANDS.md`, including:
- ClickHouse/PostgreSQL boundary and `us_stock_universe` schema example
- delisting / accepted_at handling rules
- scheduler / route / stateless cursor design
- side-by-side review UI requirement
- overall roadmap phases

Only make edits in these sections if needed to remove obvious repeated method-level wording.

- [ ] **Step 6: Lightly trim roadmap wording where it repeats subordinate docs**

Keep the roadmap itself, but compress method-detail duplication. Good examples:
- Keep “完成确定性最高的 Tier 1 抽取器” style goals.
- Avoid re-explaining the full meaning of Tier 1 / Tier 2 / Tier 3 if the subordinate docs already define them.
- Keep roadmap as phase intent, not as method-spec detail.

- [ ] **Step 7: Add one short document-boundary note if needed**

If the file still feels boundary-blurry after trimming, add one brief note in the architecture-principles or final section stating the roles of:
- `DEMANDS.md`
- `EXTRACTION_METHOD.md`
- `GOLDEN_SET.md`

Keep it short; this is a boundary reminder, not a new section with lots of detail.

- [ ] **Step 8: Verify the edited file still reads as a total architecture / total requirements doc**

After editing, read `DEMANDS.md` and confirm a reader can still understand:
- what the project is building
- the top-level architectural principles
- the system boundary and data model assumptions
- the scheduler/runtime shape
- the product review requirement
- the roadmap

without having to read the authority docs first.

---

### Task 2: Verify the dedup result

**Files:**
- Verify: `DEMANDS.md`
- Reference: `EXTRACTION_METHOD.md`
- Reference: `GOLDEN_SET.md`

- [ ] **Step 1: Run overlap-focused grep checks**

Run:

```bash
grep -n "EXTRACTION_METHOD\.md\|GOLDEN_SET\.md" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/DEMANDS.md"
grep -n "cold_start_review_gate\|error_code\|golden_case\|patch\|ObjPathExtractor\|XbrlConceptExtractor\|XmlPathExtractor\|AnchoredTableExtractor\|AnchoredSpanExtractor\|LlmSpanNormalizer" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/DEMANDS.md" || true
grep -n "gold_strict_accuracy\|silver_alignment\|invariant_pass_rate\|truth_tier\|golden_case\|golden_truth\|golden_eval_run" "/Users/weihu/Coding/QuantSystem/sec_filing_pipeline/DEMANDS.md" || true
```

Expected:
- `DEMANDS.md` still links to `EXTRACTION_METHOD.md` and `GOLDEN_SET.md`
- extractor-level implementation detail should not appear in `DEMANDS.md`
- strict golden-set metric/schema detail should not appear in `DEMANDS.md`

- [ ] **Step 2: Do a final doc-quality pass**

Check `DEMANDS.md` for these failures:
- reads like a duplicate of `EXTRACTION_METHOD.md`
- reads like a duplicate of `GOLDEN_SET.md`
- lost important project-level context
- roadmap over-trimmed into vagueness
- architecture principles now too thin to be useful

If any are present, fix them immediately.

- [ ] **Step 3: Commit the DEMANDS dedup**

```bash
git add DEMANDS.md docs/superpowers/specs/2026-04-08-demands-dedup-design.md docs/superpowers/plans/2026-04-08-demands-dedup.md
git commit -m "docs: trim DEMANDS overlap with authority docs"
```

---

## Self-review

Spec coverage check:
- keep DEMANDS as total architecture / total requirements doc: covered in Task 1 Steps 2, 5, 8
- trim extraction detail into principle + link: covered in Task 1 Step 3
- trim golden-set detail into principle + link: covered in Task 1 Step 4
- preserve roadmap/data/scheduler/UI content: covered in Task 1 Steps 5-6
- keep boundaries clear across docs: covered in Task 1 Step 7 and Task 2 Step 1

Placeholder scan:
- No TBD/TODO placeholders remain.
- All targets and verification commands are explicit.

Type / terminology consistency:
- `DEMANDS.md` stays the total architecture / total requirements doc.
- `EXTRACTION_METHOD.md` and `GOLDEN_SET.md` remain the subordinate authority docs.
