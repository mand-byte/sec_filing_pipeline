# Extraction Method (Authoritative Specification)

This document is the single authoritative specification for extraction method design. It defines field registry structure, extractor routing, correctness boundaries, cold-start policy, QA/review gates, and the fix-once regression loop. Gold/Silver/Invariant truth policy and strict evaluation rules belong in `GOLDEN_SET.md`.

## 1) Scope and non-goals

**In scope**
- Extraction architecture and runtime routing.
- Declarative field registry and the six extractor types.
- Correctness engineering boundaries (Tier 1/2/3).
- QA/review gates, evidence lineage, cold-start rollout, and regression loop.

**Out of scope**
- Golden truth-tier definitions, strict denominators, and release metrics (see `GOLDEN_SET.md`).
- Project-wide goals, roadmap, and product-level principles (see `DEMANDS.md`).

## 2) Core architecture (single source)

The extraction stack is:

`edgartools (obj/xbrl) > XML/xpath > anchored regex > LLM normalization`

- `spaCy` is out of scope for the extraction core because this is primarily a structural extraction problem (paths/tables/concepts), not an NER-first problem.
- The core system is `edgartools + declarative registry + QA/review gate`.

## 3) How we extract: registry + six extractors

### 3.1 Field registry (declarative)

Each canonical field is defined by configuration, not per-field code forks.

```yaml
field: total_revenue
form_family: [10-K, 10-Q, 20-F, 6-K-financial]
locators:
  - kind: xbrl_concept
    concepts: [Revenue, Revenues, SalesRevenueNet]
    statement_type: IncomeStatement
  - kind: obj_path
    object_path: financials.income_statement
    row_aliases: ["Revenue", "Net sales", "Sales"]
  - kind: anchored_table
    section_aliases: ["Consolidated Statements of Operations", "Income Statement"]
normalizer:
  type: currency
qa:
  nonnegative: true
  max_abs: 1e15
```

Registry contract per field:
- `form_family`
- ordered `locators`
- `normalizer`
- `qa`
- optional `span_policy` for snippet-type fields that use span-based normalization

### 3.2 The six extractor types

1. **ObjPathExtractor**  
   Reads deterministic typed properties/tables from `filing.obj()`.

2. **XbrlConceptExtractor**  
   Queries `filing.xbrl()` facts by concept/statement/period constraints.

3. **XmlPathExtractor**  
   Applies deterministic XML xpath to schema-backed filings.

4. **AnchoredTableExtractor**  
   Locates section/table first, then row-label aliases and value cells.

5. **AnchoredSpanExtractor**  
   Extracts bounded item/section spans for narrative or semi-structured fields.

6. **LlmSpanNormalizer**  
   Converts pre-cut spans into strict schema output; it does not perform whole-document search.

## 4) Filing-family routing (extraction execution guidance)

Naming note: `6-K-financial` is the canonical `form_family` label for statement-style 6-K routing. References to event-style 6-K indicate a separate non-statement path and are not labeled `6-K-financial`.

- **10-K / 10-Q / 20-F**: object/XBRL first for financial fields; fallback to anchored tables/spans only when structured channels are absent or insufficient.
- **6-K with attached/interim financial statements or financial exhibits (`6-K-financial`)**: object/XBRL first for statement fields; fallback to anchored tables/spans only when structured channels are absent or insufficient.
- **6-K event-style disclosures / press releases without statement structure**: item/section-aware anchored span and anchored table extraction; LLM only for normalization of already bounded spans.
- **8-K**: item/section-aware anchored span and anchored table extraction; LLM only for normalization of already bounded spans.
- **DEF 14A**: HTML/table-first for proposal, ownership, and comp tables; structured channels used where available.
- **3 / 4 / 5**: XML/object-first deterministic extraction.
- **13D / 13G**: object/XML-first for ownership numerics and key items.
- **144**: object/XML-first for notice fields and sale/acquisition quantities.
- **13F**: holdings/info-table-first extraction with filing totals and row-level consistency checks.

## 5) Text span selection rules

This section defines how snippet-type fields determine their text span boundaries. It belongs in the method specification, not in field registry definitions (`EXTRACTION_FIELDS.md`) or in truth/evaluation documents (`GOLDEN_SET.md`).

### 5.1 Core principle

Spans are not selected by fixed character or token length. Instead, the extraction follows a **structure-first** approach: first identify the semantic block containing the target, then expand only as needed to provide sufficient context. The goal is **minimum sufficient context** — the smallest span that unambiguously contains the target with its key qualifiers.

