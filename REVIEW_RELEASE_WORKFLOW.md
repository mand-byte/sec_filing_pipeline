# Review Workbench and Release Gate Workflow

This workflow is the operator-facing fix-once loop for SEC extraction review. It complements the approved precision plan by keeping review decisions tied to replayable evidence and by exporting regression packets before release.

## Surfaces

- `uv run python main.py review-dashboard --output-dir artifacts/review_dashboard` exports a static side-by-side dashboard with `index.html` and `packets.json`.
- `uv run python main.py review-serve --status open --host 127.0.0.1 --port 8765` runs the local HTTP workbench for task listing, evidence replay, assignment, and resolution.
- `uv run python main.py review-list`, `review-show`, `review-assign`, and `review-resolve` provide the same operator flow through the CLI.
- `uv run python main.py release-gate --output-dir artifacts/release_gate` blocks release when open review tasks remain or when resolved fix-once tasks are missing regression packets.

## Evidence replay contract

Review packets and workbench views must preserve enough context to reproduce the extraction decision:

- locator kind plus `source_locator_json`
- section/item/xpath/span fields
- heading path and block offsets for text spans
- adequacy signals, retry history, and selection trace
- raw and normalized values next to the persisted fact payload

Non-`accept` decisions require a normalized `error_code` and a non-blank reviewer identity. `corrected`, `reject`, and `not_applicable` decisions are expected to create golden regression seed data and a `golden_review_packet` run under `review-capture::<task_id>`.

## Release evidence

A successful review/release pass should leave:

- `artifacts/release_gate/summary.json`
- exported packets under `artifacts/release_gate/review_regressions/`
- green review and release tests:
  - `uv run pytest -q tests/test_review_workflow.py tests/test_review_dashboard.py tests/test_review_server.py tests/test_release_gate.py`

`strict-v2-eval` remains the release-grade evaluator entry point for golden artifacts. `offline-eval` is retained as a development/debug runner for Tier 2 text fixture investigation.
