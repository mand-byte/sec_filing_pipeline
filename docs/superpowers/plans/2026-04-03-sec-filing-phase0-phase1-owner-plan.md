# SEC Filing Phase 0-2 Owner Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 0 and Phase 1 platform foundation plus the minimum `owner` route slice for `3/4/5`, with append-only PostgreSQL persistence, replayable raw artifacts, XML-first parsing, and minimal decision/review plumbing.

**Architecture:** Keep PostgreSQL as the system of record for ingestion state, filing metadata, extracted facts, review items, and parser registries. Persist raw SEC artifacts to the local raw archive using deterministic accession- and content-hash-based paths, then parse `3/4/5` XML into structured facts with attached evidence and decision metadata.

**Tech Stack:** Python 3.12+, Typer, SQLAlchemy 2.x, Pydantic v2, psycopg, clickhouse-connect, lxml, pytest

---

## File Structure

The first implementation slice should use the repository structure already present in the last committed skeleton and expand it only where the first slice needs real code.

- `pyproject.toml`
  Keeps runtime and test dependencies.
- `main.py`
  Thin entrypoint that delegates to the Typer CLI.
- `src/cli.py`
  CLI commands for `init-db`, `owner-sync`, and `replay-accession`.
- `src/core/config.py`
  Typed settings for PostgreSQL, ClickHouse, SEC user-agent, raw store path, and rate limiting.
- `src/domain/enums.py`
  Route, parser, decision, review, and canonical-form enums.
- `src/rules/forms.py`
  Form canonicalization, route dispatch, amendment grouping, and event-time helpers.
- `src/models/base.py`
  Shared SQLAlchemy declarative base.
- `src/models/state.py`
  `ingestion_state` table.
- `src/models/filing.py`
  `filing_index`, `filing_document`, and `extracted_fact` tables.
- `src/models/review.py`
  `review_queue` table.
- `src/models/registry.py`
  `parser_registry` and `model_registry` tables.
- `src/storage/db.py`
  SQLAlchemy engine/session bootstrap.
- `src/storage/raw_store.py`
  Deterministic raw artifact persistence and hashing.
- `src/storage/sec_client.py`
  SEC HTTP client with rate limiting and explicit user-agent headers.
- `src/storage/owner_discovery.py`
  Owner-route submission discovery and cursor filtering.
- `src/parsers/ownership_xml.py`
  XML-first parser for `3/4/5` and evidence locator generation.
- `src/worker/owner_pipeline.py`
  End-to-end orchestration for owner discovery, raw persistence, parsing, fact persistence, and review-item generation.
- `tests/core/test_config.py`
  Settings and CLI smoke tests.
- `tests/domain/test_forms.py`
  Canonicalization, route dispatch, amendment grouping, and event-time tests.
- `tests/models/test_metadata.py`
  Table registration and primary-key contract tests.
- `tests/storage/test_raw_store.py`
  Raw artifact path and hash tests.
- `tests/storage/test_owner_discovery.py`
  Owner discovery cursor and SEC payload parsing tests.
- `tests/parsers/test_ownership_xml.py`
  XML parser and locator tests.
- `tests/worker/test_owner_pipeline.py`
  Persistence and review-queue generation tests.

### Task 1: Restore Project Skeleton, Settings, and Test Infrastructure

**Files:**
- Modify: `pyproject.toml`
- Modify: `main.py`
- Create: `src/__init__.py`
- Create: `src/core/__init__.py`
- Create: `src/core/config.py`
- Create: `src/cli.py`
- Create: `tests/core/test_config.py`

- [ ] **Step 1: Write the failing settings and CLI smoke tests**

```python
# tests/core/test_config.py
from pathlib import Path

from src.core.config import Settings


def test_settings_use_explicit_raw_store_dir(tmp_path):
    settings = Settings(
        _env_file=None,
        POSTGRES_DSN="postgresql+psycopg://user:pass@localhost:5432/sec_db",
        RAW_STORE_DIR=tmp_path / "raw",
        SEC_API_USER_AGENT="Example Research research@example.com",
    )

    assert settings.RAW_STORE_DIR == tmp_path / "raw"
    assert settings.SEC_API_USER_AGENT == "Example Research research@example.com"


def test_cli_app_has_expected_commands():
    from src.cli import app

    command_names = {command.name for command in app.registered_commands}
    assert {"init-db", "owner-sync", "replay-accession"} <= command_names
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/core/test_config.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'src.core.config'`.

- [ ] **Step 3: Write the minimal project scaffolding and settings implementation**

```toml
# pyproject.toml
[project]
name = "sec-filing-pipeline"
version = "0.1.0"
description = "SEC Filing Backend - Phase 1"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "clickhouse-connect",
    "lxml>=5.2.0",
    "psycopg[binary]",
    "pydantic",
    "pydantic-settings",
    "sqlalchemy",
    "typer>=0.15.0",
]

[dependency-groups]
dev = [
    "pytest>=8.2.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src"]
```

```python
# src/__init__.py
__all__ = ["cli"]
```

```python
# src/core/__init__.py
from src.core.config import Settings, settings

__all__ = ["Settings", "settings"]
```

