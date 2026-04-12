# Runtime Config Contract

The canonical runtime contract is:

- `PG_DSN`
- `CH_DSN`
- `SEC_UNIVERSE_TABLE`
- `START_DATE`
- `SCHEDULER_INTERVAL_MINUTES`
- `OFFLINE_ARTIFACTS_DIR`
- `WRITE_OFFLINE_ARTIFACTS`
- `EDGAR_IDENTITY`
- `TEXT_NORMALIZER_MODE`
- `TEXT_NORMALIZER_BASE_URL`
- `TEXT_NORMALIZER_MODEL`
- `TEXT_NORMALIZER_API_KEY`
- `TEXT_NORMALIZER_TIMEOUT_SECONDS`

During migration, legacy split env variables are still accepted:

- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `CLICKHOUSE_HOST`, `CLICKHOUSE_PORT`, `CLICKHOUSE_DATABASE`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`
- `LLM_BASE_URL`, `LLM_MODEL_NAME`, `LLM_AUTH_KEY`, `LLM_TIMEOUT_SECONDS`

When `LLM_BASE_URL` and `LLM_MODEL_NAME` are present and explicit `TEXT_NORMALIZER_*`
settings are absent, the runtime maps them to provider-backed `http_json` text
normalization for compatibility.

`EDGAR_IDENTITY` should be set to a valid SEC-compliant user identity string such as:

- `Example Company ops@example.com`

Use:

- `python main.py runtime-preflight`

to validate the configured PostgreSQL schema, ClickHouse universe table, EDGAR identity, and text normalizer settings before running live backfills.

Versioned runtime cohort config lives in:

- `configs/runtime/backfill_cohorts.yaml`

Execution follow-up should prefer DSN-style variables and keep `.env.example` as the source of truth.
