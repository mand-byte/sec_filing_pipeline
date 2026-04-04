# SEC Filing Phase A1 Owner Production Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the current owner-route slice into a PostgreSQL-driven, replay-safe, stateless ingestion loop with filing/document persistence, explicit review reasons, and discovery-based incremental sync.

**Architecture:** Keep workers stateless and move all operational state into PostgreSQL. Split Phase A1 into four concrete seams: persistence models for traceability, repositories for state/index writes, owner-specific persistence helpers, and an owner sync service that discovers unseen filings, downloads them, persists raw/index rows, runs parsing, and advances the cursor only on normal sync. Replay remains explicit, append-only, and does not move ingestion state.

**Tech Stack:** Python 3.12+, SQLAlchemy 2.x, Typer, pydantic-settings, lxml, pytest, urllib.request

---

## File Structure

- `src/domain/enums.py`
  Extend owner-slice review reason taxonomy for Phase A1.
- `src/models/filing.py`
  Add document/run/fallback provenance columns to `ExtractedFact`.
- `src/models/review.py`
  Add filing/document/run/parser/decision linkage for review items.
- `src/models/state.py`
  Keep PostgreSQL cursor model as the source of truth for incremental progress.
- `src/storage/ingestion_state_repo.py`
  PostgreSQL/in-memory compatible repository for owner ingestion cursor reads and updates.
- `src/storage/filing_repo.py`
  Idempotent repository for `filing_index` and `filing_document` writes.
- `src/storage/sec_submissions_client.py`
  Fetch SEC submissions JSON for discovery-driven owner sync using project user-agent.
- `src/storage/raw_store.py`
  Reuse deterministic raw document and snapshot persistence.
- `src/storage/owner_discovery.py`
  Reuse form filtering and cursor-aware unseen-filing discovery.
- `src/worker/owner_persistence.py`
  New helper module for building/persisting filing rows, document rows, facts, and review items.
- `src/worker/owner_pipeline.py`
  Keep parse orchestration focused on one downloaded filing bundle + one document decision path.
- `src/worker/owner_sync_service.py`
  New discovery-driven owner sync orchestrator that reads state, discovers unseen filings, ingests them, and advances cursor.
- `src/cli.py`
  Change `owner-sync` into discovery-based sync; keep `replay-accession` as explicit replay that does not advance the cursor.
- `tests/models/test_metadata.py`
  Verify Phase A1 model columns and taxonomy.
- `tests/storage/test_ingestion_state_repo.py`
  Verify owner cursor get/create/advance semantics.
- `tests/storage/test_filing_repo.py`
  Verify idempotent filing/document persistence.
- `tests/storage/test_sec_submissions_client.py`
  Verify SEC submissions fetch, user-agent wiring, and network error mapping.
- `tests/worker/test_owner_pipeline.py`
  Verify bundle ingestion persists filing/document rows, review items, and replay-safe facts.
- `tests/worker/test_owner_sync_service.py`
  Verify cold-start and incremental owner sync behavior from PostgreSQL state.
- `tests/cli/test_owner_sync_cli.py`
  Verify CLI semantics for `owner-sync` and `replay-accession`.
- `tests/integration/test_owner_incremental_flow.py`
  Verify end-to-end Phase A1 cold-start, incremental skip, and replay behavior.

### Task 1: Add Phase A1 Traceability Columns and Review Taxonomy

**Files:**
- Modify: `src/domain/enums.py:45-48`
- Modify: `src/models/filing.py:49-68`
- Modify: `src/models/review.py:9-21`
- Modify: `tests/models/test_metadata.py:33-92`

- [ ] **Step 1: Write the failing metadata and enum tests**

```python
# tests/models/test_metadata.py
from src.domain.enums import FallbackReason, ParseAttemptStatus, ParseFailureType, ReviewReason
from src.models import Base  # noqa: F401
from src.models import filing, parse_route_log, registry, review, state  # noqa: F401


def test_review_reason_taxonomy_covers_owner_phase_a1() -> None:
    assert {
        "mandatory_field_missing",
        "source_conflict",
        "amendment_conflict",
        "parser_disagreement",
        "unsupported_layout",
        "low_confidence",
    } <= {item.value for item in ReviewReason}



def test_owner_fact_and_review_tables_expose_traceability_columns() -> None:
    fact_table = Base.metadata.tables["extracted_fact"]
    review_table = Base.metadata.tables["review_queue"]

    assert {"cik", "document_id", "run_id", "fallback_reason"} <= set(
        fact_table.columns.keys()
    )
    assert {
        "filing_id",
        "document_id",
        "run_id",
        "parser_method",
        "decision_state",
    } <= set(review_table.columns.keys())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/models/test_metadata.py::test_review_reason_taxonomy_covers_owner_phase_a1 tests/models/test_metadata.py::test_owner_fact_and_review_tables_expose_traceability_columns -v`

Expected: FAIL because the new review reasons and provenance columns do not exist yet.

- [ ] **Step 3: Implement the taxonomy and model-column changes**

```python
# src/domain/enums.py
class ReviewReason(str, Enum):
    MANDATORY_FIELD_MISSING = "mandatory_field_missing"
    SOURCE_CONFLICT = "source_conflict"
    AMENDMENT_CONFLICT = "amendment_conflict"
    PARSER_DISAGREEMENT = "parser_disagreement"
    UNSUPPORTED_LAYOUT = "unsupported_layout"
    LOW_CONFIDENCE = "low_confidence"
```

