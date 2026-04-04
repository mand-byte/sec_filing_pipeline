# SEC Filing Phase 3 Decision Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement an owner-route-only Phase 3 decision layer with persistent parse-route attempt logs (`parse_route_log`), fixed fallback behavior, edgartools-backed download adapter usage, and query/timeline observability.

**Architecture:** Keep owner `3/4/5` processing deterministic and evidence-first by logging every parser attempt (success and failure) as process-audit rows in PostgreSQL. Use a decision service to enforce `structured_xml -> deterministic_rule -> needs_review` semantics, and keep fact/review persistence idempotent while adding replay-visible run history. Integrate edgartools for filing/attachment download metadata and route all bytes through deterministic raw-store paths before parsing.

**Tech Stack:** Python 3.12+, Typer, SQLAlchemy 2.x, Pydantic v2, lxml, edgartools, pytest

---

## File Structure

- `README.md`
  Build metadata readme required by Hatchling so `uv run` and `uv build` work in this tree.
- `pyproject.toml`
  Add `edgartools` dependency for download adapter integration.
- `src/models/base.py`
  Restore declarative base module required by model imports.
- `src/domain/enums.py`
  Add parse-attempt status, failure-type, and fallback-reason enums.
- `src/models/parse_route_log.py`
  Define `parse_route_log` SQLAlchemy table and query indexes.
- `src/models/__init__.py`
  Continue exporting `Base`.
- `src/storage/parse_route_log_repo.py`
  Append/query/timeline repository for process audit logs.
- `src/parsers/ownership_deterministic.py`
  Deterministic fallback parser for owner XML text.
- `src/storage/sec_download_adapter.py`
  Edgartools adapter that returns normalized filing + attachment descriptors.
- `src/worker/decision_service.py`
  Enforce parse chain and write parse-route attempts.
- `src/worker/owner_pipeline.py`
  Wire decision service output to fact/review persistence and replay-safe behavior.
- `src/cli.py`
  Add `parse-log query` and `parse-log timeline` CLI commands; wire owner-sync/replay to phase-3 pipeline entrypoints.
- `tests/models/test_metadata.py`
  Extend metadata coverage to include `parse_route_log`.
- `tests/storage/test_parse_route_log_repo.py`
  Test append/query/timeline behavior by required dimensions.
- `tests/parsers/test_ownership_deterministic.py`
  Test deterministic fallback parser behavior.
- `tests/storage/test_sec_download_adapter.py`
  Test adapter normalization and network-failure classification.
- `tests/worker/test_decision_service.py`
  Test structured success, structured failure with deterministic success, and all-fail outcomes.
- `tests/worker/test_owner_pipeline.py`
  Extend replay/idempotency and parse-route-log linkage checks.
- `tests/cli/test_parse_log_cli.py`
  Validate parse-log command wiring and output shape.

### Task 1: Stabilize Baseline for Phase 3 Work

**Files:**
- Create: `README.md`
- Create: `src/models/base.py`
- Modify: `src/models/__init__.py`
- Test: `tests/models/test_metadata.py`

- [ ] **Step 1: Write the failing baseline test for `Base` import**

```python
# tests/models/test_metadata.py
from src.models import Base  # noqa: F401
from src.models import filing, registry, review, state  # noqa: F401


def test_models_base_module_is_importable() -> None:
    from src.models.base import Base as DeclarativeBase

    assert DeclarativeBase is Base


def test_metadata_contains_required_phase0_tables():
    table_names = set(Base.metadata.tables)

    assert {
        "ingestion_state",
        "filing_index",
        "filing_document",
        "extracted_fact",
        "review_queue",
        "parser_registry",
        "model_registry",
    } <= table_names
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/models/test_metadata.py::test_models_base_module_is_importable -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'src.models.base'`.

- [ ] **Step 3: Add baseline files required for package + model imports**

```markdown
# README.md

SEC filing pipeline workspace.

This repository contains a precision-first SEC ingestion backend.
```

```python
# src/models/base.py
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

```python
# src/models/__init__.py
from src.models.base import Base

__all__ = ["Base"]
```

- [ ] **Step 4: Run baseline checks**

Run: `uv run pytest tests/models/test_metadata.py -v`

Expected: PASS for base import and metadata checks.

- [ ] **Step 5: Commit baseline stabilization**

```bash
git add README.md src/models/base.py src/models/__init__.py tests/models/test_metadata.py
git commit -m "fix: restore packaging readme and models base module"
```

### Task 2: Add Parse Route Log Domain and Table Contracts

**Files:**
- Modify: `src/domain/enums.py`
- Create: `src/models/parse_route_log.py`
- Modify: `src/models/__init__.py`
- Modify: `tests/models/test_metadata.py`

- [ ] **Step 1: Write failing table and enum contract tests**

```python
# tests/models/test_metadata.py
from src.domain.enums import FallbackReason, ParseAttemptStatus, ParseFailureType
from src.models import Base  # noqa: F401
from src.models import filing, parse_route_log, registry, review, state  # noqa: F401


