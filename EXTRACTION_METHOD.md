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

## 5) Correctness engineering boundaries (Tier 1/2/3)

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

## 6) Runtime flow, QA gate, evidence lineage, anti-bloat rules

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

## 7) Cold-start progression and review gate

### 7.1 Phase progression

- **Phase 0 (seed truth build)**: create initial golden cases and baseline field coverage.
- **Phase 1 (Tier 1 only)**: enable ObjPath/XbrlConcept/XmlPath; all new patterns heavily reviewed.
- **Phase 2 (enable Tier 2)**: allow AnchoredTable/AnchoredSpan where Tier 1 is absent or incomplete.
- **Phase 3 (enable Tier 3)**: allow LLM normalization on bounded spans with strict schema and review controls.

Progression principle: **Tier 1 first, then Tier 2, then LLM**.

### 7.2 Representative cold_start_review_gate logic

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

## 8) Fix-once regression loop

Each corrected extraction issue must produce:

1. **`error_code`**: normalized failure class (e.g., row match error, unit scaling, locator miss, schema mismatch).
2. **`golden_case`**: reproducible case added to regression/eval artifacts.
3. **`patch`**: targeted fix in registry/normalizer/review-gate/extractor logic.

Operational rule:
- Generalize a fix only when it is **repeated**, **generalizable**, and **low-risk**.
- Otherwise keep it as a **one-off override** with explicit rationale and lineage.

## 9) Document boundaries

- **`DEMANDS.md`**: project goals, global principles, and roadmap.
- **`EXTRACTION_METHOD.md` (this doc)**: extraction architecture, routing, correctness engineering, cold-start, and review process.
- **`GOLDEN_SET.md`**: truth tiers, strict schema, evaluation metrics/artifacts, and release gates.
