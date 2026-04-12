# Production Evidence Checklist

This checklist covers the remaining non-repository proof needed before claiming full `DEMANDS.md` production completion.

## 1. Runtime configuration
Confirm one of these provider configurations is present:

- preferred:
  - `TEXT_NORMALIZER_MODE=http_json`
  - `TEXT_NORMALIZER_BASE_URL=...`
  - `TEXT_NORMALIZER_MODEL=...`
  - `TEXT_NORMALIZER_API_KEY=...`
- legacy-compatible:
  - `LLM_BASE_URL=...`
  - `LLM_MODEL_NAME=...`
  - `LLM_AUTH_KEY=...`

Also confirm:
- `PG_DSN`
- `CH_DSN`
- `SEC_UNIVERSE_TABLE`
- `EDGAR_IDENTITY`
- `OFFLINE_ARTIFACTS_DIR`

Run:
```bash
./.venv/bin/python main.py runtime-preflight
```

This should pass before attempting live backfill evidence collection.

## 2. Database rollout
Bootstrap the base schema if the target database is empty:
```bash
./.venv/bin/python main.py db-init
```

Then apply rollout SQL:
```bash
./.venv/bin/python main.py db-rollout-apply
```

Save the rollout output.

## 3. Seed historical backfill evidence

### Phase 1 deterministic cohort
```bash
./.venv/bin/python main.py backfill-cohort \
  --cohort phase1_deterministic \
  --start-date 2014-01-01
```

### Phase 2 financial cohort
```bash
./.venv/bin/python main.py backfill-cohort \
  --cohort phase2_financial \
  --route issuer \
  --start-date 2014-01-01
```

Keep the emitted `cohort manifest:` paths.

## 4. Runtime artifact verification
For every per-route runtime run id in the cohort manifest:
```bash
./.venv/bin/python main.py verify-runtime-run --run-id <runtime_run_id>
```

## 5. Strict-v2 evaluation
```bash
./.venv/bin/python main.py strict-v2-eval --artifacts-dir artifacts/golden
```

Keep the emitted `strict-v2 run_id`.

## 6. Release-gate with cohort evidence
```bash
./.venv/bin/python main.py release-gate \
  --output-dir artifacts/release_gate \
  --strict-summary artifacts/golden/<strict_run_id>/summary.json \
  --runtime-cohort-manifest <cohort_manifest_path>
```

Repeat `--strict-summary` and `--runtime-cohort-manifest` as needed.

## 7. Post-backfill incremental proof
Run controlled incremental ticks after backfill:
```bash
./.venv/bin/python main.py run-once --route issuer
./.venv/bin/python main.py run-once --route owner
./.venv/bin/python main.py run-once --route holding
```

Or controlled scheduler validation:
```bash
./.venv/bin/python main.py schedule --route issuer
```

Expected proof:
- historical filings are skipped behind watermark after backfill
- new filings persist cleanly
- `pipeline_log`, `filing_attempt`, and artifacts stay consistent

## 8. Evidence bundle to retain
- db rollout output
- strict-v2 summary path(s)
- release-gate summary
- cohort manifest(s)
- representative runtime artifact directories
- any scheduler/run-once logs showing post-backfill incremental behavior

## 9. Claim boundary
If the repository test suite is green but the checklist above has not been run on a real environment, only claim:
- repository-side DEMANDS closure complete

Do **not** claim:
- production-complete DEMANDS closure