```python
# src/core/config.py
from pathlib import Path

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    POSTGRES_DSN: PostgresDsn | str = Field(
        default="postgresql+psycopg://user:pass@localhost:5432/sec_db"
    )
    CLICKHOUSE_HOST: str = "localhost"
    CLICKHOUSE_PORT: int = 8123
    CLICKHOUSE_USER: str = "default"
    CLICKHOUSE_PASSWORD: str = ""
    CLICKHOUSE_DB: str = "data_quant"
    RAW_STORE_DIR: Path = Path("raw_data")
    SEC_API_USER_AGENT: str = "Example Research research@example.com"
    SEC_RATE_LIMIT_PER_SECOND: float = 5.0


settings = Settings()
```

```python
# src/cli.py
import typer


app = typer.Typer(help="SEC filing pipeline")


@app.command("init-db")
def init_db() -> None:
    """Initialize database tables."""
    raise NotImplementedError("implemented in Task 3")


@app.command("owner-sync")
def owner_sync() -> None:
    """Run the owner-route sync pipeline."""
    raise NotImplementedError("implemented in Task 6")


@app.command("replay-accession")
def replay_accession(accession_no: str) -> None:
    """Replay one archived accession."""
    raise NotImplementedError(accession_no)
```

```python
# main.py
from src.cli import app


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/core/test_config.py -v`

Expected: PASS for both tests.

- [ ] **Step 5: Commit the scaffold**

```bash
git add pyproject.toml main.py src/__init__.py src/core/__init__.py src/core/config.py src/cli.py tests/core/test_config.py
git commit -m "feat: restore pipeline scaffold and typed settings"
```

### Task 2: Add Canonical Form, Route, Amendment, and Event-Time Rules

**Files:**
- Create: `src/domain/__init__.py`
- Create: `src/domain/enums.py`
- Create: `src/rules/__init__.py`
- Create: `src/rules/forms.py`
- Test: `tests/domain/test_forms.py`

- [ ] **Step 1: Write the failing domain-rule tests**

```python
# tests/domain/test_forms.py
from datetime import datetime, timezone

from src.domain.enums import RouteType
from src.rules.forms import canonicalize_form_type, choose_event_time, route_for_form


def test_canonicalize_form_type_marks_amendments():
    canonical = canonicalize_form_type("4/A")

    assert canonical.form_type_raw == "4/A"
    assert canonical.form_type_base == "4"
    assert canonical.is_amendment is True


def test_route_for_form_uses_owner_route_for_form4():
    canonical = canonicalize_form_type("4")
    assert route_for_form(canonical) is RouteType.OWNER


def test_choose_event_time_prefers_acceptance_datetime():
    acceptance = datetime(2026, 4, 3, 12, 30, tzinfo=timezone.utc)
    filing_date = datetime(2026, 4, 2, 0, 0, tzinfo=timezone.utc)

    assert choose_event_time(acceptance, filing_date) == acceptance
```

- [ ] **Step 2: Run the domain tests to verify they fail**

Run: `uv run pytest tests/domain/test_forms.py -v`

Expected: FAIL with `ModuleNotFoundError` for `src.domain.enums` or `src.rules.forms`.

- [ ] **Step 3: Implement the canonicalization and rule helpers**

```python
# src/domain/__init__.py
from src.domain.enums import CanonicalForm, DecisionState, ParserMethod, ReviewReason, RouteType

__all__ = [
    "CanonicalForm",
    "DecisionState",
    "ParserMethod",
    "ReviewReason",
    "RouteType",
]
```

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


class DecisionState(str, Enum):
    ACCEPTED = "accepted"
    ACCEPTED_WITH_WARNING = "accepted_with_warning"
    NEEDS_REVIEW = "needs_review"
    DROPPED = "dropped"


class ReviewReason(str, Enum):
    MANDATORY_FIELD_MISSING = "mandatory_field_missing"
    SOURCE_CONFLICT = "source_conflict"
    AMENDMENT_CONFLICT = "amendment_conflict"


@dataclass(frozen=True)
class CanonicalForm:
    form_type_raw: str
    form_type_base: str
    is_amendment: bool
```

```python
# src/rules/__init__.py
from src.rules.forms import canonicalize_form_type, choose_event_time, route_for_form

__all__ = ["canonicalize_form_type", "choose_event_time", "route_for_form"]
```

```python
# src/rules/forms.py
from datetime import datetime

from src.domain.enums import CanonicalForm, RouteType


OWNER_FORMS = {"3", "4", "5", "13D", "13G", "144"}
HOLDINGS_FORMS = {"13F-HR"}


def canonicalize_form_type(form_type_raw: str) -> CanonicalForm:
    value = form_type_raw.strip().upper()
    is_amendment = value.endswith("/A")
    base = value[:-2] if is_amendment else value
    return CanonicalForm(
        form_type_raw=value,
        form_type_base=base,
        is_amendment=is_amendment,
    )


def route_for_form(canonical_form: CanonicalForm) -> RouteType:
    if canonical_form.form_type_base in OWNER_FORMS:
        return RouteType.OWNER
    if canonical_form.form_type_base in HOLDINGS_FORMS:
        return RouteType.HOLDINGS
    return RouteType.ISSUER


def choose_event_time(
    acceptance_datetime_utc: datetime | None,
    filing_date: datetime | None,
) -> datetime | None:
    if acceptance_datetime_utc is not None:
        return acceptance_datetime_utc
    return filing_date