### 5.2 Structure-first segmentation

Before span selection begins, the filing is segmented into `Block` units:

```python
@dataclass
class Block:
    kind: str               # heading, paragraph, table, footnote, exhibit
    text: str
    heading_path: list[str]
    start_char: int
    end_char: int
```

A span is then constructed as a sequence of one or more contiguous blocks, not as an arbitrary character window.

### 5.3 SpanPolicy configuration

Each snippet field can define an optional `SpanPolicy` in field metadata to guide span selection:

```python
@dataclass  # illustrative pseudocode
class SpanPolicy:
    field_name: str
    anchor_headers: list[str]          # primary structural anchors
    min_tokens: int                    # hard lower bound
    max_tokens: int                    # hard upper bound
    preferred_tokens: tuple[int, int]  # preferred scoring range
    expand_steps: tuple[int, ...]      # block-expansion sequence
    must_include: list[str]            # hard requirements if applicable
    avoid: list[str]                   # over-selection indicators
```

These policies are declarative metadata, not runtime code. `anchor_headers`, `min_tokens`, and `max_tokens` are hard constraints; `preferred_tokens`, `must_include`, and `avoid` shape candidate scoring and acceptance heuristics.

### 5.4 Candidate generation and scoring

The span selection process works as follows:

1. **Anchor identification**: Locate the primary `Block` anchored by the configured heading/item match. If multiple anchors match, prefer the earliest exact heading/item match within the nearest relevant section.
2. **Candidate construction**: Generate candidate spans by expanding outward from the anchor in contiguous block steps defined by `expand_steps`.
3. **Hard filtering**: Reject candidates that violate hard constraints (`min_tokens`, `max_tokens`, missing required anchor context, or missing `must_include` patterns when defined).
4. **Scoring**: Score the remaining candidates on multiple dimensions:
   - Token length falls within `preferred_tokens` range
   - Contains the target heading/item
   - Includes key qualifiers: units, currencies, negations, dates
   - Contains only a single target object (not multiple proposals, events, or entities)
   - Does not trigger `avoid` patterns (e.g., "other agreements", "see also")
5. **Selection**: Among all passing candidates, select the shortest one.

### 5.5 Too-small and too-large signals

The extraction must detect when a span is inadequate:

**Too-small signals:**
- Extracted value is `unclear` or missing critical qualifiers
- Confidence score from LLM normalization is low
- Missing unit, currency, or negation that should be present
- Subject pronoun reference cannot be resolved from context

**Too-large signals:**
- Output contains multiple distinct target objects (e.g., two separate proposals)
- Output mixes unrelated events or tables
- Rerun with same prompt shows high variance
- Confidence drops significantly when span is expanded

### 5.6 Adequacy check and retry policy

This adequacy loop primarily applies to snippet fields that flow through `AnchoredSpanExtractor` into `LlmSpanNormalizer`.

By default, the system performs **0 LLM pre-screen + 1 main extraction**. The first LLM call returns the normalized value along with adequacy signals (e.g., `confidence`, `multiple_candidate_targets`, `sufficient_context`). Only when these signals indicate the span is too small or too large does the system trigger a retry:

- **Too small**: expand the span by one configured contiguous-block `expand_step` and re-extract.
- **Too large**: contract the span by removing the outermost peripheral blocks symmetrically around the anchor when possible, then re-extract.

This default-one-try policy avoids the inefficiency of always running two LLM calls when the first span is adequate.

### 5.7 Boundary note

This section defines extraction method — how spans are selected and validated — and is distinct from:
- `EXTRACTION_FIELDS.md`, which defines field registry metadata
- `GOLDEN_SET.md`, which defines truth tiers and evaluation criteria

### 5.8 Span evidence contract

For every span-based extraction, the persisted artifact must capture sufficient evidence for human review and replay. This contract is about reviewability, not UI layout.

The persisted span evidence must include at minimum:

- **Selected span text**: the exact text string extracted as the candidate span.
- **Source block identifiers**: block IDs or source character offsets (`start_char`, `end_char`) that enable re-location in the source filing.
- **Heading path / item number / source section**: the structural context anchoring the span (e.g., heading path from block metadata, item number, section alias).
- **Span locator kind**: which span-selection locator produced this candidate (for example `anchored_span`).
- **Adequacy signals**: when `LlmSpanNormalizer` is used, persist runtime signals such as:
  - `confidence`
  - `sufficient_context`
  - `multiple_candidate_targets`