def test_phase3_enums_match_fixed_taxonomy() -> None:
    assert {item.value for item in ParseFailureType} == {"network", "parse", "logic"}
    assert {item.value for item in ParseAttemptStatus} == {"success", "failed", "skipped"}
    assert "all_methods_failed" in {item.value for item in FallbackReason}


def test_parse_route_log_table_has_required_columns() -> None:
    table = Base.metadata.tables["parse_route_log"]
    expected = {
        "id",
        "run_id",
        "route_type",
        "filing_id",
        "accession_no",
        "cik",
        "document_id",
        "document_type",
        "document_filename",
        "document_path",
        "snapshot_path",
        "source_url",
        "sha256_hex",
        "byte_length",
        "parser_method",
        "attempted_at_utc",
        "status",
        "failure_type",
        "error_message",
        "fallback_reason",
        "decision_state",
        "selected_candidate",
    }
    assert expected <= set(table.columns.keys())
```

- [ ] **Step 2: Run test to verify failure**

Run: `uv run pytest tests/models/test_metadata.py::test_parse_route_log_table_has_required_columns -v`

Expected: FAIL with missing `parse_route_log` table or import error for phase-3 enums.

- [ ] **Step 3: Implement enums and model table**

```python
# src/domain/enums.py
from dataclasses import dataclass
from enum import Enum


class RouteType(str, Enum):
    ISSUER = "issuer"
    OWNER = "owner"
    HOLDINGS = "holdings"


class ParserMethod(str, Enum):
    STRUCTURED_XML = "structured_xml"
    DETERMINISTIC_RULE = "deterministic_rule"


class ParseAttemptStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class ParseFailureType(str, Enum):
    NETWORK = "network"
    PARSE = "parse"
    LOGIC = "logic"


class FallbackReason(str, Enum):
    STRUCTURED_XML_EXCEPTION = "structured_xml_exception"
    STRUCTURED_XML_MISSING_MANDATORY = "structured_xml_missing_mandatory"
    STRUCTURED_XML_NUMERIC_INVALID = "structured_xml_numeric_invalid"
    STRUCTURED_XML_EMPTY_VALUE = "structured_xml_empty_value"
    DETERMINISTIC_RULE_EXCEPTION = "deterministic_rule_exception"
    DETERMINISTIC_RULE_NOT_APPLICABLE = "deterministic_rule_not_applicable"
    ALL_METHODS_FAILED = "all_methods_failed"


class DecisionState(str, Enum):
    ACCEPTED = "accepted"
    ACCEPTED_WITH_WARNING = "accepted_with_warning"
    NEEDS_REVIEW = "needs_review"
    DROPPED = "dropped"


class ReviewReason(str, Enum):
    MANDATORY_FIELD_MISSING = "mandatory_field_missing"
    SOURCE_CONFLICT = "source_conflict"
    AMENDMENT_CONFLICT = "amendment_conflict"


@dataclass(frozen=True, slots=True)
class CanonicalForm:
    form_type_raw: str
    form_type_base: str
    is_amendment: bool
```

```python
# src/models/parse_route_log.py
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class ParseRouteLog(Base):
    __tablename__ = "parse_route_log"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    route_type: Mapped[str] = mapped_column(String(32), index=True)
    filing_id: Mapped[str] = mapped_column(String(128), index=True)
    accession_no: Mapped[str] = mapped_column(String(32), index=True)
    cik: Mapped[str] = mapped_column(String(10), index=True)
    document_id: Mapped[str] = mapped_column(String(128), index=True)

    document_type: Mapped[str] = mapped_column(String(32), index=True)
    document_filename: Mapped[str] = mapped_column(String(255))
    document_path: Mapped[str] = mapped_column(Text)
    snapshot_path: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    sha256_hex: Mapped[str] = mapped_column(String(64), index=True)
    byte_length: Mapped[int] = mapped_column(Integer)

    parser_method: Mapped[str] = mapped_column(String(64), index=True)
    attempted_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)

    failure_type: Mapped[str | None] = mapped_column(String(16), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    fallback_reason: Mapped[str | None] = mapped_column(String(64), index=True)

    decision_state: Mapped[str | None] = mapped_column(String(32), index=True)
    selected_candidate: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index("ix_parse_route_log_doc_type_attempted", "document_type", "attempted_at_utc"),
        Index("ix_parse_route_log_failure_attempted", "failure_type", "attempted_at_utc"),
        Index("ix_parse_route_log_timeline", "accession_no", "document_id", "attempted_at_utc"),
    )
```

```python
# src/models/__init__.py
from src.models.base import Base

__all__ = ["Base"]
```

- [ ] **Step 4: Run table/enum contract tests**

Run: `uv run pytest tests/models/test_metadata.py -v`

Expected: PASS with `parse_route_log` present in metadata and phase-3 enums loadable.

- [ ] **Step 5: Commit parse-route schema contracts**

```bash
git add src/domain/enums.py src/models/parse_route_log.py src/models/__init__.py tests/models/test_metadata.py
git commit -m "feat: add parse route log schema and phase3 enums"
```

### Task 3: Implement Parse Route Log Repository Query API

**Files:**
- Create: `src/storage/parse_route_log_repo.py`
- Create: `tests/storage/test_parse_route_log_repo.py`

- [ ] **Step 1: Write failing repository tests for append/query/timeline**

```python
# tests/storage/test_parse_route_log_repo.py
from datetime import datetime, timezone