```

- [ ] **Step 4: Run the tests to verify the rules pass**

Run: `uv run pytest tests/domain/test_forms.py -v`

Expected: PASS for amendment, route, and event-time selection.

- [ ] **Step 5: Commit the domain rules**

```bash
git add src/domain/__init__.py src/domain/enums.py src/rules/__init__.py src/rules/forms.py tests/domain/test_forms.py
git commit -m "feat: add canonical form and route rules"
```

### Task 3: Create the Core PostgreSQL Tables and Database Bootstrap

**Files:**
- Create: `src/models/__init__.py`
- Create: `src/models/base.py`
- Create: `src/models/state.py`
- Create: `src/models/filing.py`
- Create: `src/models/review.py`
- Create: `src/models/registry.py`
- Create: `src/storage/__init__.py`
- Create: `src/storage/db.py`
- Modify: `src/cli.py`
- Test: `tests/models/test_metadata.py`

- [ ] **Step 1: Write the failing metadata-contract tests**

```python
# tests/models/test_metadata.py
from src.models import Base  # noqa: F401
from src.models import filing, registry, review, state  # noqa: F401


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


def test_ingestion_state_primary_key_is_cik_plus_route_type():
    table = Base.metadata.tables["ingestion_state"]
    primary_key_names = {column.name for column in table.primary_key.columns}

    assert primary_key_names == {"cik", "route_type"}
```

- [ ] **Step 2: Run the metadata tests to verify they fail**

Run: `uv run pytest tests/models/test_metadata.py -v`

Expected: FAIL because the model modules do not exist yet.

- [ ] **Step 3: Implement the base models, registries, and database bootstrap**

```python
# src/models/__init__.py
from src.models.base import Base

__all__ = ["Base"]
```

```python
# src/models/base.py
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

```python
# src/models/state.py
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class IngestionState(Base):
    __tablename__ = "ingestion_state"

    cik: Mapped[str] = mapped_column(String(10), primary_key=True)
    route_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    last_acceptance_datetime_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_accession_no: Mapped[str | None] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

```python
# src/models/filing.py
from datetime import datetime, date

from sqlalchemy import Boolean, Date, DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class FilingIndex(Base):
    __tablename__ = "filing_index"

    filing_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    cik: Mapped[str] = mapped_column(String(10), index=True)
    accession_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    form_type_raw: Mapped[str] = mapped_column(String(32))
    form_type_base: Mapped[str] = mapped_column(String(32))
    is_amendment: Mapped[bool] = mapped_column(Boolean, nullable=False)
    route_type: Mapped[str] = mapped_column(String(32), index=True)
    acceptance_datetime_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    filing_date: Mapped[date | None] = mapped_column(Date)
    primary_document: Mapped[str | None] = mapped_column(String(255))
    amendment_group_key: Mapped[str] = mapped_column(String(128), index=True)
    amendment_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FilingDocument(Base):
    __tablename__ = "filing_document"

    document_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    filing_id: Mapped[str] = mapped_column(String(128), index=True)
    accession_no: Mapped[str] = mapped_column(String(32), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(128))
    sha256_hex: Mapped[str] = mapped_column(String(64), index=True)
    byte_length: Mapped[int] = mapped_column(Integer)
    raw_path: Mapped[str] = mapped_column(Text)
    decoded_text_path: Mapped[str | None] = mapped_column(Text)
    parser_snapshot_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExtractedFact(Base):
    __tablename__ = "extracted_fact"

    fact_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    filing_id: Mapped[str] = mapped_column(String(128), index=True)
    accession_no: Mapped[str] = mapped_column(String(32), index=True)
    fact_name: Mapped[str] = mapped_column(String(128), index=True)
    fact_value: Mapped[str] = mapped_column(Text)
    parser_method: Mapped[str] = mapped_column(String(64))
    confidence_score: Mapped[float] = mapped_column(nullable=False)
    confidence_bucket: Mapped[str] = mapped_column(String(16))
    decision_state: Mapped[str] = mapped_column(String(32))
    snippet_text: Mapped[str] = mapped_column(Text)
    snippet_locator: Mapped[str] = mapped_column(Text)
    document_filename: Mapped[str] = mapped_column(String(255))
    validation_results: Mapped[dict] = mapped_column(JSON)
    attempted_methods: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

```python
# src/models/review.py
from datetime import datetime

from sqlalchemy import DateTime, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class ReviewQueueItem(Base):
    __tablename__ = "review_queue"

    review_item_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    accession_no: Mapped[str] = mapped_column(String(32), index=True)
    fact_id: Mapped[str | None] = mapped_column(String(160), index=True)
    review_reason: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(32), default="open")
    note: Mapped[str | None] = mapped_column(Text)
```

```python
# src/models/registry.py
from datetime import datetime

from sqlalchemy import DateTime, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class ParserRegistry(Base):
    __tablename__ = "parser_registry"

    parser_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    route_type: Mapped[str] = mapped_column(String(32))
    form_family: Mapped[str] = mapped_column(String(32))
    metadata_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelRegistry(Base):
    __tablename__ = "model_registry"

    model_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    model_family: Mapped[str] = mapped_column(String(32))
    metadata_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

```python
# src/storage/__init__.py
from src.storage.db import SessionLocal, engine

__all__ = ["SessionLocal", "engine"]
```

```python
# src/storage/db.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.config import settings