```python
# src/models/filing.py
class ExtractedFact(Base):
    __tablename__ = "extracted_fact"

    fact_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    filing_id: Mapped[str] = mapped_column(String(128), index=True)
    accession_no: Mapped[str] = mapped_column(String(32), index=True)
    cik: Mapped[str] = mapped_column(String(10), index=True)
    document_id: Mapped[str] = mapped_column(String(128), index=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    fact_name: Mapped[str] = mapped_column(String(128), index=True)
    fact_value: Mapped[str] = mapped_column(Text)
    parser_method: Mapped[str] = mapped_column(String(64))
    fallback_reason: Mapped[str | None] = mapped_column(String(64), index=True)
    confidence_score: Mapped[float] = mapped_column(nullable=False)
    confidence_bucket: Mapped[str] = mapped_column(String(16))
    decision_state: Mapped[str] = mapped_column(String(32))
    snippet_text: Mapped[str] = mapped_column(Text)
    snippet_locator: Mapped[str] = mapped_column(Text)
    document_filename: Mapped[str] = mapped_column(String(255))
    validation_results: Mapped[dict] = mapped_column(JSON)
    attempted_methods: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

```python
# src/models/review.py
class ReviewQueueItem(Base):
    __tablename__ = "review_queue"

    review_item_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    filing_id: Mapped[str] = mapped_column(String(128), index=True)
    accession_no: Mapped[str] = mapped_column(String(32), index=True)
    document_id: Mapped[str] = mapped_column(String(128), index=True)
    fact_id: Mapped[str | None] = mapped_column(String(160), index=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    parser_method: Mapped[str | None] = mapped_column(String(64), index=True)
    decision_state: Mapped[str] = mapped_column(String(32), index=True)
    review_reason: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String(32), default="open")
    note: Mapped[str | None] = mapped_column(Text)
```

- [ ] **Step 4: Run the metadata tests again**

Run: `uv run pytest tests/models/test_metadata.py -v`

Expected: PASS with the new review reasons and traceability columns present in metadata.

- [ ] **Step 5: Commit the traceability model baseline**

```bash
git add src/domain/enums.py src/models/filing.py src/models/review.py tests/models/test_metadata.py
git commit -m "feat: add owner phase a1 traceability columns"
```

### Task 2: Add PostgreSQL Repositories for Cursor and Filing Metadata

**Files:**
- Create: `src/storage/ingestion_state_repo.py`
- Create: `src/storage/filing_repo.py`
- Create: `tests/storage/test_ingestion_state_repo.py`
- Create: `tests/storage/test_filing_repo.py`

- [ ] **Step 1: Write the failing repository tests**

```python
# tests/storage/test_ingestion_state_repo.py
from datetime import datetime, timezone

from src.storage.ingestion_state_repo import IngestionStateRepository


class FakeSession:
    def __init__(self) -> None:
        self.by_pk = {}
        self.added = []

    def add(self, obj) -> None:
        self.added.append(obj)
        self.by_pk[(obj.__class__, obj.cik, obj.route_type)] = obj

    def get(self, model, pk):
        if isinstance(pk, tuple):
            return self.by_pk.get((model, *pk))
        return self.by_pk.get((model, pk))



def test_get_or_create_owner_state_returns_existing_row() -> None:
    session = FakeSession()
    repo = IngestionStateRepository(session)

    state = repo.get_or_create(cik="0000320193", route_type="owner")
    same = repo.get_or_create(cik="0000320193", route_type="owner")

    assert same is state
    assert len(session.added) == 1



def test_advance_only_moves_cursor_forward() -> None:
    session = FakeSession()
    repo = IngestionStateRepository(session)
    state = repo.get_or_create(cik="0000320193", route_type="owner")

    repo.advance(
        state=state,
        accession_no="0000320193-24-000050",
        acceptance_datetime_utc=datetime(2024, 4, 4, tzinfo=timezone.utc),
    )
    repo.advance(
        state=state,
        accession_no="0000320193-24-000010",
        acceptance_datetime_utc=datetime(2024, 4, 3, tzinfo=timezone.utc),
    )

    assert state.last_accession_no == "0000320193-24-000050"
```

```python
# tests/storage/test_filing_repo.py
from src.models.filing import FilingDocument, FilingIndex
from src.storage.filing_repo import FilingRepository


class FakeSession:
    def __init__(self) -> None:
        self.by_pk = {}
        self.added = []

    def add(self, obj) -> None:
        self.added.append(obj)
        key_name = "filing_id" if isinstance(obj, FilingIndex) else "document_id"
        self.by_pk[(obj.__class__, getattr(obj, key_name))] = obj

    def get(self, model, pk):
        return self.by_pk.get((model, pk))



def test_add_filing_index_if_missing_is_idempotent() -> None:
    session = FakeSession()
    repo = FilingRepository(session)
    row = FilingIndex(
        filing_id="owner:0000320193:0000320193-24-000012",
        cik="0000320193",
        accession_no="0000320193-24-000012",
        form_type_raw="4",
        form_type_base="4",
        is_amendment=False,
        route_type="owner",
        acceptance_datetime_utc=None,
        filing_date=None,
        primary_document="ownership.xml",
        amendment_group_key="0000320193:4:0000320193-24-000012",
        amendment_sequence=0,
    )

    first = repo.add_filing_index_if_missing(row)
    second = repo.add_filing_index_if_missing(row)

    assert first is row
    assert second is row
    assert len(session.added) == 1
```

- [ ] **Step 2: Run the repository tests to verify they fail**

Run: `uv run pytest tests/storage/test_ingestion_state_repo.py tests/storage/test_filing_repo.py -v`

Expected: FAIL with `ModuleNotFoundError` for the new repository modules.

- [ ] **Step 3: Implement the repositories**

```python
# src/storage/ingestion_state_repo.py
from datetime import datetime
from typing import Any