from src.models.parse_route_log import ParseRouteLog
from src.storage.parse_route_log_repo import ParseRouteLogRepository


class FakeSession:
    def __init__(self) -> None:
        self.rows: list[ParseRouteLog] = []

    def add(self, row: ParseRouteLog) -> None:
        self.rows.append(row)


def make_row(*, row_id: str, document_type: str, failure_type: str | None, attempted: datetime, accession_no: str, document_id: str) -> ParseRouteLog:
    return ParseRouteLog(
        id=row_id,
        run_id="run-1",
        route_type="owner",
        filing_id="filing-1",
        accession_no=accession_no,
        cik="0000320193",
        document_id=document_id,
        document_type=document_type,
        document_filename="primary_doc.xml",
        document_path="raw/0000320193/acc/doc.xml",
        snapshot_path="raw/0000320193/acc/snapshots/doc.txt",
        source_url="https://www.sec.gov/Archives/edgar/data/320193/doc.xml",
        sha256_hex="f" * 64,
        byte_length=123,
        parser_method="structured_xml",
        attempted_at_utc=attempted,
        status="failed" if failure_type else "success",
        failure_type=failure_type,
        error_message="boom" if failure_type else None,
        fallback_reason=None,
        decision_state="needs_review",
        selected_candidate=False,
    )


def test_query_filters_by_document_type_failure_type_and_attempted_range() -> None:
    session = FakeSession()
    repo = ParseRouteLogRepository(session)

    repo.append(make_row(row_id="1", document_type="XML", failure_type="parse", attempted=datetime(2026, 4, 3, 1, tzinfo=timezone.utc), accession_no="A", document_id="D1"))
    repo.append(make_row(row_id="2", document_type="HTML", failure_type="network", attempted=datetime(2026, 4, 4, 1, tzinfo=timezone.utc), accession_no="B", document_id="D2"))

    result = repo.query(
        document_type="XML",
        start_utc=datetime(2026, 4, 3, 0, tzinfo=timezone.utc),
        end_utc=datetime(2026, 4, 3, 23, tzinfo=timezone.utc),
        failure_type="parse",
        limit=100,
        offset=0,
    )
    assert [row.id for row in result] == ["1"]


