# SEC Filing Pipeline - Phase 1 Design Specification

## 1. Overview
This document specifies the technical design for Phase 1 of the SEC Filing Backend. The mandate of Phase 1 is to establish the foundation: package initialization, routing enums, models, event time rules, and ingestion state schemas.

## 2. Core Principles
- **Precision First**: The highest goal. System defaults to determinism over guesswork.
- **Stateless Application Architecture**: The Python daemon holds no running complex state. **PostgreSQL is the single source of truth.** The daemon crashes/restarts seamlessly by polling the database to find what tasks are pending.
- **Single Operational Database**: PostgreSQL handles all ingestion state, dedup, and fact persistence locally.
- **External Integration**: Read-only connection to existing ClickHouse to source CIK dimensions from `quant_data.us_stock_universe`.

## 3. Tech Stack
- **Language**: Python 3.12+ 
- **Package Manager**: `uv`
- **Database Engine & ORM**: PostgreSQL (`SQLAlchemy 2.0` + `psycopg`)
- **Data Validation**: `Pydantic` v2

## 4. Architecture & Database Design

### 4.1 "Stateless" Orchestration strategy
The background system runs on a loop or via cron. In a typical cycle:
1. Fetch active targets: Read target CIKs from ClickHouse `quant_data.us_stock_universe`.
2. Sync target list: Compare them against PostgreSQL target tasks. 
3. Resume Crawl: The daemon queries the PostgreSQL `ingestion_state` table for the target to get the checkpoint (`last_acceptance_datetime_utc` and `last_accession_no`).
4. Execute: Perform crawl/parse. Use `ON CONFLICT (cik, route_type) DO UPDATE` to bump the cursor in the `ingestion_state` table. This UPSERT acts as the only persistence mechanism.

### 4.2 Local PostgreSQL Schema (Phase 1)
**Table: `ingestion_state`**
Manages the crawling cursor statelessly.
- `cik` (VARCHAR/FK) - primary key component
- `route_type` (VARCHAR) - primary key component ('issuer', 'owner', 'holdings')
- `last_acceptance_datetime_utc` (TIMESTAMP)
- `last_accession_no` (VARCHAR)
- `updated_at` (TIMESTAMP)

### 4.3 Explicit Enums & Form Routing
The domain model strictly enforces route splitting.
- **`RouteType`**: `ISSUER`, `OWNER`, `HOLDINGS`
- **`FormType`**: Categorized by canonical types (`10-K`, `10-K/A`, `13F-HR`, `13D`, etc). 
- **Amendment Identification**: Derived statelessly based on form code `/A`. Each submission record tracks `amendment_group_key` (the original accession ID tied to the filing family) and `amendment_sequence` (0 for original, strictly incremented for subsequent amendments).

### 4.4 Raw Persistence Layout
Though storage happens securely in later phases, the abstraction determines paths based entirely on hashes:
- Filing level: `/[Storage-Root]/[CIK]/[Accession]/metadata.json`
- Document level: `/[Storage-Root]/[CIK]/[Accession]/[Content-Hash]_document.extension`

## 5. Directory Structure
```
sec_filing_pipeline/
├── pyproject.toml        # maintained by uv
├── .env                  # dev environmental variables
└── src/
    ├── cli.py            # Entry points and commands
    ├── core/             # Base configurations and constants
    ├── domain/           # Business entities (Routes, Form Enums)
    ├── models/           # SQLAlchemy schemas
    ├── rules/            # Deterministic static rules (e.g. amendment parsing)
    ├── storage/          # Connectors (PostgreSQL engine, CH readonly reader)
    └── worker/           # Application state loop processors
```