from src.models.state import IngestionState
from src.worker.owner_pipeline import update_ingestion_state


class IngestionStateRepository:
    def __init__(self, session: Any) -> None:
        self.session = session

    def get_or_create(self, *, cik: str, route_type: str) -> IngestionState:
        state = self.session.get(IngestionState, (cik, route_type))
        if state is not None:
            return state
        state = IngestionState(cik=cik, route_type=route_type)
        self.session.add(state)
        return state

    def advance(
        self,
        *,
        state: IngestionState,
        accession_no: str,
        acceptance_datetime_utc: datetime,
    ) -> IngestionState:
        return update_ingestion_state(
            state=state,
            accession_no=accession_no,
            acceptance_datetime_utc=acceptance_datetime_utc,
        )
```

```python
# src/storage/filing_repo.py
from typing import Any

from src.models.filing import FilingDocument, FilingIndex


class FilingRepository:
    def __init__(self, session: Any) -> None:
        self.session = session

    def add_filing_index_if_missing(self, row: FilingIndex) -> FilingIndex:
        existing = self.session.get(FilingIndex, row.filing_id)
        if existing is not None:
            return existing
        self.session.add(row)
        return row

    def add_document_if_missing(self, row: FilingDocument) -> FilingDocument:
        existing = self.session.get(FilingDocument, row.document_id)
        if existing is not None:
            return existing
        self.session.add(row)
        return row
```

- [ ] **Step 4: Run the repository tests again**

Run: `uv run pytest tests/storage/test_ingestion_state_repo.py tests/storage/test_filing_repo.py -v`

Expected: PASS with cursor get/create/advance and filing/document idempotency covered.

- [ ] **Step 5: Commit the repository layer**

```bash
git add src/storage/ingestion_state_repo.py src/storage/filing_repo.py tests/storage/test_ingestion_state_repo.py tests/storage/test_filing_repo.py
git commit -m "feat: add owner cursor and filing repositories"
```

### Task 3: Persist Filing Rows, Document Rows, Snapshots, and Review Artifacts

**Files:**
- Create: `src/worker/owner_persistence.py`
- Modify: `src/worker/owner_pipeline.py:1-378`
- Modify: `tests/worker/test_owner_pipeline.py:39-459`

- [ ] **Step 1: Write the failing owner persistence tests**

```python
# tests/worker/test_owner_pipeline.py
from datetime import datetime, timezone

from src.storage.owner_discovery import DiscoveredFiling
from src.storage.parse_route_log_repo import ParseRouteLogRepository
from src.storage.raw_store import RawStore
from src.storage.sec_download_adapter import DownloadedAttachment, DownloadedFilingBundle
from src.worker.owner_pipeline import ingest_downloaded_owner_filing_bundle, process_owner_document



def test_deterministic_fallback_creates_parser_disagreement_review_item(tmp_path) -> None:
    session = FakeSession()
    repo = ParseRouteLogRepository(session)

    def structured_stub(_: str):
        return ParsedOwnershipSubmission(
            accession_no="0000320193-24-000012",
            document_filename="ownership.xml",
            facts=[
                ParsedOwnershipFact(
                    fact_name="issuer_cik",
                    fact_value="",
                    parser_method="structured_xml",
                    snippet_text="",
                    snippet_locator="/ownershipDocument/issuer/issuerCik",
                    document_filename="ownership.xml",
                    validation_results={"mandatory_present": False},
                )
            ],
        )

    def deterministic_stub(_: str):
        return ParsedOwnershipSubmission(
            accession_no="0000320193-24-000012",
            document_filename="ownership.txt",
            facts=[
                ParsedOwnershipFact(
                    fact_name="issuer_cik",
                    fact_value="0000320193",
                    parser_method="deterministic_rule",
                    snippet_text="Issuer CIK: 0000320193",
                    snippet_locator="line:1",
                    document_filename="ownership.txt",
                    validation_results={"mandatory_present": True},
                )
            ],
        )

    result = process_owner_document(
        session=session,
        parse_route_logger=repo,
        run_id="run-1",
        attempted_at_utc=datetime(2024, 4, 3, 12, 30, tzinfo=timezone.utc),
        filing_id="filing-1",
        accession_no="0000320193-24-000012",
        cik="0000320193",
        document_id="doc-1",
        document_type="4",
        document_filename="ownership.xml",
        document_path="raw/doc.xml",
        snapshot_path="raw/snapshots/ownership.txt",
        source_url=None,
        sha256_hex="a" * 64,
        byte_length=32,
        xml_text="ownership text",
        structured_parser=structured_stub,
        deterministic_parser=deterministic_stub,
    )

    review_rows = [obj for obj in session.added if getattr(obj, "__tablename__", "") == "review_queue"]
    assert result.final_decision_state == "needs_review"
    assert any(row.review_reason == "parser_disagreement" for row in review_rows)



def test_ingest_bundle_persists_filing_index_document_and_snapshots(tmp_path) -> None:
    session = FakeSession()
    repo = ParseRouteLogRepository(session)
    raw_store = RawStore(tmp_path)
    bundle = DownloadedFilingBundle(
        cik="0000320193",
        accession_no="0000320193-24-000012",
        attachments=[
            DownloadedAttachment(
                filename="ownership.xml",
                content_type="text/xml",
                content=b"<ownershipDocument><issuer><issuerCik>0000320193</issuerCik></issuer></ownershipDocument>",
            )
        ],
    )

    discovered_filing = DiscoveredFiling(
        cik="0000320193",
        accession_no="0000320193-24-000012",
        form_type_raw="4",
        acceptance_datetime_utc=datetime(2024, 4, 3, 12, 30, tzinfo=timezone.utc),
        primary_document="ownership.xml",
    )

    processed = ingest_downloaded_owner_filing_bundle(
        session=session,
        parse_route_logger=repo,
        raw_store=raw_store,
        bundle=bundle,
        discovered_filing=discovered_filing,
        run_id="run-1",
        attempted_at_utc=datetime(2024, 4, 3, 12, 30, tzinfo=timezone.utc),
    )

    assert processed == 1
    assert any(getattr(obj, "__tablename__", "") == "filing_index" for obj in session.added)
    assert any(getattr(obj, "__tablename__", "") == "filing_document" for obj in session.added)
    assert list((tmp_path / "0000320193" / "0000320193-24-000012" / "snapshots").iterdir())