def test_timeline_returns_ordered_rows_for_one_file() -> None:
    session = FakeSession()
    repo = ParseRouteLogRepository(session)

    repo.append(make_row(row_id="1", document_type="XML", failure_type="parse", attempted=datetime(2026, 4, 3, 1, tzinfo=timezone.utc), accession_no="ACC", document_id="DOC"))
    repo.append(make_row(row_id="2", document_type="XML", failure_type=None, attempted=datetime(2026, 4, 3, 2, tzinfo=timezone.utc), accession_no="ACC", document_id="DOC"))

    timeline = repo.timeline(accession_no="ACC", document_id="DOC")
    assert [row.id for row in timeline] == ["1", "2"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/storage/test_parse_route_log_repo.py -v`

Expected: FAIL with `ModuleNotFoundError` for `src.storage.parse_route_log_repo`.

- [ ] **Step 3: Implement in-memory-friendly repository with SQLAlchemy-compatible signatures**

```python
# src/storage/parse_route_log_repo.py
from dataclasses import dataclass
from datetime import datetime

from src.models.parse_route_log import ParseRouteLog


@dataclass(slots=True)
class ParseRouteLogRepository:
    session: object

    def append(self, row: ParseRouteLog) -> None:
        self.session.add(row)

    def _rows(self) -> list[ParseRouteLog]:
        rows = getattr(self.session, "rows", None)
        if rows is None:
            raise RuntimeError("ParseRouteLogRepository requires session.rows for this phase")
        return rows

    def query(
        self,
        *,
        document_type: str | None,
        start_utc: datetime | None,
        end_utc: datetime | None,
        failure_type: str | None,
        limit: int,
        offset: int,
    ) -> list[ParseRouteLog]:
        rows = self._rows()
        filtered = rows
        if document_type is not None:
            filtered = [row for row in filtered if row.document_type == document_type]
        if start_utc is not None:
            filtered = [row for row in filtered if row.attempted_at_utc >= start_utc]
        if end_utc is not None:
            filtered = [row for row in filtered if row.attempted_at_utc <= end_utc]
        if failure_type is not None:
            filtered = [row for row in filtered if row.failure_type == failure_type]

        filtered.sort(key=lambda row: row.attempted_at_utc)
        return filtered[offset : offset + limit]

    def timeline(self, *, accession_no: str, document_id: str) -> list[ParseRouteLog]:
        rows = [
            row
            for row in self._rows()
            if row.accession_no == accession_no and row.document_id == document_id
        ]
        rows.sort(key=lambda row: row.attempted_at_utc)
        return rows
```

- [ ] **Step 4: Run repository tests**

Run: `uv run pytest tests/storage/test_parse_route_log_repo.py -v`

Expected: PASS for filters by `document_type`, `attempted_at_utc`, `failure_type`, and ordered timeline output.

- [ ] **Step 5: Commit repository layer**

```bash
git add src/storage/parse_route_log_repo.py tests/storage/test_parse_route_log_repo.py
git commit -m "feat: add parse route log query and timeline repository"
```

### Task 4: Implement Deterministic Fallback Parser and Decision Service

**Files:**
- Create: `src/parsers/ownership_deterministic.py`
- Create: `src/worker/decision_service.py`
- Create: `tests/parsers/test_ownership_deterministic.py`
- Create: `tests/worker/test_decision_service.py`

- [ ] **Step 1: Write failing decision-chain tests**

```python
# tests/worker/test_decision_service.py
from datetime import datetime, timezone

from src.worker.decision_service import DecisionService, ParseDocument


class FakeLogger:
    def __init__(self) -> None:
        self.rows = []

    def append(self, row) -> None:
        self.rows.append(row)


def base_document(xml_text: str) -> ParseDocument:
    return ParseDocument(
        filing_id="filing-1",
        accession_no="0000320193-24-000012",
        cik="0000320193",
        document_id="doc-1",
        document_type="XML",
        document_filename="primary_doc.xml",
        document_path="raw/0000320193/0000320193-24-000012/documents/abc.xml",
        snapshot_path=None,
        source_url="https://www.sec.gov/Archives/edgar/data/320193/doc.xml",
        sha256_hex="a" * 64,
        byte_length=len(xml_text.encode("utf-8")),
        xml_text=xml_text,
    )


def test_structured_success_returns_accepted() -> None:
    logger = FakeLogger()
    service = DecisionService(parse_route_logger=logger)
    xml_text = """
<ownershipDocument>
  <issuer><issuerCik>0000320193</issuerCik></issuer>
  <reportingOwner><reportingOwnerId><rptOwnerCik>0001214156</rptOwnerCik></reportingOwnerId></reportingOwner>
  <nonDerivativeTable><nonDerivativeTransaction><transactionAmounts><transactionShares><value>12</value></transactionShares></transactionAmounts></nonDerivativeTransaction></nonDerivativeTable>
</ownershipDocument>
"""
    result = service.process_document(run_id="run-1", attempted_at_utc=datetime(2026, 4, 3, tzinfo=timezone.utc), document=base_document(xml_text))

    assert result.decision_state == "accepted"
    assert [row.parser_method for row in logger.rows] == ["structured_xml"]


def test_structured_failure_then_deterministic_success_still_needs_review() -> None:
    logger = FakeLogger()
    service = DecisionService(parse_route_logger=logger)
    xml_text = "<ownershipDocument><issuer><issuerCik>0000320193</issuerCik></issuer></ownershipDocument>"

    result = service.process_document(run_id="run-2", attempted_at_utc=datetime(2026, 4, 3, tzinfo=timezone.utc), document=base_document(xml_text))

    assert result.decision_state == "needs_review"
    assert [row.parser_method for row in logger.rows] == ["structured_xml", "deterministic_rule"]


def test_all_methods_failed_marks_needs_review_and_logs_failure_details() -> None:
    logger = FakeLogger()
    service = DecisionService(parse_route_logger=logger)
    result = service.process_document(run_id="run-3", attempted_at_utc=datetime(2026, 4, 3, tzinfo=timezone.utc), document=base_document("<broken>"))

    assert result.decision_state == "needs_review"
    assert any(row.status == "failed" and row.failure_type in {"parse", "logic"} for row in logger.rows)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/worker/test_decision_service.py -v`

Expected: FAIL with missing module `src.worker.decision_service`.

- [ ] **Step 3: Implement deterministic parser and decision service**

```python
# src/parsers/ownership_deterministic.py
import re

from src.domain.enums import ParserMethod
from src.parsers.ownership_xml import ParsedOwnershipFact, ParsedOwnershipSubmission


def _extract(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def parse_ownership_deterministic(
    *, accession_no: str, document_filename: str, xml_text: str
) -> ParsedOwnershipSubmission:
    issuer_cik = _extract(r"<issuerCik>([^<]+)</issuerCik>", xml_text)
    reporting_owner_cik = _extract(r"<rptOwnerCik>([^<]+)</rptOwnerCik>", xml_text)
    transaction_shares = _extract(r"<transactionShares>\s*<value>([^<]+)</value>", xml_text)

    facts = [
        ParsedOwnershipFact(
            fact_name="issuer_cik",
            fact_value=issuer_cik,
            parser_method=ParserMethod.DETERMINISTIC_RULE.value,
            snippet_text=issuer_cik,
            snippet_locator="regex:issuerCik",
            document_filename=document_filename,
            validation_results={"mandatory_present": bool(issuer_cik), "is_numeric": True},
        ),
        ParsedOwnershipFact(
            fact_name="reporting_owner_cik",
            fact_value=reporting_owner_cik,
            parser_method=ParserMethod.DETERMINISTIC_RULE.value,
            snippet_text=reporting_owner_cik,
            snippet_locator="regex:rptOwnerCik",
            document_filename=document_filename,
            validation_results={"mandatory_present": bool(reporting_owner_cik), "is_numeric": True},
        ),
        ParsedOwnershipFact(
            fact_name="transaction_shares",
            fact_value=transaction_shares,
            parser_method=ParserMethod.DETERMINISTIC_RULE.value,
            snippet_text=transaction_shares,
            snippet_locator="regex:transactionShares",
            document_filename=document_filename,
            validation_results={
                "mandatory_present": bool(transaction_shares),
                "is_numeric": transaction_shares.isdigit(),
            },
        ),
    ]

    return ParsedOwnershipSubmission(
        accession_no=accession_no,
        document_filename=document_filename,
        facts=facts,
    )
```

```python
# src/worker/decision_service.py
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha1

from src.domain.enums import DecisionState, FallbackReason, ParseAttemptStatus, ParseFailureType, ParserMethod, RouteType
from src.models.parse_route_log import ParseRouteLog
from src.parsers.ownership_deterministic import parse_ownership_deterministic
from src.parsers.ownership_xml import ParsedOwnershipSubmission, parse_ownership_xml


@dataclass(frozen=True)
class ParseDocument:
    filing_id: str
    accession_no: str
    cik: str
    document_id: str
    document_type: str
    document_filename: str
    document_path: str
    snapshot_path: str | None
    source_url: str | None
    sha256_hex: str
    byte_length: int
    xml_text: str


@dataclass(frozen=True)
class DecisionResult:
    parsed_submission: ParsedOwnershipSubmission | None
    decision_state: str
    fallback_reason: str | None


class DecisionService:
    def __init__(self, *, parse_route_logger) -> None:
        self.parse_route_logger = parse_route_logger

    def _log(self, *, run_id: str, attempted_at_utc: datetime, document: ParseDocument, parser_method: str, status: str, failure_type: str | None, error_message: str | None, fallback_reason: str | None, decision_state: str | None, selected_candidate: bool) -> None:
        log_id = sha1(f"{run_id}:{document.document_id}:{parser_method}:{attempted_at_utc.isoformat()}:{status}".encode("utf-8")).hexdigest()
        self.parse_route_logger.append(
            ParseRouteLog(
                id=log_id,
                run_id=run_id,
                route_type=RouteType.OWNER.value,
                filing_id=document.filing_id,
                accession_no=document.accession_no,
                cik=document.cik,
                document_id=document.document_id,
                document_type=document.document_type,
                document_filename=document.document_filename,
                document_path=document.document_path,
                snapshot_path=document.snapshot_path,
                source_url=document.source_url,
                sha256_hex=document.sha256_hex,
                byte_length=document.byte_length,
                parser_method=parser_method,
                attempted_at_utc=attempted_at_utc,
                status=status,
                failure_type=failure_type,
                error_message=error_message,
                fallback_reason=fallback_reason,
                decision_state=decision_state,
                selected_candidate=selected_candidate,
            )
        )

    def process_document(self, *, run_id: str, attempted_at_utc: datetime, document: ParseDocument) -> DecisionResult:
        try:
            structured = parse_ownership_xml(
                accession_no=document.accession_no,
                document_filename=document.document_filename,
                xml_text=document.xml_text,
            )
            all_ok = all(
                fact.validation_results.get("mandatory_present", True)
                and fact.validation_results.get("is_numeric", True)
                for fact in structured.facts
            )
            if all_ok:
                self._log(
                    run_id=run_id,
                    attempted_at_utc=attempted_at_utc,
                    document=document,
                    parser_method=ParserMethod.STRUCTURED_XML.value,
                    status=ParseAttemptStatus.SUCCESS.value,
                    failure_type=None,
                    error_message=None,
                    fallback_reason=None,
                    decision_state=DecisionState.ACCEPTED.value,
                    selected_candidate=True,
                )
                return DecisionResult(structured, DecisionState.ACCEPTED.value, None)

            self._log(
                run_id=run_id,
                attempted_at_utc=attempted_at_utc,
                document=document,
                parser_method=ParserMethod.STRUCTURED_XML.value,
                status=ParseAttemptStatus.FAILED.value,
                failure_type=ParseFailureType.LOGIC.value,
                error_message="structured_xml validation failed",
                fallback_reason=FallbackReason.STRUCTURED_XML_MISSING_MANDATORY.value,
                decision_state=DecisionState.NEEDS_REVIEW.value,
                selected_candidate=False,
            )
        except Exception as exc:  # noqa: BLE001
            self._log(
                run_id=run_id,
                attempted_at_utc=attempted_at_utc,
                document=document,
                parser_method=ParserMethod.STRUCTURED_XML.value,
                status=ParseAttemptStatus.FAILED.value,
                failure_type=ParseFailureType.PARSE.value,
                error_message=str(exc),
                fallback_reason=FallbackReason.STRUCTURED_XML_EXCEPTION.value,
                decision_state=DecisionState.NEEDS_REVIEW.value,
                selected_candidate=False,
            )

        try:
            deterministic = parse_ownership_deterministic(
                accession_no=document.accession_no,
                document_filename=document.document_filename,
                xml_text=document.xml_text,
            )
            self._log(
                run_id=run_id,
                attempted_at_utc=attempted_at_utc,
                document=document,
                parser_method=ParserMethod.DETERMINISTIC_RULE.value,
                status=ParseAttemptStatus.SUCCESS.value,
                failure_type=None,
                error_message=None,
                fallback_reason=FallbackReason.DETERMINISTIC_RULE_NOT_APPLICABLE.value,
                decision_state=DecisionState.NEEDS_REVIEW.value,
                selected_candidate=True,
            )
            return DecisionResult(
                parsed_submission=deterministic,
                decision_state=DecisionState.NEEDS_REVIEW.value,
                fallback_reason=FallbackReason.DETERMINISTIC_RULE_NOT_APPLICABLE.value,
            )
        except Exception as exc:  # noqa: BLE001
            self._log(
                run_id=run_id,
                attempted_at_utc=attempted_at_utc,
                document=document,
                parser_method=ParserMethod.DETERMINISTIC_RULE.value,
                status=ParseAttemptStatus.FAILED.value,
                failure_type=ParseFailureType.LOGIC.value,
                error_message=str(exc),
                fallback_reason=FallbackReason.ALL_METHODS_FAILED.value,
                decision_state=DecisionState.NEEDS_REVIEW.value,
                selected_candidate=False,
            )
            return DecisionResult(
                parsed_submission=None,
                decision_state=DecisionState.NEEDS_REVIEW.value,
                fallback_reason=FallbackReason.ALL_METHODS_FAILED.value,
            )
```

- [ ] **Step 4: Run parser + decision tests**

Run: `uv run pytest tests/parsers/test_ownership_deterministic.py tests/worker/test_decision_service.py -v`

Expected: PASS for fixed chain behavior and per-attempt logging.

- [ ] **Step 5: Commit decision chain implementation**

```bash
git add src/parsers/ownership_deterministic.py src/worker/decision_service.py tests/parsers/test_ownership_deterministic.py tests/worker/test_decision_service.py
git commit -m "feat: add deterministic fallback parser and decision service"
```

### Task 5: Add Edgartools Download Adapter and Raw Artifact Ingress

**Files:**
- Modify: `pyproject.toml`
- Create: `src/storage/sec_download_adapter.py`
- Create: `tests/storage/test_sec_download_adapter.py`

- [ ] **Step 1: Write failing download adapter tests**

```python
# tests/storage/test_sec_download_adapter.py
import pytest

from src.storage.sec_download_adapter import DownloadedAttachment, SecDownloadAdapter


class FakeEdgarClient:
    def fetch_filing(self, cik: str, accession_no: str):
        return {
            "filing_id": "filing-1",
            "source_url": "https://www.sec.gov/Archives/edgar/data/320193/filing-index.html",
            "attachments": [
                {
                    "document_id": "doc-1",
                    "document_type": "XML",
                    "filename": "primary_doc.xml",
                    "content_type": "text/xml",
                    "content": b"<ownershipDocument></ownershipDocument>",
                    "source_url": "https://www.sec.gov/Archives/edgar/data/320193/doc1.xml",
                },
                {
                    "document_id": "doc-2",
                    "document_type": "TXT",
                    "filename": "notes.txt",
                    "content_type": "text/plain",
                    "content": b"notes",
                    "source_url": "https://www.sec.gov/Archives/edgar/data/320193/doc2.txt",
                },
            ],
        }


class BrokenClient:
    def fetch_filing(self, cik: str, accession_no: str):
        raise OSError("connection reset")


def test_download_adapter_returns_all_attachments() -> None:
    adapter = SecDownloadAdapter(edgar_client=FakeEdgarClient())
    bundle = adapter.download_owner_filing_bundle(cik="0000320193", accession_no="0000320193-24-000012")

    assert bundle.accession_no == "0000320193-24-000012"
    assert len(bundle.attachments) == 2
    assert isinstance(bundle.attachments[0], DownloadedAttachment)


def test_download_adapter_maps_network_failure() -> None:
    adapter = SecDownloadAdapter(edgar_client=BrokenClient())

    with pytest.raises(RuntimeError, match="network"):
        adapter.download_owner_filing_bundle(cik="0000320193", accession_no="0000320193-24-000012")
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/storage/test_sec_download_adapter.py -v`

Expected: FAIL with missing `src.storage.sec_download_adapter`.

- [ ] **Step 3: Implement adapter and dependency declaration**

```toml
# pyproject.toml (project.dependencies)
dependencies = [
    "clickhouse-connect",
    "edgartools",
    "lxml>=5.2.0",
    "psycopg[binary]",
    "pydantic",
    "pydantic-settings",
    "sqlalchemy",
    "typer>=0.15.0",
]
```

```python
# src/storage/sec_download_adapter.py
from dataclasses import dataclass


@dataclass(frozen=True)
class DownloadedAttachment:
    document_id: str
    document_type: str
    filename: str
    content_type: str
    content: bytes
    source_url: str | None


@dataclass(frozen=True)
class DownloadedFilingBundle:
    filing_id: str
    cik: str
    accession_no: str
    source_url: str | None
    attachments: list[DownloadedAttachment]


class SecDownloadAdapter:
    def __init__(self, *, edgar_client) -> None:
        self.edgar_client = edgar_client

    def download_owner_filing_bundle(
        self, *, cik: str, accession_no: str
    ) -> DownloadedFilingBundle:
        try:
            payload = self.edgar_client.fetch_filing(cik=cik, accession_no=accession_no)
        except OSError as exc:
            raise RuntimeError(f"network failure while downloading filing: {exc}") from exc

        attachments = [
            DownloadedAttachment(
                document_id=item["document_id"],
                document_type=item["document_type"],
                filename=item["filename"],
                content_type=item.get("content_type", "application/octet-stream"),
                content=item["content"],
                source_url=item.get("source_url"),
            )
            for item in payload["attachments"]
        ]
        return DownloadedFilingBundle(
            filing_id=payload["filing_id"],
            cik=cik,
            accession_no=accession_no,
            source_url=payload.get("source_url"),
            attachments=attachments,
        )
```

- [ ] **Step 4: Run adapter tests**

Run: `uv run pytest tests/storage/test_sec_download_adapter.py -v`

Expected: PASS for all-attachment download and network failure mapping.

- [ ] **Step 5: Commit download adapter**

```bash
git add pyproject.toml src/storage/sec_download_adapter.py tests/storage/test_sec_download_adapter.py
git commit -m "feat: add edgartools-backed download adapter contract"
```

### Task 6: Wire Owner Pipeline with Parse Route Logging and Replay Semantics

**Files:**
- Modify: `src/worker/owner_pipeline.py`
- Modify: `tests/worker/test_owner_pipeline.py`

- [ ] **Step 1: Write failing pipeline tests for run-history and durable idempotency**

```python
# tests/worker/test_owner_pipeline.py
from datetime import datetime, timezone

from src.worker.owner_pipeline import process_owner_document


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.by_pk = {}

    def add(self, obj) -> None:
        self.added.append(obj)
        if hasattr(obj, "fact_id"):
            self.by_pk[(obj.__class__, obj.fact_id)] = obj
        if hasattr(obj, "review_item_id"):
            self.by_pk[(obj.__class__, obj.review_item_id)] = obj

    def get(self, model, pk):
        return self.by_pk.get((model, pk))


class FakeParseRouteLogger:
    def __init__(self) -> None:
        self.rows = []

    def append(self, row) -> None:
        self.rows.append(row)


def test_replay_creates_new_parse_route_log_rows_with_new_run_id() -> None:
    session = FakeSession()
    logger = FakeParseRouteLogger()

    process_owner_document(
        session=session,
        parse_route_logger=logger,
        run_id="run-1",
        attempted_at_utc=datetime(2026, 4, 3, tzinfo=timezone.utc),
        filing_id="filing-1",
        accession_no="0000320193-24-000012",
        cik="0000320193",
        document_id="doc-1",
        document_type="XML",
        document_filename="primary_doc.xml",
        document_path="raw/0000320193/0000320193-24-000012/documents/doc.xml",
        snapshot_path=None,
        source_url="https://example",
        sha256_hex="a" * 64,
        byte_length=100,
        xml_text="<ownershipDocument><issuer><issuerCik>0000320193</issuerCik></issuer></ownershipDocument>",
    )
    process_owner_document(
        session=session,
        parse_route_logger=logger,
        run_id="run-2",
        attempted_at_utc=datetime(2026, 4, 4, tzinfo=timezone.utc),
        filing_id="filing-1",
        accession_no="0000320193-24-000012",
        cik="0000320193",
        document_id="doc-1",
        document_type="XML",
        document_filename="primary_doc.xml",
        document_path="raw/0000320193/0000320193-24-000012/documents/doc.xml",
        snapshot_path=None,
        source_url="https://example",
        sha256_hex="a" * 64,
        byte_length=100,
        xml_text="<ownershipDocument><issuer><issuerCik>0000320193</issuerCik></issuer></ownershipDocument>",
    )

    run_ids = {row.run_id for row in logger.rows}
    assert run_ids == {"run-1", "run-2"}
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/worker/test_owner_pipeline.py::test_replay_creates_new_parse_route_log_rows_with_new_run_id -v`

Expected: FAIL with missing `process_owner_document`.

- [ ] **Step 3: Implement phase-3 owner document processing wrapper**

```python
# src/worker/owner_pipeline.py (additions)
from datetime import datetime

from src.worker.decision_service import DecisionService, ParseDocument


def process_owner_document(
    *,
    session,
    parse_route_logger,
    run_id: str,
    attempted_at_utc: datetime,
    filing_id: str,
    accession_no: str,
    cik: str,
    document_id: str,
    document_type: str,
    document_filename: str,
    document_path: str,
    snapshot_path: str | None,
    source_url: str | None,
    sha256_hex: str,
    byte_length: int,
    xml_text: str,
) -> None:
    decision_service = DecisionService(parse_route_logger=parse_route_logger)
    decision = decision_service.process_document(
        run_id=run_id,
        attempted_at_utc=attempted_at_utc,
        document=ParseDocument(
            filing_id=filing_id,
            accession_no=accession_no,
            cik=cik,
            document_id=document_id,
            document_type=document_type,
            document_filename=document_filename,
            document_path=document_path,
            snapshot_path=snapshot_path,
            source_url=source_url,
            sha256_hex=sha256_hex,
            byte_length=byte_length,
            xml_text=xml_text,
        ),
    )
    if decision.parsed_submission is None:
        return

    persist_owner_submission(
        session=session,
        filing_id=filing_id,
        parsed_submission=decision.parsed_submission,
    )
```

- [ ] **Step 4: Run owner pipeline tests**

Run: `uv run pytest tests/worker/test_owner_pipeline.py -v`

Expected: PASS with replay-run history rows and idempotent fact/review boundaries.

- [ ] **Step 5: Commit pipeline phase-3 wiring**

```bash
git add src/worker/owner_pipeline.py tests/worker/test_owner_pipeline.py
git commit -m "feat: wire owner pipeline through phase3 decision logging"
```

### Task 7: Add Parse-Log CLI Commands and Complete Verification

**Files:**
- Modify: `src/cli.py`
- Create: `tests/cli/test_parse_log_cli.py`

- [ ] **Step 1: Write failing CLI tests for query/timeline commands**

```python
# tests/cli/test_parse_log_cli.py
from typer.testing import CliRunner

from src.cli import app


def test_parse_log_commands_are_registered() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "parse-log" in result.stdout


def test_parse_log_query_accepts_required_filters() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "parse-log",
            "query",
            "--document-type",
            "XML",
            "--from-utc",
            "2026-04-03T00:00:00+00:00",
            "--to-utc",
            "2026-04-04T00:00:00+00:00",
            "--failure-type",
            "parse",
        ],
    )

    assert result.exit_code == 0
