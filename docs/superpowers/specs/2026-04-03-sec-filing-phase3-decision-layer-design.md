# SEC Filing Phase 3 Decision Layer Design

Date: 2026-04-03

## 1. Scope and Goal

This spec defines the next implementation stage after the completed Phase 0-2 owner slice.

Phase 3 scope is intentionally constrained to `owner` route `3/4/5` and focuses on turning parse routing, fallback decisions, and failure observability into explicit platform behavior.

Primary goal:

- build a deterministic parse routing and decision layer for owner `3/4/5`
- persist success and failure attempts to PostgreSQL with file-level traceability
- support operational querying by file type, attempt time range, and failure type

Out of scope for this phase:

- holdings (`13F`) route onboarding
- issuer route onboarding
- replacing `structured_xml` parser with edgartools parsing

## 2. Fixed Decisions

The following decisions are fixed for this phase.

### 2.1 Route and parser chain

- Route scope is owner forms `3/4/5` only.
- Parse chain is fixed:
  - `structured_xml`
  - `deterministic_rule`
  - final state `needs_review`

### 2.2 Decision policy

- If `structured_xml` succeeds and validations pass, decision can be accepted path.
- If `structured_xml` fails and `deterministic_rule` succeeds, final decision is `needs_review`.
- If both methods fail, final decision is `needs_review`.

### 2.3 Logging policy

- Logging object name is `parse_route_log` (解析路由日志).
- Every parse attempt, success or failure, must be persisted to PostgreSQL.
- Failed attempts must include:
  - `failure_type` in `network | parse | logic`
  - `error_message` as detailed failure text

### 2.4 Download strategy

- Do not use edgartools as the main parser for field extraction in this phase.
- Use edgartools as the download adapter for SEC filing and attachments.
- Download all attachments for each selected filing.
- Persist all downloaded artifacts through deterministic raw-store paths before parse routing.

Reasoning boundary:

- Current `structured_xml` implementation preserves field-level evidence (`snippet_text`, `snippet_locator`) and is aligned with precision-first audit requirements.
- edgartools parsing API is not the primary path for this phase because field-level provenance guarantees required by this project are not yet the control boundary.

## 3. Parse Route Log Contract

`parse_route_log` is the process audit table for parse routing. One row represents one method attempt on one concrete document.

### 3.1 Row granularity

- Key process unit: one document + one parser method + one attempt timestamp.
- The same document can produce multiple rows in one run because fallback methods are logged separately.
- Replays produce new rows with a new `run_id`.

### 3.2 Required fields

Identity and linkage:

- `id`
- `run_id`
- `route_type`
- `filing_id`
- `accession_no`
- `cik`
- `document_id`

File metadata:

- `document_type`
- `document_filename`
- `document_path`
- `snapshot_path`
- `source_url`
- `sha256_hex`
- `byte_length`

Attempt metadata:

- `parser_method`
- `attempted_at_utc`
- `status` (`success | failed | skipped`)

Failure and fallback metadata:

- `failure_type` (`network | parse | logic`)
- `error_message`
- `fallback_reason`

Decision linkage metadata:

- `decision_state`
- `selected_candidate` (boolean)

### 3.3 Constraints

- If `status = failed`, both `failure_type` and `error_message` are required.
- If `status = success`, `failure_type` is null.
- `parser_method` must be one of the registered parse methods for this phase.
- File metadata must be present so operators can locate the concrete artifact and replay path.

## 4. Failure and Fallback Taxonomy

### 4.1 Failure type enum

- `network`: fetch/download or transport layer failure
- `parse`: XML/text parsing failure
- `logic`: deterministic-rule execution or validation logic failure

### 4.2 Fallback reason enum (phase minimum)

- `structured_xml_exception`
- `structured_xml_missing_mandatory`
- `structured_xml_numeric_invalid`
- `structured_xml_empty_value`
- `deterministic_rule_exception`
- `deterministic_rule_not_applicable`
- `all_methods_failed`

## 5. Query and Observability Requirements

### 5.1 Mandatory query dimensions

