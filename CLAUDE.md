<!-- GSD:project-start source:PROJECT.md -->
## Project

**SEC Filing Precision-First Backend**

A precision-first SEC filing backend for quantitative data extraction. It ingests filings via edgartools, supports both cold-start and incremental ingestion, and persists operational truth in PostgreSQL while consuming stock universe seeds from ClickHouse. The system is designed to maximize extraction correctness and minimize manual corrections through deterministic extraction first, strict QA gates, and replayable lineage.

**Core Value:** Quant-critical filing data is extracted with verifiable correctness, auditable lineage, and minimal manual intervention.

### Constraints

- **Ingestion**: Must support cold-start and incremental ingestion — required by demand scope
- **Downloader**: Must use edgartools — explicit requirement
- **Data source**: Must consume universe from ClickHouse table `data_quant.us_stock_universe` — explicit requirement
- **State store**: PostgreSQL is source of truth for operational/extraction state — selected architecture
- **Accuracy**: Strict correctness gate for v1 acceptance — selected quality bar
- **Observability**: Parse/extraction logs must be persisted with failure reasons — explicit requirement for diagnostics and continuous improvement
<!-- GSD:project-end -->

<!-- GSD:stack-start source:STACK.md -->
## Technology Stack

Technology stack not yet documented. Will populate after codebase mapping or first phase.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