engine = create_engine(str(settings.POSTGRES_DSN), future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
```

```python
# src/cli.py
import typer

from src.models import Base
from src.models import filing, registry, review, state  # noqa: F401
from src.storage.db import engine


app = typer.Typer(help="SEC filing pipeline")


@app.command("init-db")
def init_db() -> None:
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)


@app.command("owner-sync")
def owner_sync() -> None:
    """Run the owner-route sync pipeline."""
    raise NotImplementedError("implemented in Task 6")


@app.command("replay-accession")
def replay_accession(accession_no: str) -> None:
    """Replay one archived accession."""
    raise NotImplementedError(accession_no)
```

- [ ] **Step 4: Run the metadata tests to verify they pass**

Run: `uv run pytest tests/models/test_metadata.py -v`

Expected: PASS with the seven required tables present.

- [ ] **Step 5: Commit the storage contracts**

```bash
git add src/models/__init__.py src/models/base.py src/models/state.py src/models/filing.py src/models/review.py src/models/registry.py src/storage/__init__.py src/storage/db.py src/cli.py tests/models/test_metadata.py
git commit -m "feat: add postgres tables for ingestion and audit state"
```

### Task 4: Implement Deterministic Raw Artifact Persistence

**Files:**
- Create: `src/storage/raw_store.py`
- Test: `tests/storage/test_raw_store.py`

- [ ] **Step 1: Write the failing raw-store tests**

```python
# tests/storage/test_raw_store.py
from src.storage.raw_store import RawArtifact, RawStore


def test_raw_store_persists_document_to_deterministic_path(tmp_path):
    store = RawStore(root=tmp_path)
    artifact = RawArtifact(
        cik="0000320193",
        accession_no="0000320193-24-000010",
        filename="xslF345X03/primary_doc.xml",
        content_type="text/xml",
        content=b"<ownershipDocument/>",
    )

    stored = store.persist_document(artifact)

    assert stored.sha256_hex
    assert stored.byte_length == len(b"<ownershipDocument/>")
    assert stored.path.relative_to(tmp_path).as_posix().startswith(
        "0000320193/0000320193-24-000010/documents/"
    )


def test_raw_store_persists_parser_snapshot_beside_document(tmp_path):
    store = RawStore(root=tmp_path)
    path = store.persist_text_snapshot(
        cik="0000320193",
        accession_no="0000320193-24-000010",
        filename="primary_doc.xml",
        suffix="parser-input.json",
        content='{"form":"4"}',
    )

    assert path.read_text() == '{"form":"4"}'
    assert path.relative_to(tmp_path).as_posix().endswith("parser-input.json")
```

- [ ] **Step 2: Run the raw-store tests to verify they fail**

Run: `uv run pytest tests/storage/test_raw_store.py -v`

Expected: FAIL because `src.storage.raw_store` does not exist.

- [ ] **Step 3: Implement the raw store and hash-based paths**

```python
# src/storage/raw_store.py
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


@dataclass(frozen=True)
class RawArtifact:
    cik: str
    accession_no: str
    filename: str
    content_type: str | None
    content: bytes


@dataclass(frozen=True)
class StoredArtifact:
    path: Path
    sha256_hex: str
    byte_length: int


class RawStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def persist_document(self, artifact: RawArtifact) -> StoredArtifact:
        sha256_hex = sha256(artifact.content).hexdigest()
        suffix = Path(artifact.filename).suffix or ".bin"
        target = (
            self.root
            / artifact.cik
            / artifact.accession_no
            / "documents"
            / f"{sha256_hex}{suffix}"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(artifact.content)
        return StoredArtifact(path=target, sha256_hex=sha256_hex, byte_length=len(artifact.content))

    def persist_text_snapshot(
        self,
        *,
        cik: str,
        accession_no: str,
        filename: str,
        suffix: str,
        content: str,
    ) -> Path:
        stem = Path(filename).stem
        target = self.root / cik / accession_no / "snapshots" / f"{stem}.{suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return target
```

- [ ] **Step 4: Run the raw-store tests to verify they pass**

Run: `uv run pytest tests/storage/test_raw_store.py -v`

Expected: PASS with deterministic document and snapshot paths.

- [ ] **Step 5: Commit the raw-store implementation**

```bash
git add src/storage/raw_store.py tests/storage/test_raw_store.py
git commit -m "feat: add deterministic raw artifact storage"
```

### Task 5: Implement the SEC Client and Owner Discovery Cursor Logic

**Files:**
- Create: `src/storage/sec_client.py`
- Create: `src/storage/owner_discovery.py`
- Test: `tests/storage/test_owner_discovery.py`

- [ ] **Step 1: Write the failing discovery tests**

```python
# tests/storage/test_owner_discovery.py
from datetime import datetime, timezone

from src.storage.owner_discovery import DiscoveryCursor, discover_owner_filings


def test_discover_owner_filings_filters_out_seen_accessions():
    payload = {
        "filings": {
            "recent": {
                "form": ["4", "4/A", "8-K"],
                "accessionNumber": [
                    "0000320193-24-000012",
                    "0000320193-24-000011",
                    "0000320193-24-000010",
                ],
                "acceptanceDateTime": [
                    "2024-04-03T12:30:00Z",
                    "2024-04-02T12:30:00Z",
                    "2024-04-01T12:30:00Z",
                ],
                "primaryDocument": ["doc4.xml", "doc4a.xml", "doc8k.htm"],
            }
        }
    }
    cursor = DiscoveryCursor(
        last_acceptance_datetime_utc=datetime(2024, 4, 2, 12, 30, tzinfo=timezone.utc),
        last_accession_no="0000320193-24-000011",
    )

    filings = discover_owner_filings(cik="0000320193", payload=payload, cursor=cursor)

    assert [item.accession_no for item in filings] == ["0000320193-24-000012"]


def test_discover_owner_filings_ignores_non_owner_forms():
    payload = {
        "filings": {
            "recent": {
                "form": ["8-K"],
                "accessionNumber": ["0000320193-24-000010"],
                "acceptanceDateTime": ["2024-04-01T12:30:00Z"],
                "primaryDocument": ["doc8k.htm"],
            }
        }
    }

    assert discover_owner_filings(cik="0000320193", payload=payload, cursor=None) == []
```

- [ ] **Step 2: Run the discovery tests to verify they fail**

Run: `uv run pytest tests/storage/test_owner_discovery.py -v`

Expected: FAIL because the discovery module does not exist.

- [ ] **Step 3: Implement the SEC client and owner discovery helper**

```python
# src/storage/sec_client.py
import json
import time
from urllib.request import Request, urlopen

from src.core.config import settings


class SecClient:
    def __init__(self, user_agent: str | None = None, rate_limit_per_second: float | None = None):
        self.user_agent = user_agent or settings.SEC_API_USER_AGENT
        self.rate_limit_per_second = rate_limit_per_second or settings.SEC_RATE_LIMIT_PER_SECOND
        self._last_request_monotonic = 0.0

    def get_json(self, url: str) -> dict:
        delay = 1 / self.rate_limit_per_second
        elapsed = time.monotonic() - self._last_request_monotonic
        if elapsed < delay:
            time.sleep(delay - elapsed)

        request = Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/json"})
        with urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))

        self._last_request_monotonic = time.monotonic()
        return payload