- **Retry history**: if the span was expanded or contracted due to adequacy checks, record the sequence of attempts (original span, expansion/contraction steps, final span).
- **Review decision linkage**: reference to the final review outcome (`ACCEPT` / `NEEDS_REVIEW` / `REJECT`) and any associated correction metadata.

This span evidence extends the general evidence/lineage requirements below and enables:
- Reviewers to verify the span boundaries against source
- Replay of the extraction with modified parameters
- Audit trail from raw span to final normalized output

## 6) Correctness engineering boundaries (Tier 1/2/3)

| Tier | Extractors | Trust level | Why trust differs | Representative failure modes | Primary mitigations |
|---|---|---|---|---|---|
| Tier 1 | ObjPath, XbrlConcept, XmlPath | Highest (deterministic) | Backed by structured object/XBRL/XML semantics | Missing object path, taxonomy extension mismatch, period/dimension mis-selection | Ordered locator fallback within Tier 1, strict locator metadata, field QA bounds |
| Tier 2 | AnchoredTable, AnchoredSpan | Medium (semi-structured) | Depends on template/layout and alias stability | Header/row alias drift, merged cells, section boundary miss | Section-first anchoring, alias caps, template-aware review triggers, cross-check vs Tier 1 when both exist |
| Tier 3 | LlmSpanNormalizer | Conditional (input-dependent) | Relies on model interpretation of extracted span | Schema drift, hallucinated keys, inconsistent normalization | 1–3 KB bounded spans only, strict JSON schema validation, deterministic prompting, review on uncertainty |

Boundary rule (fallback vs review semantics):
- If a candidate fails QA, continue to the next locator in ordered policy.
- If a higher-trust candidate passes QA and review gate returns `NEEDS_REVIEW`, stop fallback and send that candidate to review.
- If a higher-trust candidate passes QA and review gate returns `REJECT` (candidate invalid or contradicted by stronger evidence), continue ordered fallback (remaining same-tier locators, then next locator/tier if configured).
- A lower-trust tier must not replace a higher-trust QA-passing candidate unless that higher-trust candidate was explicitly `REJECT`ed.

## 7) Runtime flow, QA gate, evidence lineage, anti-bloat rules

### 6.1 Runtime flow

```python
def extract_field(filing, field_spec, stats):
    for locator in field_spec.locators:
        candidate = locator.try_extract(filing, field_spec)
        if not candidate:
            continue
        value = normalize(candidate.raw, field_spec.normalizer)
        if not qa_pass(value, field_spec.qa):
            continue

        result = {
            "value": value,
            "raw": candidate.raw,
            "locator_kind": locator.kind,
            "lineage": candidate.lineage,
            "confidence": candidate.confidence,
        }
        decision, reason = cold_start_review_gate(result, field_spec, stats)
        result["review_decision"] = decision
        result["review_reason"] = reason
        if decision == "ACCEPT":
            return result
        if decision == "NEEDS_REVIEW":
            return result
        # REJECT: continue searching lower-priority locators
    return None
```

### 6.2 QA gate expectations

QA gate determines whether a candidate is valid enough to enter review-gate decisioning; a QA pass is necessary but not always auto-accept.

After QA pass, review gate assigns **ACCEPT / NEEDS_REVIEW / REJECT** using:
- Field-level bounds and type checks.
- Locator-level confidence and parser validity.
- Optional cross-locator agreement checks.
- History-aware outlier checks where applicable.

### 6.3 Evidence and lineage requirements

Each accepted/reviewed candidate must persist:
- `accession_no`, `form_type`, `cik`, filing timestamp.
- `field_name`, `locator_kind`, locator-specific path (`object_path`/`xbrl_concept`/`xpath`/section/item id).
- `source_span` (or XML node reference), `raw_value`, `normalized_value`.
- `confidence`, `qa_flags`, and review decision.

### 6.4 Anti-bloat rules

- Max **3 locators** per field unless a regression-backed exception is approved.
- Max **10 aliases per field**; if alias growth exceeds this cap, upgrade to a stronger structural locator instead of adding more aliases.
- LLM input must be bounded to small pre-cut spans; never pass whole filings.
- New extraction rules must be justified by recurring regression evidence.

## 8) Cold-start progression and review gate

### 8.1 Phase progression

