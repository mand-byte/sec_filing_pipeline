# AGENTS.md

Guidance for agentic coding agents working in `sec_filing_pipeline`.

## 1) Repository Facts

- Language: Python
- Package manager/runtime: `uv`
- Python version: `.python-version` is `3.13` (project requires `>=3.12`)
- Test framework: `pytest`
- Packaging backend: `hatchling`
- CLI entrypoint: `main.py` (Typer app in `src/cli.py`)
- Main source root: `src/`
- Tests root: `tests/`

## 2) Rules Files Check (Cursor / Copilot)

I searched for repository-level agent-instruction files:

- `.cursor/rules/**` -> not found
- `.cursorrules` -> not found
- `.github/copilot-instructions.md` -> not found

If these files are added later, treat them as higher-priority, repository-specific instructions and update this file.

## 3) Environment Setup

Run from repository root:

```bash
uv sync --dev
```

If dependencies are already synced and you only need commands, use `uv run ...` directly.

## 4) Build / Lint / Test Commands

This repo currently has minimal tool configuration in `pyproject.toml`, so prefer the commands below.

### 4.1 Build / Run

- Run CLI help:

```bash
uv run python main.py --help
```

- Initialize DB schema:

```bash
uv run python main.py init-db
```

- Run owner sync placeholder command:

```bash
uv run python main.py owner-sync
```

- Replay accession placeholder command:

```bash
uv run python main.py replay-accession 0000320193-24-000012
```

- Build wheel/sdist:

```bash
uv build
```

### 4.2 Lint / Format

No lint tool is pinned in `pyproject.toml` yet. If `ruff` is available in your env, use:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
```

If these fail due to missing `ruff`, install/add it first rather than inventing a new lint stack.

### 4.3 Tests

- Run all tests:

```bash
uv run pytest -v
```

- Run one test file:

```bash
uv run pytest tests/storage/test_raw_store.py -v
```

- Run one test function (most important single-test pattern):

```bash
uv run pytest tests/storage/test_raw_store.py::test_persist_document_writes_to_deterministic_documents_path -v
```

- Run tests by keyword expression:

```bash
uv run pytest -k owner_pipeline -v
```

- Stop on first failure:

```bash
uv run pytest -x -v
```

## 5) Codebase Map (High Signal)

- `main.py`: minimal executable entrypoint into Typer app.
- `src/cli.py`: command definitions (`init-db`, `owner-sync`, `replay-accession`).
- `src/core/config.py`: settings via Pydantic Settings, reads `.env`.
- `src/domain/enums.py`: canonical enums and form dataclass types.
- `src/rules/forms.py`: form canonicalization, route dispatch, event time selection.
- `src/storage/sec_client.py`: SEC JSON client with user-agent + rate limiting.
- `src/storage/raw_store.py`: deterministic raw artifact persistence + path validation.
- `src/storage/owner_discovery.py`: owner-form discovery and cursor-based incrementals.
- `src/parsers/ownership_xml.py`: XML ownership parser with XXE/DOCTYPE protections.
- `src/worker/owner_pipeline.py`: fact row/review item creation and ingestion cursor updates.
- `src/models/*.py`: SQLAlchemy models for filing, review queue, registries, ingestion state.

## 6) Style Guidelines (Inferred From Existing Code)

Follow existing repository patterns unless explicitly told otherwise.

### 6.1 Imports

- Group imports in this order: stdlib -> third-party -> local `src.*`.
- Use absolute imports from `src` (e.g., `from src.rules.forms import ...`).
- Keep imports explicit; avoid wildcard imports.

### 6.2 Typing

- Use Python 3.12+ style typing: `list[str]`, `dict[str, str]`, `A | B`.
- Add return type annotations on functions (`-> None` where applicable).
- Prefer concrete types for dataclass fields and function arguments.

### 6.3 Naming

- Functions/variables/modules: `snake_case`.
- Classes/dataclasses/enums: `PascalCase`.
- Constants: `UPPER_SNAKE_CASE` (e.g., form sets in `rules/forms.py`).
- Test names: `test_<behavior>`.

### 6.4 Data Modeling

- Use dataclasses for small immutable data carriers (`@dataclass(frozen=True)`; `slots=True` where useful).
- Use SQLAlchemy typed declarative patterns (`Mapped[...]`, `mapped_column(...)`).
- Preserve deterministic IDs and keys when extending persistence logic.

### 6.5 Error Handling

- Raise specific exceptions for invalid input (`ValueError` for path component validation).
- Fail closed on parser/security-sensitive paths (e.g., reject unsafe XML constructs).
- Do not silently swallow parsing/storage errors; propagate with context.

### 6.6 Determinism / Idempotency

- Keep ingestion idempotent: avoid duplicate inserts on reprocessing.
- Prefer deterministic keys/hashes for artifacts and fact/review identifiers.
- Maintain monotonic cursor update logic (`acceptance_datetime_utc`, then accession tie-breaker).

## 7) Testing Expectations for New Changes

- Add/adjust tests in `tests/` for every behavior change.
- Prefer focused unit tests near the changed module.
- For bug fixes: write or update a regression test first.
- Validate both happy path and key edge/error paths.
- Keep fixtures lightweight; this codebase favors direct object construction.

## 8) Working Agreement for Agents

- Do not introduce new frameworks/tools unless the repo already adopted them or user requested them.
- Keep changes minimal, local, and consistent with current architecture.
- Preserve security posture in XML/network/file handling code.
- Avoid large refactors while implementing scoped feature requests.
- If you add a new mandatory command/tool, update this `AGENTS.md` in the same change.