```

```python
# src/storage/owner_discovery.py
from dataclasses import dataclass
from datetime import datetime

from src.rules.forms import canonicalize_form_type, route_for_form
from src.domain.enums import RouteType


@dataclass(frozen=True)
class DiscoveryCursor:
    last_acceptance_datetime_utc: datetime | None
    last_accession_no: str | None


@dataclass(frozen=True)
class DiscoveredFiling:
    cik: str
    accession_no: str
    form_type_raw: str
    acceptance_datetime_utc: datetime
    primary_document: str


def discover_owner_filings(cik: str, payload: dict, cursor: DiscoveryCursor | None) -> list[DiscoveredFiling]:
    recent = payload.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    acceptance_times = recent.get("acceptanceDateTime", [])
    primary_documents = recent.get("primaryDocument", [])

    discovered: list[DiscoveredFiling] = []
    for form, accession_no, acceptance_raw, primary_document in zip(
        forms,
        accessions,
        acceptance_times,
        primary_documents,
        strict=True,
    ):
        canonical = canonicalize_form_type(form)
        if route_for_form(canonical) is not RouteType.OWNER:
            continue

        acceptance_datetime_utc = datetime.fromisoformat(acceptance_raw.replace("Z", "+00:00"))
        if cursor is not None and cursor.last_acceptance_datetime_utc is not None:
            if acceptance_datetime_utc < cursor.last_acceptance_datetime_utc:
                continue
            if (
                acceptance_datetime_utc == cursor.last_acceptance_datetime_utc
                and accession_no <= (cursor.last_accession_no or "")
            ):
                continue

        discovered.append(
            DiscoveredFiling(
                cik=cik,
                accession_no=accession_no,
                form_type_raw=form,
                acceptance_datetime_utc=acceptance_datetime_utc,
                primary_document=primary_document,
            )
        )

    return discovered
```

- [ ] **Step 4: Run the discovery tests to verify they pass**

Run: `uv run pytest tests/storage/test_owner_discovery.py -v`

Expected: PASS with the older accession filtered out and the non-owner form ignored.

- [ ] **Step 5: Commit the client and discovery layer**

```bash
git add src/storage/sec_client.py src/storage/owner_discovery.py tests/storage/test_owner_discovery.py
git commit -m "feat: add sec client and owner discovery cursor logic"
```

### Task 6: Parse `3/4/5` XML and Build Fact and Review Rows

**Files:**
- Create: `src/parsers/__init__.py`
- Create: `src/parsers/ownership_xml.py`
- Create: `src/worker/__init__.py`
- Create: `src/worker/owner_pipeline.py`
- Test: `tests/parsers/test_ownership_xml.py`
- Test: `tests/worker/test_owner_pipeline.py`

- [ ] **Step 1: Write the failing parser and pipeline tests**

```python
# tests/parsers/test_ownership_xml.py
from src.parsers.ownership_xml import parse_ownership_xml