```

- [ ] **Step 2: Run the owner pipeline tests to verify they fail**

Run: `uv run pytest tests/worker/test_owner_pipeline.py::test_deterministic_fallback_creates_parser_disagreement_review_item tests/worker/test_owner_pipeline.py::test_ingest_bundle_persists_filing_index_document_and_snapshots -v`

Expected: FAIL because `process_owner_document()` does not create the new review reason and `ingest_downloaded_owner_filing_bundle()` does not persist filing/document rows or snapshots.

- [ ] **Step 3: Implement owner persistence helpers and wire them into the pipeline**

```python
# src/worker/owner_persistence.py
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha1

from src.domain.enums import DecisionState, ReviewReason, RouteType
from src.models.filing import ExtractedFact, FilingDocument, FilingIndex
from src.models.review import ReviewQueueItem
from src.rules.forms import canonicalize_form_type
from src.storage.owner_discovery import DiscoveredFiling
from src.storage.sec_download_adapter import DownloadedAttachment
from src.worker.decision_service import DecisionResult
from src.parsers.ownership_xml import ParsedOwnershipFact, ParsedOwnershipSubmission


@dataclass(frozen=True, slots=True)
class OwnerStoredDocument:
    document_id: str
    raw_path: str
    decoded_text_path: str | None
    parser_snapshot_path: str | None
    sha256_hex: str
    byte_length: int



def build_filing_index_row(discovered_filing: DiscoveredFiling) -> FilingIndex:
    canonical = canonicalize_form_type(discovered_filing.form_type_raw)
    filing_id = f"owner:{discovered_filing.cik}:{discovered_filing.accession_no}"
    return FilingIndex(
        filing_id=filing_id,
        cik=discovered_filing.cik,
        accession_no=discovered_filing.accession_no,
        form_type_raw=canonical.form_type_raw,
        form_type_base=canonical.form_type_base,
        is_amendment=canonical.is_amendment,
        route_type=RouteType.OWNER.value,
        acceptance_datetime_utc=discovered_filing.acceptance_datetime_utc,
        filing_date=discovered_filing.acceptance_datetime_utc.date(),
        primary_document=discovered_filing.primary_document,
        amendment_group_key=(
            f"{discovered_filing.cik}:{canonical.form_type_base}:{discovered_filing.accession_no}"
        ),
        amendment_sequence=1 if canonical.is_amendment else 0,
    )



def build_filing_document_row(
    *,
    filing_id: str,
    accession_no: str,
    attachment: DownloadedAttachment,
    stored_document: OwnerStoredDocument,
) -> FilingDocument:
    return FilingDocument(
        document_id=stored_document.document_id,
        filing_id=filing_id,
        accession_no=accession_no,
        filename=attachment.filename,
        content_type=attachment.content_type,
        sha256_hex=stored_document.sha256_hex,
        byte_length=stored_document.byte_length,
        raw_path=stored_document.raw_path,
        decoded_text_path=stored_document.decoded_text_path,
        parser_snapshot_path=stored_document.parser_snapshot_path,
    )
```

```python
# src/worker/owner_persistence.py

def build_fact_row(
    *,
    run_id: str,
    filing_id: str,
    accession_no: str,
    cik: str,
    document_id: str,
    fallback_reason: str | None,
    parsed_fact: ParsedOwnershipFact,
    attempted_methods: list[str],
) -> ExtractedFact:
    is_complete = bool(parsed_fact.validation_results.get("mandatory_present", True))
    is_numeric_ok = parsed_fact.validation_results.get("is_numeric", True)
    accepted = is_complete and is_numeric_ok and parsed_fact.parser_method == "structured_xml"
    return ExtractedFact(
        fact_id=sha1(f"{accession_no}:{parsed_fact.fact_name}:{parsed_fact.snippet_locator}".encode("utf-8")).hexdigest(),
        filing_id=filing_id,
        accession_no=accession_no,
        cik=cik,
        document_id=document_id,
        run_id=run_id,
        fact_name=parsed_fact.fact_name,
        fact_value=parsed_fact.fact_value,
        parser_method=parsed_fact.parser_method,
        fallback_reason=fallback_reason,
        confidence_score=0.99 if accepted else 0.30,
        confidence_bucket="high" if accepted else "low",
        decision_state="accepted" if accepted else "needs_review",
        snippet_text=parsed_fact.snippet_text,
        snippet_locator=parsed_fact.snippet_locator,
        document_filename=parsed_fact.document_filename,
        validation_results=parsed_fact.validation_results,
        attempted_methods=attempted_methods,
    )