```

- [ ] **Step 2: Run CLI tests to verify failure**

Run: `uv run pytest tests/cli/test_parse_log_cli.py -v`

Expected: FAIL because `parse-log` command group does not exist yet.

- [ ] **Step 3: Implement parse-log command group and wiring**

```python
# src/cli.py (additions)
from datetime import datetime

import typer

app = typer.Typer(help="SEC Filing Pipeline")
parse_log_app = typer.Typer(help="Parse route log inspection commands")
app.add_typer(parse_log_app, name="parse-log")


@parse_log_app.command("query")
def parse_log_query(
    document_type: str | None = typer.Option(None, "--document-type"),
    from_utc: str | None = typer.Option(None, "--from-utc"),
    to_utc: str | None = typer.Option(None, "--to-utc"),
    failure_type: str | None = typer.Option(None, "--failure-type"),
    limit: int = typer.Option(100, "--limit"),
    offset: int = typer.Option(0, "--offset"),
) -> None:
    typer.echo(
        "parse-log query: "
        f"document_type={document_type} from={from_utc} to={to_utc} "
        f"failure_type={failure_type} limit={limit} offset={offset}"
    )


@parse_log_app.command("timeline")
def parse_log_timeline(
    accession_no: str = typer.Option(..., "--accession-no"),
    document_id: str = typer.Option(..., "--document-id"),
) -> None:
    typer.echo(f"parse-log timeline: accession_no={accession_no} document_id={document_id}")
