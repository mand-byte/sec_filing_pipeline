# Spec/Plan Historical Filename Reference Cleanup Design

## Goal
Clean up residual historical references to the old field-dictionary filename `EXTRACTION_FIELDS.md` inside `docs/superpowers/specs/*.md` and `docs/superpowers/plans/*.md`, replacing them with `EXTRACTION_FIELDS.md` where the reference is only naming the current authority document.

## Scope
This cleanup is intentionally narrow:
- update old filename references in spec/plan docs when they refer to the surviving authority doc
- keep the historical narrative intact
- do not touch shipped root docs, which are already correct
- do not reopen broader content changes in the specs/plans

## Non-goals
- do not rewrite historical context about deleted docs like `EXTRACTOR_CORRECTNESS.md` or `GOLDEN_SET_PLAN.md`
- do not alter substantive design decisions recorded in the specs/plans
- do not rename files again

## Rules
1. If a spec/plan sentence refers to the field-dictionary authority doc that now exists, use `EXTRACTION_FIELDS.md`.
2. If a sentence is quoting an old command or old state purely as historical evidence, preserve the history unless the old filename is being presented as the current target.
3. Do not modify any root shipped docs as part of this cleanup unless a missed old reference is discovered.

## Expected targets
Likely files include:
- `docs/superpowers/specs/2026-04-08-extraction-field-dictionary-design.md`
- `docs/superpowers/specs/2026-04-08-doc-cleanup-bundle-design.md`
- `docs/superpowers/specs/2026-04-08-repo-doc-boundary-audit-design.md`
- `docs/superpowers/plans/2026-04-08-extraction-field-dictionary.md`
- `docs/superpowers/plans/2026-04-08-doc-cleanup-bundle.md`
- `docs/superpowers/plans/2026-04-08-repo-doc-boundary-audit.md`

## Acceptance criteria
- no spec/plan doc refers to `EXTRACTION_FIELDS.md` as if it were the current authority filename
- historical meaning remains readable
- no new ambiguity is introduced about which field-dictionary doc is current