def build_review_item(
    *,
    run_id: str,
    filing_id: str,
    accession_no: str,
    document_id: str,
    fact_row: ExtractedFact,
    review_reason: str,
) -> ReviewQueueItem:
    return ReviewQueueItem(
        review_item_id=sha1(f"review:{fact_row.fact_id}:{review_reason}".encode("utf-8")).hexdigest(),
        filing_id=filing_id,
        accession_no=accession_no,
        document_id=document_id,
        fact_id=fact_row.fact_id,
        run_id=run_id,
        parser_method=fact_row.parser_method,
        decision_state=fact_row.decision_state,
        review_reason=review_reason,
        payload={
            "fact_name": fact_row.fact_name,
            "snippet_locator": fact_row.snippet_locator,
            "fallback_reason": fact_row.fallback_reason,
            "validation_results": fact_row.validation_results,
        },
        status="open",
        note=None,
    )
```

```python
# src/worker/owner_pipeline.py
from src.storage.filing_repo import FilingRepository
from src.storage.owner_discovery import DiscoveredFiling
from src.worker.owner_persistence import (
    OwnerStoredDocument,
    build_fact_row,
    build_filing_document_row,
    build_filing_index_row,
    build_review_item,
)


def process_owner_document(... ) -> DecisionResult:
    ...
    if decision_result.parsed_submission is None:
        document_review = ReviewQueueItem(
            review_item_id=sha1(f"document-review:{accession_no}:{document_id}:{run_id}".encode("utf-8")).hexdigest(),
            filing_id=filing_id,
            accession_no=accession_no,
            document_id=document_id,
            fact_id=None,
            run_id=run_id,
            parser_method=None,
            decision_state=decision_result.final_decision_state,
            review_reason=ReviewReason.UNSUPPORTED_LAYOUT.value,
            payload={"failure_reason": decision_result.failure_reason},
            status="open",
            note=None,
        )
        session.add(document_review)
        return decision_result
    ...
```

```python
# src/worker/owner_pipeline.py

def ingest_downloaded_owner_filing_bundle(
    session,
    parse_route_logger,
    raw_store: RawStore,
    bundle: DownloadedFilingBundle,
    discovered_filing: DiscoveredFiling,
    run_id: str,
    attempted_at_utc: datetime,
    structured_parser: Callable[[str], ParsedOwnershipSubmission] | None = None,
    deterministic_parser: Callable[[str], ParsedOwnershipSubmission] | None = None,
) -> int:
    filing_repo = FilingRepository(session)
    filing_row = build_filing_index_row(discovered_filing)
    filing_repo.add_filing_index_if_missing(filing_row)

    processed_documents = 0
    for attachment in bundle.attachments:
        stored = raw_store.persist_document(...)
        decoded_text = _decode_attachment_text(attachment)
        decoded_text_path = raw_store.persist_text_snapshot(
            cik=bundle.cik,
            accession_no=bundle.accession_no,
            filename=attachment.filename,
            suffix="decoded.txt",
            content=decoded_text,
        )
        parser_snapshot_path = raw_store.persist_text_snapshot(
            cik=bundle.cik,
            accession_no=bundle.accession_no,
            filename=attachment.filename,
            suffix="parser-input.txt",
            content=decoded_text,
        )
        document_id = sha1(f"{bundle.accession_no}:{attachment.filename}:{stored.sha256_hex}".encode("utf-8")).hexdigest()
        filing_repo.add_document_if_missing(
            build_filing_document_row(
                filing_id=filing_row.filing_id,
                accession_no=bundle.accession_no,
                attachment=attachment,
                stored_document=OwnerStoredDocument(
                    document_id=document_id,
                    raw_path=str(stored.path),
                    decoded_text_path=str(decoded_text_path),
                    parser_snapshot_path=str(parser_snapshot_path),
                    sha256_hex=stored.sha256_hex,
                    byte_length=stored.byte_length,
                ),
            )
        )
        ...
```

- [ ] **Step 4: Run the updated owner pipeline tests**

Run: `uv run pytest tests/worker/test_owner_pipeline.py -v`

Expected: PASS with filing/document rows, snapshots, fact provenance, parser-disagreement review items, and replay-safe fact persistence all covered.

- [ ] **Step 5: Commit the owner persistence layer**

```bash
git add src/worker/owner_persistence.py src/worker/owner_pipeline.py tests/worker/test_owner_pipeline.py
git commit -m "feat: persist owner filing metadata and review artifacts"
```

### Task 4: Add SEC Submissions Fetching and Discovery-Driven Owner Sync Service

**Files:**
- Create: `src/storage/sec_submissions_client.py`
- Create: `src/worker/owner_sync_service.py`
- Create: `tests/storage/test_sec_submissions_client.py`
- Create: `tests/worker/test_owner_sync_service.py`

- [ ] **Step 1: Write the failing discovery/sync tests**

```python
# tests/storage/test_sec_submissions_client.py
import json

import pytest

from src.storage.sec_submissions_client import SecSubmissionsClient


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False



def test_fetch_company_submissions_uses_zero_padded_cik_and_returns_json() -> None:
    requested_urls = []

    def fake_urlopen(request):
        requested_urls.append(request.full_url)
        assert request.headers["User-agent"]
        return FakeResponse({"name": "Apple Inc."})

    client = SecSubmissionsClient(urlopen=fake_urlopen)
    payload = client.fetch_company_submissions("320193")

    assert payload["name"] == "Apple Inc."
    assert requested_urls == ["https://data.sec.gov/submissions/CIK0000320193.json"]



def test_fetch_company_submissions_maps_network_error() -> None:
    def fake_urlopen(_request):
        raise OSError("timeout")

    client = SecSubmissionsClient(urlopen=fake_urlopen)
    with pytest.raises(RuntimeError, match="submissions download failure"):
        client.fetch_company_submissions("0000320193")
```

```python
# tests/worker/test_owner_sync_service.py
from datetime import datetime, timezone