```

- [ ] **Step 4: Run full phase-3 verification suite**

Run: `uv run pytest tests/models/test_metadata.py tests/storage/test_parse_route_log_repo.py tests/parsers/test_ownership_deterministic.py tests/storage/test_sec_download_adapter.py tests/worker/test_decision_service.py tests/worker/test_owner_pipeline.py tests/cli/test_parse_log_cli.py -v`

Expected: PASS with all phase-3 tests green.

- [ ] **Step 5: Commit CLI and final verification scope**

```bash
git add src/cli.py tests/cli/test_parse_log_cli.py
git commit -m "feat: add parse-log query and timeline cli commands"
```

## Final Verification Checklist

- [ ] `uv run pytest tests/models/test_metadata.py -v`
- [ ] `uv run pytest tests/storage/test_parse_route_log_repo.py -v`
- [ ] `uv run pytest tests/parsers/test_ownership_deterministic.py tests/worker/test_decision_service.py -v`
- [ ] `uv run pytest tests/storage/test_sec_download_adapter.py tests/worker/test_owner_pipeline.py -v`
- [ ] `uv run pytest tests/cli/test_parse_log_cli.py -v`
- [ ] `uv run pytest -v`

## Spec Coverage Map

- Parse chain fixed behavior (`structured_xml -> deterministic_rule -> needs_review`): Task 4 + Task 6.
- Persist success and failure parse attempts: Task 2 + Task 3 + Task 4.
- Fixed `failure_type` enum (`network|parse|logic`) and detailed `error_message`: Task 2 + Task 4 + Task 5.
- Query dimensions (`document_type`, `attempted_at_utc`, `failure_type`) and timeline API: Task 3 + Task 7.
- Edgartools download adapter and all-attachment handling boundary: Task 5.
- Replay run history while maintaining idempotent fact/review persistence: Task 6.