- **Phase 0 (seed truth build)**: create initial golden cases and baseline field coverage.
- **Phase 1 (Tier 1 only)**: enable ObjPath/XbrlConcept/XmlPath; all new patterns heavily reviewed.
- **Phase 2 (enable Tier 2)**: allow AnchoredTable/AnchoredSpan where Tier 1 is absent or incomplete.
- **Phase 3 (enable Tier 3)**: allow LLM normalization on bounded spans with strict schema and review controls.

Progression principle: **Tier 1 first, then Tier 2, then LLM**.

### 8.2 Representative cold_start_review_gate logic

```python
def cold_start_review_gate(result, field_spec, stats):
    if stats.issuer_field_count(result.cik, field_spec.name) == 0:
        return "NEEDS_REVIEW", "first_seen_issuer_field"

    if stats.template_field_count(result.template_hash, field_spec.name) == 0:
        return "NEEDS_REVIEW", "first_seen_template"

    if stats.is_outlier_vs_history(field_spec.name, result.value):
        return "NEEDS_REVIEW", "outlier_vs_history"

    return "ACCEPT", None
```

## 9) Human review workflow contract

### 9.1 Review states

The extraction gate uses `ACCEPT`, `NEEDS_REVIEW`, and `REJECT` as routing decisions. Human review may then resolve the case with one of the following terminal dispositions:

- **ACCEPT**: Candidate is confirmed and may proceed to persistence.
- **CORRECTED**: Reviewer edits the payload; the corrected payload must re-enter QA validation before persistence.
- **REJECT**: Candidate is rejected; extraction must reopen ordered fallback from the next eligible locator rather than persisting the rejected candidate.
- **NOT_APPLICABLE**: Field does not apply to this filing/subject and should persist as not applicable where supported.

`NEEDS_REVIEW` is the gate state that sends a candidate into human review; it is not itself a terminal review disposition.

### 9.2 Reviewer-editable fields

A reviewer may modify the following fields during review:

- **Numeric value**: Corrected or override numeric output.
- **Selected span**: Adjusted span boundaries for span-based extractions.
- **Subject identity**: Corrected entity/subject reference (e.g., which registrant or segment).
- **Applicability**: Mark field as applicable or not applicable.
- **Error code**: Assign normalized failure class (e.g., `row_match_error`, `unit_scaling`, `locator_miss`).
- **Note/rationale**: Free-text explanation for the review decision or correction.

### 9.3 Persisted review output

Each completed review must persist:

- **Final decision**: One of the terminal review dispositions defined above.
- **Corrected payload**: The final value and metadata after any reviewer edits (or original if unchanged).
- **Evidence references**: Identifiers for both the original candidate evidence and the final corrected evidence when a correction occurred.
- **Reviewer note**: The rationale or explanation provided by the reviewer.
- **Timestamp**: When the review was completed.
- **Reviewer identifier**: When available, the reviewer identity (user ID, system, or automated agent).

### 9.4 Feedback-loop rules

When a review identifies an extraction issue:

- **Recurring errors**: If the same error pattern occurs across multiple filings, the fix must produce:
  1. An `error_code` identifying the normalized failure class.
  2. A `golden_case` added to regression/eval artifacts.
  3. A targeted `patch` in registry/normalizer/review-gate/extractor logic.
- **One-off anomalies**: If the error is a unique anomaly, it may remain as a reviewer override with explicit rationale and lineage rather than becoming a general rule.

Operational principle: Generalize a fix only when it is repeated, generalizable, and low-risk. Reviewer corrections preserve original evidence, produce corrected evidence, and re-enter QA before final persistence.

## 10) Fix-once regression loop

Each corrected extraction issue must produce:

1. **`error_code`**: normalized failure class (e.g., row match error, unit scaling, locator miss, schema mismatch).
2. **`golden_case`**: reproducible case added to regression/eval artifacts.
3. **`patch`**: targeted fix in registry/normalizer/review-gate/extractor logic.

Operational rule:
- Generalize a fix only when it is **repeated**, **generalizable**, and **low-risk**.
- Otherwise keep it as a **one-off override** with explicit rationale and lineage.

## 11) Document boundaries

- **`DEMANDS.md`**: project goals, global principles, and roadmap.
- **`EXTRACTION_METHOD.md` (this doc)**: extraction architecture, routing, correctness engineering, cold-start, and review process.
- **`GOLDEN_SET.md`**: truth tiers, strict schema, evaluation metrics/artifacts, and release gates.