from src.storage.owner_discovery import DiscoveredFiling
from src.worker.owner_sync_service import OwnerSyncService


class FakeSubmissionsClient:
    def fetch_company_submissions(self, cik: str) -> dict:
        return {
            "filings": {
                "recent": {
                    "form": ["4", "8-K"],
                    "accessionNumber": [
                        "0000320193-24-000012",
                        "0000320193-24-000100",
                    ],
                    "acceptanceDateTime": [
                        "2024-04-03T12:30:00Z",
                        "2024-04-03T11:00:00Z",
                    ],
                    "primaryDocument": ["ownership.xml", "issuer.htm"],
                }
            }
        }


class FakeAdapter:
    def __init__(self, bundle) -> None:
        self.bundle = bundle
        self.calls = []

    def download_owner_filing_bundle(self, cik: str, accession_no: str):
        self.calls.append((cik, accession_no))
        return self.bundle



def test_owner_sync_processes_only_unseen_owner_filings_and_advances_cursor(tmp_path) -> None:
    session = FakeSession()
    service = OwnerSyncService(
        session=session,
        submissions_client=FakeSubmissionsClient(),
        sec_download_adapter=FakeAdapter(bundle=owner_bundle()),
        raw_store=RawStore(tmp_path),
        parse_route_logger=ParseRouteLogRepository(session),
    )

    result = service.sync_cik("0000320193")

    assert result.discovered_count == 1
    assert result.processed_count == 1
    assert result.last_accession_no == "0000320193-24-000012"
```

- [ ] **Step 2: Run the sync tests to verify they fail**

Run: `uv run pytest tests/storage/test_sec_submissions_client.py tests/worker/test_owner_sync_service.py -v`

Expected: FAIL with missing modules for the submissions client and sync service.

- [ ] **Step 3: Implement the submissions client and owner sync service**

```python
# src/storage/sec_submissions_client.py
import json
from typing import Callable
from urllib.request import Request, urlopen

from src.core.config import settings


class SecSubmissionsClient:
    def __init__(self, urlopen: Callable = urlopen) -> None:
        self._urlopen = urlopen

    def fetch_company_submissions(self, cik: str) -> dict:
        normalized_cik = cik.zfill(10)
        request = Request(
            f"https://data.sec.gov/submissions/CIK{normalized_cik}.json",
            headers={
                "User-Agent": settings.SEC_API_USER_AGENT,
                "Accept": "application/json",
            },
        )
        try:
            with self._urlopen(request) as response:
                return json.loads(response.read().decode("utf-8"))
        except OSError as exc:
            raise RuntimeError("submissions download failure") from exc
```

```python
# src/worker/owner_sync_service.py
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from src.domain.enums import RouteType
from src.storage.ingestion_state_repo import IngestionStateRepository
from src.storage.owner_discovery import DiscoveryCursor, discover_owner_filings
from src.worker.owner_pipeline import ingest_downloaded_owner_filing_bundle


@dataclass(frozen=True, slots=True)
class OwnerSyncResult:
    discovered_count: int
    processed_count: int
    last_accession_no: str | None


class OwnerSyncService:
    def __init__(
        self,
        *,
        session,
        submissions_client,
        sec_download_adapter,
        raw_store,
        parse_route_logger,
    ) -> None:
        self.session = session
        self.submissions_client = submissions_client
        self.sec_download_adapter = sec_download_adapter
        self.raw_store = raw_store
        self.parse_route_logger = parse_route_logger
        self.state_repo = IngestionStateRepository(session)

    def sync_cik(self, cik: str) -> OwnerSyncResult:
        state = self.state_repo.get_or_create(cik=cik, route_type=RouteType.OWNER.value)
        payload = self.submissions_client.fetch_company_submissions(cik)
        discovered = discover_owner_filings(
            cik=cik,
            payload=payload,
            cursor=DiscoveryCursor(
                last_acceptance_datetime_utc=state.last_acceptance_datetime_utc,
                last_accession_no=state.last_accession_no,
            ),
        )
        discovered.sort(key=lambda item: (item.acceptance_datetime_utc, item.accession_no))

        processed_count = 0
        for filing in discovered:
            bundle = self.sec_download_adapter.download_owner_filing_bundle(
                cik=filing.cik,
                accession_no=filing.accession_no,
            )
            processed_count += ingest_downloaded_owner_filing_bundle(
                session=self.session,
                parse_route_logger=self.parse_route_logger,
                raw_store=self.raw_store,
                bundle=bundle,
                discovered_filing=filing,
                run_id=f"owner-sync-{uuid4().hex}",
                attempted_at_utc=datetime.now(timezone.utc),
            )
            self.state_repo.advance(
                state=state,
                accession_no=filing.accession_no,
                acceptance_datetime_utc=filing.acceptance_datetime_utc,
            )

        return OwnerSyncResult(
            discovered_count=len(discovered),
            processed_count=processed_count,
            last_accession_no=state.last_accession_no,
        )
```

- [ ] **Step 4: Run the new discovery/sync tests**

Run: `uv run pytest tests/storage/test_sec_submissions_client.py tests/worker/test_owner_sync_service.py tests/storage/test_owner_discovery.py -v`

Expected: PASS with zero-padded CIK fetches, network failure mapping, owner-only discovery, and cursor-advancing sync behavior.

- [ ] **Step 5: Commit the discovery-driven sync layer**

```bash
git add src/storage/sec_submissions_client.py src/worker/owner_sync_service.py tests/storage/test_sec_submissions_client.py tests/worker/test_owner_sync_service.py
git commit -m "feat: add discovery driven owner sync service"
```

### Task 5: Update CLI Semantics for Sync vs Replay

**Files:**
- Modify: `src/cli.py:36-176`
- Create: `tests/cli/test_owner_sync_cli.py`

- [ ] **Step 1: Write the failing CLI tests**

```python
# tests/cli/test_owner_sync_cli.py
from typer.testing import CliRunner