FORM4_XML = """
<ownershipDocument>
  <issuer>
    <issuerCik>0000320193</issuerCik>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0001214156</rptOwnerCik>
    </reportingOwnerId>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionAmounts>
        <transactionShares>
          <value>1234</value>
        </transactionShares>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""


def test_parse_ownership_xml_emits_xpath_backed_facts():
    parsed = parse_ownership_xml(
        accession_no="0000320193-24-000012",
        document_filename="primary_doc.xml",
        xml_text=FORM4_XML,
    )

    fact_names = {fact.fact_name for fact in parsed.facts}
    assert {"issuer_cik", "reporting_owner_cik", "transaction_shares"} <= fact_names

    shares_fact = next(fact for fact in parsed.facts if fact.fact_name == "transaction_shares")
    assert shares_fact.snippet_locator.endswith("/nonDerivativeTransaction/transactionAmounts/transactionShares/value")
    assert shares_fact.parser_method == "structured_xml"
```

```python
# tests/worker/test_owner_pipeline.py
from src.parsers.ownership_xml import ParsedOwnershipFact
from src.worker.owner_pipeline import build_fact_row, build_review_item


def test_build_fact_row_marks_complete_xml_fact_as_accepted():
    parsed_fact = ParsedOwnershipFact(
        fact_name="transaction_shares",
        fact_value="1234",
        parser_method="structured_xml",
        snippet_text="1234",
        snippet_locator="/ownershipDocument/nonDerivativeTable/nonDerivativeTransaction/transactionAmounts/transactionShares/value",
        document_filename="primary_doc.xml",
        validation_results={"is_numeric": True},
    )

    fact_row = build_fact_row(
        filing_id="filing-1",
        accession_no="0000320193-24-000012",
        parsed_fact=parsed_fact,
    )

    assert fact_row.decision_state == "accepted"
    assert fact_row.confidence_bucket == "high"


def test_build_review_item_for_missing_mandatory_value():
    parsed_fact = ParsedOwnershipFact(
        fact_name="reporting_owner_cik",
        fact_value="",
        parser_method="structured_xml",
        snippet_text="",
        snippet_locator="/ownershipDocument/reportingOwner/reportingOwnerId/rptOwnerCik",
        document_filename="primary_doc.xml",
        validation_results={"mandatory_present": False},
    )

    review_item = build_review_item(
        accession_no="0000320193-24-000012",
        parsed_fact=parsed_fact,
    )

    assert review_item.review_reason == "mandatory_field_missing"
    assert review_item.status == "open"
```

- [ ] **Step 2: Run the parser and pipeline tests to verify they fail**

Run: `uv run pytest tests/parsers/test_ownership_xml.py tests/worker/test_owner_pipeline.py -v`

Expected: FAIL because the parser and worker modules do not exist.

- [ ] **Step 3: Implement the XML parser and row-building helpers**

```python
# src/parsers/__init__.py
from src.parsers.ownership_xml import ParsedOwnershipFact, ParsedOwnershipSubmission, parse_ownership_xml

__all__ = ["ParsedOwnershipFact", "ParsedOwnershipSubmission", "parse_ownership_xml"]
```

```python
# src/parsers/ownership_xml.py
from dataclasses import dataclass

from lxml import etree

from src.domain.enums import ParserMethod


@dataclass(frozen=True)
class ParsedOwnershipFact:
    fact_name: str
    fact_value: str
    parser_method: str
    snippet_text: str
    snippet_locator: str
    document_filename: str
    validation_results: dict


@dataclass(frozen=True)
class ParsedOwnershipSubmission:
    accession_no: str
    document_filename: str
    facts: list[ParsedOwnershipFact]


def _first_text(root: etree._Element, xpath: str) -> str:
    values = root.xpath(xpath)
    if not values:
        return ""
    node = values[0]
    if isinstance(node, etree._Element):
        return (node.text or "").strip()
    return str(node).strip()


def parse_ownership_xml(accession_no: str, document_filename: str, xml_text: str) -> ParsedOwnershipSubmission:
    root = etree.fromstring(xml_text.encode("utf-8"))
    fields = {
        "issuer_cik": "/ownershipDocument/issuer/issuerCik",
        "reporting_owner_cik": "/ownershipDocument/reportingOwner/reportingOwnerId/rptOwnerCik",
        "transaction_shares": "/ownershipDocument/nonDerivativeTable/nonDerivativeTransaction/transactionAmounts/transactionShares/value",
    }

    facts: list[ParsedOwnershipFact] = []
    for fact_name, xpath in fields.items():
        value = _first_text(root, xpath)
        facts.append(
            ParsedOwnershipFact(
                fact_name=fact_name,
                fact_value=value,
                parser_method=ParserMethod.STRUCTURED_XML.value,
                snippet_text=value,
                snippet_locator=xpath,
                document_filename=document_filename,
                validation_results={
                    "mandatory_present": bool(value),
                    "is_numeric": value.isdigit() if fact_name == "transaction_shares" else True,
                },
            )
        )

    return ParsedOwnershipSubmission(
        accession_no=accession_no,
        document_filename=document_filename,
        facts=facts,
    )
```

```python
# src/worker/__init__.py
from src.worker.owner_pipeline import build_fact_row, build_review_item

__all__ = ["build_fact_row", "build_review_item"]
```

```python
# src/worker/owner_pipeline.py
from hashlib import sha1

from src.domain.enums import DecisionState, ReviewReason
from src.models.filing import ExtractedFact
from src.models.review import ReviewQueueItem
from src.parsers.ownership_xml import ParsedOwnershipFact


def _fact_id(accession_no: str, fact_name: str, snippet_locator: str) -> str:
    return sha1(f"{accession_no}:{fact_name}:{snippet_locator}".encode("utf-8")).hexdigest()


def build_fact_row(filing_id: str, accession_no: str, parsed_fact: ParsedOwnershipFact) -> ExtractedFact:
    is_complete = bool(parsed_fact.validation_results.get("mandatory_present", True))
    is_numeric_ok = parsed_fact.validation_results.get("is_numeric", True)
    accepted = is_complete and is_numeric_ok
    return ExtractedFact(
        fact_id=_fact_id(accession_no, parsed_fact.fact_name, parsed_fact.snippet_locator),
        filing_id=filing_id,
        accession_no=accession_no,
        fact_name=parsed_fact.fact_name,
        fact_value=parsed_fact.fact_value,
        parser_method=parsed_fact.parser_method,
        confidence_score=0.99 if accepted else 0.30,
        confidence_bucket="high" if accepted else "low",
        decision_state=DecisionState.ACCEPTED.value if accepted else DecisionState.NEEDS_REVIEW.value,
        snippet_text=parsed_fact.snippet_text,
        snippet_locator=parsed_fact.snippet_locator,
        document_filename=parsed_fact.document_filename,
        validation_results=parsed_fact.validation_results,
        attempted_methods=[parsed_fact.parser_method],
    )


def build_review_item(accession_no: str, parsed_fact: ParsedOwnershipFact) -> ReviewQueueItem:
    return ReviewQueueItem(
        review_item_id=_fact_id(accession_no, parsed_fact.fact_name, parsed_fact.snippet_locator),
        accession_no=accession_no,
        fact_id=None,
        review_reason=ReviewReason.MANDATORY_FIELD_MISSING.value,
        payload={
            "fact_name": parsed_fact.fact_name,
            "snippet_locator": parsed_fact.snippet_locator,
            "validation_results": parsed_fact.validation_results,
        },
        status="open",
        note=None,
    )
```

- [ ] **Step 4: Run the parser and pipeline tests to verify they pass**

Run: `uv run pytest tests/parsers/test_ownership_xml.py tests/worker/test_owner_pipeline.py -v`

Expected: PASS with structured XML facts accepted and missing mandatory facts routed to review generation.

- [ ] **Step 5: Commit the owner XML slice**

```bash
git add src/parsers/__init__.py src/parsers/ownership_xml.py src/worker/__init__.py src/worker/owner_pipeline.py src/cli.py tests/parsers/test_ownership_xml.py tests/worker/test_owner_pipeline.py
git commit -m "feat: add owner xml parsing and review plumbing"
```

### Task 7: Persist Owner Submissions, Advance the Cursor, and Add Replay Wiring

**Files:**
- Modify: `src/worker/owner_pipeline.py`
- Modify: `src/cli.py`
- Test: `tests/worker/test_owner_pipeline.py`

- [ ] **Step 1: Extend the failing worker tests to cover persistence and cursor updates**

```python
# tests/worker/test_owner_pipeline.py
from datetime import datetime, timezone

from src.models.state import IngestionState
from src.parsers.ownership_xml import ParsedOwnershipFact, ParsedOwnershipSubmission
from src.worker.owner_pipeline import (
    build_fact_row,
    build_review_item,
    persist_owner_submission,
    update_ingestion_state,
)


class FakeSession:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


def test_persist_owner_submission_adds_facts_and_review_items():
    parsed_submission = ParsedOwnershipSubmission(
        accession_no="0000320193-24-000012",
        document_filename="primary_doc.xml",
        facts=[
            ParsedOwnershipFact(
                fact_name="issuer_cik",
                fact_value="0000320193",
                parser_method="structured_xml",
                snippet_text="0000320193",
                snippet_locator="/ownershipDocument/issuer/issuerCik",
                document_filename="primary_doc.xml",
                validation_results={"mandatory_present": True},
            ),
            ParsedOwnershipFact(
                fact_name="reporting_owner_cik",
                fact_value="",
                parser_method="structured_xml",
                snippet_text="",
                snippet_locator="/ownershipDocument/reportingOwner/reportingOwnerId/rptOwnerCik",
                document_filename="primary_doc.xml",
                validation_results={"mandatory_present": False},
            ),
        ],
    )

    session = FakeSession()
    persist_owner_submission(session=session, filing_id="filing-1", parsed_submission=parsed_submission)

    assert len(session.added) == 3
    assert [obj.__tablename__ for obj in session.added] == [
        "extracted_fact",
        "extracted_fact",
        "review_queue",
    ]


def test_update_ingestion_state_advances_cursor_values():
    state = IngestionState(cik="0000320193", route_type="owner")
    acceptance = datetime(2024, 4, 3, 12, 30, tzinfo=timezone.utc)

    updated = update_ingestion_state(
        state=state,
        accession_no="0000320193-24-000012",
        acceptance_datetime_utc=acceptance,
    )

    assert updated.last_acceptance_datetime_utc == acceptance
    assert updated.last_accession_no == "0000320193-24-000012"
```

- [ ] **Step 2: Run the worker tests to verify they fail**

Run: `uv run pytest tests/worker/test_owner_pipeline.py -v`

Expected: FAIL because `persist_owner_submission` and `update_ingestion_state` are not implemented yet.

- [ ] **Step 3: Implement persistence, cursor updates, and CLI wiring**

```python
# src/worker/owner_pipeline.py
from datetime import datetime
from hashlib import sha1

from src.domain.enums import DecisionState, ReviewReason, RouteType
from src.models.filing import ExtractedFact
from src.models.review import ReviewQueueItem
from src.models.state import IngestionState
from src.parsers.ownership_xml import ParsedOwnershipFact, ParsedOwnershipSubmission


def _fact_id(accession_no: str, fact_name: str, snippet_locator: str) -> str:
    return sha1(f"{accession_no}:{fact_name}:{snippet_locator}".encode("utf-8")).hexdigest()


def build_fact_row(filing_id: str, accession_no: str, parsed_fact: ParsedOwnershipFact) -> ExtractedFact:
    is_complete = bool(parsed_fact.validation_results.get("mandatory_present", True))
    is_numeric_ok = parsed_fact.validation_results.get("is_numeric", True)
    accepted = is_complete and is_numeric_ok
    return ExtractedFact(
        fact_id=_fact_id(accession_no, parsed_fact.fact_name, parsed_fact.snippet_locator),
        filing_id=filing_id,
        accession_no=accession_no,
        fact_name=parsed_fact.fact_name,
        fact_value=parsed_fact.fact_value,
        parser_method=parsed_fact.parser_method,
        confidence_score=0.99 if accepted else 0.30,
        confidence_bucket="high" if accepted else "low",
        decision_state=DecisionState.ACCEPTED.value if accepted else DecisionState.NEEDS_REVIEW.value,
        snippet_text=parsed_fact.snippet_text,
        snippet_locator=parsed_fact.snippet_locator,
        document_filename=parsed_fact.document_filename,
        validation_results=parsed_fact.validation_results,
        attempted_methods=[parsed_fact.parser_method],
    )


def build_review_item(accession_no: str, parsed_fact: ParsedOwnershipFact) -> ReviewQueueItem:
    return ReviewQueueItem(
        review_item_id=_fact_id(accession_no, parsed_fact.fact_name, parsed_fact.snippet_locator),
        accession_no=accession_no,
        fact_id=None,
        review_reason=ReviewReason.MANDATORY_FIELD_MISSING.value,
        payload={
            "fact_name": parsed_fact.fact_name,
            "snippet_locator": parsed_fact.snippet_locator,
            "validation_results": parsed_fact.validation_results,
        },
        status="open",
        note=None,
    )


def persist_owner_submission(session, filing_id: str, parsed_submission: ParsedOwnershipSubmission) -> None:
    for parsed_fact in parsed_submission.facts:
        fact_row = build_fact_row(
            filing_id=filing_id,
            accession_no=parsed_submission.accession_no,
            parsed_fact=parsed_fact,
        )
        session.add(fact_row)
        if fact_row.decision_state == DecisionState.NEEDS_REVIEW.value:
            session.add(build_review_item(parsed_submission.accession_no, parsed_fact))


def update_ingestion_state(
    state: IngestionState,
    accession_no: str,
    acceptance_datetime_utc: datetime,
) -> IngestionState:
    state.last_accession_no = accession_no
    state.last_acceptance_datetime_utc = acceptance_datetime_utc
    return state


def default_ingestion_state(cik: str) -> IngestionState:
    return IngestionState(cik=cik, route_type=RouteType.OWNER.value)
```

```python
# src/cli.py
import typer

from src.models import Base
from src.models import filing, registry, review, state  # noqa: F401
from src.storage.db import engine


app = typer.Typer(help="SEC filing pipeline")


@app.command("init-db")
def init_db() -> None:
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)


@app.command("owner-sync")
def owner_sync() -> None:
    """Run the owner-route sync pipeline."""
    typer.echo("run src.worker.owner_pipeline.persist_owner_submission from this command")


@app.command("replay-accession")
def replay_accession(accession_no: str) -> None:
    """Replay one archived accession."""
    typer.echo(f"load archived raw payload and rerun parser for {accession_no}")
```

- [ ] **Step 4: Run the worker tests to verify they pass**

Run: `uv run pytest tests/worker/test_owner_pipeline.py -v`

Expected: PASS with both fact persistence and ingestion-state updates covered.

- [ ] **Step 5: Commit the pipeline orchestration wiring**

```bash
git add src/worker/owner_pipeline.py src/cli.py tests/worker/test_owner_pipeline.py
git commit -m "feat: wire owner persistence and replay scaffolding"
```

## Plan Review Checklist

- Spec coverage in scope: Phase 0, Phase 1, and the minimum owner `3/4/5` slice are covered by Tasks 1 through 7.
- Explicitly out of scope for this plan: `13F`, broad issuer parsing, fuzzy mapping, spaCy training, LLM structuring, and the full QA rollout.
- No placeholders: each task names exact files, test commands, and implementation snippets.
- Type consistency: `CanonicalForm`, `DecisionState`, `ReviewReason`, `ParsedOwnershipFact`, and `ExtractedFact` are named consistently across tasks.

## Verification Commands

Run the full first-slice test suite after completing all tasks:

`uv run pytest tests/core/test_config.py tests/domain/test_forms.py tests/models/test_metadata.py tests/storage/test_raw_store.py tests/storage/test_owner_discovery.py tests/parsers/test_ownership_xml.py tests/worker/test_owner_pipeline.py -v`

Expected: all tests PASS.