Phase 3 must support parse route log retrieval by:

- `document_type`
- date range on `attempted_at_utc`
- `failure_type`

### 5.2 Timeline reconstruction

System must provide timeline reconstruction for one concrete file via:

- `accession_no`
- `document_id`

The returned timeline must show ordered attempts with method, status, failure details, fallback reason, and decision state.

### 5.3 Output minimum for operator-facing query

Query/timeline output must include at least:

- `accession_no`
- `document_filename`
- `document_type`
- `document_path`
- `parser_method`
- `status`
- `failure_type`
- `attempted_at_utc`

## 6. Integration Design

### 6.1 Components

- `SecDownloadAdapter`:
  - wraps edgartools for filing selection and attachment download metadata
  - emits normalized filing/document descriptors for pipeline processing
- `ParseRouteLogger`:
  - single write interface for parse attempt logs
- `DecisionService`:
  - executes fixed parser chain and emits final decision state
- `ParseRouteLogRepository`:
  - implements filtered query and timeline APIs

### 6.2 Processing order

For each discovered owner filing:

1. download filing bundle and all attachments via `SecDownloadAdapter`
2. persist downloaded artifacts to deterministic raw store
3. run parser chain per candidate document
4. append `parse_route_log` row for each attempt
5. produce facts/review items from decision outcome

### 6.3 Existing result-table relationship

- `parse_route_log` is the process audit boundary.
- `extracted_fact` and `review_queue` remain result tables.
- Each review/fact record must be traceable to source document and parse route logs by filing/document linkage keys.

## 7. CLI and Service Contract (Phase Minimum)

### 7.1 Service-level interfaces

- `download_owner_filing_bundle(cik, accession_no) -> FilingBundle`
- `append_parse_route_log(log_row) -> None`
- `query_parse_route_logs(document_type?, start_utc?, end_utc?, failure_type?, limit, offset) -> list`
- `get_parse_route_timeline(accession_no, document_id) -> list`
- `process_owner_document(bundle, document) -> DecisionResult`

### 7.2 CLI behavior

- Keep `owner-sync` as owner ingestion entrypoint, now using download adapter + parse route logger pipeline.
- Keep `replay-accession <accession_no>` as replay entrypoint with a new `run_id` per replay execution.
- Add:
  - `parse-log query --document-type --from-utc --to-utc --failure-type --limit --offset`
  - `parse-log timeline --accession-no --document-id`

## 8. Testing Strategy

### 8.1 Required tests

- Download adapter tests:
  - normalized metadata extraction
  - network failure logging as `failure_type = network`
- Parse chain tests:
  - structured success path
  - structured fail -> deterministic success -> final `needs_review`
  - both fail -> final `needs_review`
- Parse route log tests:
  - success and failure rows are both persisted
  - failed row contains required `failure_type` and `error_message`
- Query tests:
  - filtering by `document_type`
  - filtering by `attempted_at_utc` range
  - filtering by `failure_type`
- Timeline tests:
  - ordered attempt reconstruction for one accession/document pair
- Replay tests:
  - replay creates new run log history
  - result persistence remains idempotent for fact/review boundaries

### 8.2 Representative regression cases

- malformed XML causes `parse` failure log with error text
- deterministic fallback success still ends in `needs_review`
- attachment download success + parse failure still preserves full file traceability in logs
- non-target attachment behavior is auditable as skipped or non-selected without missing file trace

## 9. Phase 3 Exit Criteria

Phase 3 is complete when all conditions are met:

- PostgreSQL has a working `parse_route_log` process table with success/failure persistence.
- Operator query paths support required dimensions:
  - `document_type`
  - `attempted_at_utc` date range
  - `failure_type`
- Any review item can be traced back to concrete file metadata and parse routing attempts.
- Owner `3/4/5` routing behavior is stable and matches fixed chain and decision policy.
- All-attachment download via edgartools is integrated and replayable through deterministic raw persistence.

## 10. Non-Goals and Follow-On

This phase does not generalize to holdings or issuer routes. That generalization belongs to a later phase once owner-route decision and observability contracts are proven stable.