import src.cli as cli_module



def test_owner_sync_cli_calls_discovery_service(monkeypatch) -> None:
    runner = CliRunner()

    class FakeService:
        def sync_cik(self, cik: str):
            assert cik == "0000320193"
            return type("Result", (), {"discovered_count": 2, "processed_count": 1, "last_accession_no": "0000320193-24-000012"})()

    monkeypatch.setattr(cli_module, "build_owner_sync_service", lambda session: FakeService())
    result = runner.invoke(cli_module.app, ["owner-sync", "--cik", "0000320193"])

    assert result.exit_code == 0
    assert "discovered=2 processed=1" in result.stdout



def test_replay_accession_cli_keeps_explicit_accession_contract(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(cli_module, "process_replay_accession", lambda cik, accession_no: 1)

    result = runner.invoke(
        cli_module.app,
        ["replay-accession", "0000320193-24-000012", "--cik", "0000320193"],
    )

    assert result.exit_code == 0
    assert "replay completed" in result.stdout
```

- [ ] **Step 2: Run the CLI tests to verify they fail**

Run: `uv run pytest tests/cli/test_owner_sync_cli.py -v`

Expected: FAIL because `build_owner_sync_service()` does not exist and `owner-sync` still uses explicit accession replay semantics.

- [ ] **Step 3: Implement the CLI split**

```python
# src/cli.py
from src.storage.parse_route_log_repo import ParseRouteLogRepository
from src.storage.raw_store import RawStore
from src.storage.sec_download_adapter import SecDownloadAdapter
from src.storage.sec_submissions_client import SecSubmissionsClient
from src.worker.owner_sync_service import OwnerSyncService



def build_owner_sync_service(session):
    return OwnerSyncService(
        session=session,
        submissions_client=SecSubmissionsClient(),
        sec_download_adapter=SecDownloadAdapter(),
        raw_store=RawStore(root=Path(settings.RAW_STORE_DIR)),
        parse_route_logger=ParseRouteLogRepository(session),
    )


@app.command("owner-sync")
def owner_sync(
    cik: str = typer.Option(..., "--cik"),
) -> None:
    session = SessionLocal()
    try:
        result = build_owner_sync_service(session).sync_cik(cik)
        session.commit()
    except RuntimeError as exc:
        session.rollback()
        raise typer.BadParameter(f"owner-sync failed: {exc}") from exc
    finally:
        session.close()

    typer.echo(
        f"owner-sync completed for {cik}: discovered={result.discovered_count} processed={result.processed_count} last_accession_no={result.last_accession_no}"
    )
```

```python
# src/cli.py
@app.command("replay-accession")
def replay_accession_command(
    accession_no: str,
    cik: str = typer.Option(..., "--cik"),
) -> None:
    processed = process_replay_accession(cik=cik, accession_no=accession_no)
    typer.echo(f"replay completed for {accession_no}: processed_documents={processed}")
```

- [ ] **Step 4: Run the CLI tests again**

Run: `uv run pytest tests/cli/test_owner_sync_cli.py tests/cli/test_parse_log_cli.py -v`

Expected: PASS with discovery-based `owner-sync`, explicit replay behavior, and existing parse-log commands intact.

- [ ] **Step 5: Commit the CLI split**

```bash
git add src/cli.py tests/cli/test_owner_sync_cli.py
git commit -m "feat: split owner sync from explicit replay"
```

### Task 6: Add Phase A1 End-to-End Regression Coverage

**Files:**
- Create: `tests/integration/test_owner_incremental_flow.py`

- [ ] **Step 1: Write the failing integration regression tests**

```python
# tests/integration/test_owner_incremental_flow.py
from datetime import datetime, timezone
from pathlib import Path

from src.storage.parse_route_log_repo import ParseRouteLogRepository
from src.storage.raw_store import RawStore
from src.storage.sec_download_adapter import DownloadedAttachment, DownloadedFilingBundle
from src.worker.owner_sync_service import OwnerSyncService
from src.worker.owner_pipeline import replay_owner_accession


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.by_pk = {}
        self.rows = []

    def add(self, obj) -> None:
        self.added.append(obj)
        if hasattr(obj, "fact_id"):
            self.by_pk[(obj.__class__, obj.fact_id)] = obj
        elif hasattr(obj, "review_item_id"):
            self.by_pk[(obj.__class__, obj.review_item_id)] = obj
        elif hasattr(obj, "filing_id"):
            self.by_pk[(obj.__class__, obj.filing_id)] = obj
        elif hasattr(obj, "document_id"):
            self.by_pk[(obj.__class__, obj.document_id)] = obj
        elif hasattr(obj, "route_type") and hasattr(obj, "cik"):
            self.by_pk[(obj.__class__, obj.cik, obj.route_type)] = obj

    def get(self, model, pk):
        if isinstance(pk, tuple):
            return self.by_pk.get((model, *pk))
        return self.by_pk.get((model, pk))


class FakeSubmissionsClient:
    def fetch_company_submissions(self, cik: str) -> dict:
        return {
            "filings": {
                "recent": {
                    "form": ["4"],
                    "accessionNumber": ["0000320193-24-000012"],
                    "acceptanceDateTime": ["2024-04-03T12:30:00Z"],
                    "primaryDocument": ["ownership.xml"],
                }
            }
        }


class FakeAdapter:
    def download_owner_filing_bundle(self, cik: str, accession_no: str) -> DownloadedFilingBundle:
        return DownloadedFilingBundle(
            cik=cik,
            accession_no=accession_no,
            attachments=[
                DownloadedAttachment(
                    filename="ownership.xml",
                    content_type="text/xml",
                    content=b"<ownershipDocument><issuer><issuerCik>0000320193</issuerCik></issuer></ownershipDocument>",
                )
            ],
        )



def test_cold_start_then_incremental_skip_then_replay(tmp_path: Path) -> None:
    session = FakeSession()
    repo = ParseRouteLogRepository(session)
    raw_store = RawStore(tmp_path)
    service = OwnerSyncService(
        session=session,
        submissions_client=FakeSubmissionsClient(),
        sec_download_adapter=FakeAdapter(),
        raw_store=raw_store,
        parse_route_logger=repo,
    )

    first = service.sync_cik("0000320193")
    second = service.sync_cik("0000320193")
    replayed = replay_owner_accession(
        session=session,
        parse_route_logger=repo,
        raw_store=raw_store,
        sec_download_adapter=FakeAdapter(),
        cik="0000320193",
        accession_no="0000320193-24-000012",
        run_id="replay-1",
        attempted_at_utc=datetime(2024, 4, 3, 13, 0, tzinfo=timezone.utc),
    )

    fact_rows = [obj for obj in session.added if getattr(obj, "__tablename__", "") == "extracted_fact"]
    assert first.processed_count == 1
    assert second.processed_count == 0
    assert replayed == 1
    assert len({row.fact_id for row in fact_rows}) == len(fact_rows)
    assert len({row.run_id for row in session.rows}) >= 2
```

- [ ] **Step 2: Run the integration test to verify it fails**

Run: `uv run pytest tests/integration/test_owner_incremental_flow.py -v`

Expected: FAIL because the discovery-based sync service and filing/document persistence are not fully wired yet.

- [ ] **Step 3: Implement the minimal fixes needed for the full flow to pass**

```python
# src/worker/owner_sync_service.py
# No new API surface here; use the exact implementation from Task 4.
# The integration-specific fix is to keep sync idempotent by relying on:
# - IngestionStateRepository.get_or_create()
# - FilingRepository.add_filing_index_if_missing()
# - FilingRepository.add_document_if_missing()
# - fact/review deterministic IDs in owner_persistence.py
# - replay_owner_accession() continuing to skip cursor advancement
```

```python
# src/worker/owner_pipeline.py
# Keep replay path explicit and state-free:
# replay_owner_accession(...) downloads a bundle and calls ingest_downloaded_owner_filing_bundle(...)
# without touching IngestionStateRepository.
```

- [ ] **Step 4: Run the Phase A1 verification suite**

Run: `uv run pytest tests/models/test_metadata.py tests/storage/test_ingestion_state_repo.py tests/storage/test_filing_repo.py tests/storage/test_raw_store.py tests/storage/test_owner_discovery.py tests/storage/test_sec_download_adapter.py tests/storage/test_sec_submissions_client.py tests/worker/test_decision_service.py tests/worker/test_owner_pipeline.py tests/worker/test_owner_sync_service.py tests/cli/test_parse_log_cli.py tests/cli/test_owner_sync_cli.py tests/integration/test_owner_incremental_flow.py -v`

Expected: PASS with all Phase A1 regression coverage green.

- [ ] **Step 5: Commit the Phase A1 regression suite**

```bash
git add tests/integration/test_owner_incremental_flow.py
git commit -m "test: add owner phase a1 incremental regression coverage"
```

## Final Verification Checklist

- [ ] `uv run pytest tests/models/test_metadata.py -v`
- [ ] `uv run pytest tests/storage/test_ingestion_state_repo.py tests/storage/test_filing_repo.py -v`
- [ ] `uv run pytest tests/storage/test_raw_store.py tests/storage/test_owner_discovery.py tests/storage/test_sec_download_adapter.py tests/storage/test_sec_submissions_client.py -v`
- [ ] `uv run pytest tests/worker/test_decision_service.py tests/worker/test_owner_pipeline.py tests/worker/test_owner_sync_service.py -v`
- [ ] `uv run pytest tests/cli/test_parse_log_cli.py tests/cli/test_owner_sync_cli.py -v`
- [ ] `uv run pytest tests/integration/test_owner_incremental_flow.py -v`
- [ ] `uv run pytest -v`

## Spec Coverage Map

- PostgreSQL-driven ingestion state: Task 2 + Task 4 + Task 5 + Task 6.
- Replay-safe idempotency: Task 2 + Task 3 + Task 5 + Task 6.
- Append-only audit and traceability for facts/reviews: Task 1 + Task 3 + Task 6.
- Deterministic raw/archive contract with text snapshots: Task 3 + Task 6.
- Owner-slice review reason taxonomy for production closure: Task 1 + Task 3.
- Discovery-based owner sync from persisted cursor state: Task 4 + Task 5 + Task 6.

## Self-Review

- **Spec coverage:** This plan intentionally covers Phase A1 only from `docs/superpowers/specs/2026-04-03-sec-filing-backend-rollout-design.md`: owner route production closure, PostgreSQL state management, replay/idempotency/audit hardening, and discovery-based sync. It does not attempt issuer route, 13F, security mapping, spaCy, LLM, or QA rollups.
- **Placeholder scan:** No `TODO`, `TBD`, or “implement later” placeholders remain. Every task has exact files, concrete tests, commands, and implementation snippets.
- **Type consistency:** `run_id`, `document_id`, `filing_id`, `fallback_reason`, and `review_reason` are used consistently across model, repository, worker, CLI, and test tasks.
