# Runtime Config Contract

The canonical runtime contract is:

- `PG_DSN`
- `CH_DSN`
- `SEC_UNIVERSE_TABLE`
- `START_DATE`
- `SCHEDULER_INTERVAL_MINUTES`
- `OFFLINE_ARTIFACTS_DIR`
- `WRITE_OFFLINE_ARTIFACTS`

During migration, legacy split env variables are still accepted:

- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `CLICKHOUSE_HOST`, `CLICKHOUSE_PORT`, `CLICKHOUSE_DATABASE`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`

Execution follow-up should prefer DSN-style variables and keep `.env.example` as the source of truth.
