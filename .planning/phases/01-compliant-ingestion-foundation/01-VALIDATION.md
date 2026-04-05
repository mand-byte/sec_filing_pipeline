---
phase: 1
slug: compliant-ingestion-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-05
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | none detected |
| **Quick run command** | `uv run pytest tests/storage/test_owner_discovery.py tests/storage/test_filing_repo.py tests/storage/test_sec_submissions_client.py -q` |
| **Full suite command** | `uv run pytest -v` |
| **Estimated runtime** | ~60-180 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/storage/test_owner_discovery.py tests/storage/test_filing_repo.py tests/storage/test_sec_submissions_client.py -q`
- **After every plan wave:** Run `uv run pytest -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 180 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 1 | ING-01 | T-1-01 | Cold-start run only schedules eligible universe CIK/form targets | integration | `uv run pytest tests/worker/test_cold_start_ingestion.py -q` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 1 | ING-05 | T-1-02 | Inactive tickers obey `acceptance_datetime_utc <= delisted_utc` boundary | unit+integration | `uv run pytest tests/storage/test_universe_filtering.py -q` | ❌ W0 | ⬜ pending |
| 1-01-03 | 02 | 1 | ING-06 | T-1-03 | Duplicate accession discovery cannot create duplicate canonical filing rows | unit+integration | `uv run pytest tests/storage/test_filing_repo.py tests/integration/test_owner_incremental_flow.py::test_owner_phase_a1_incremental_sync_and_replay_are_idempotent -q` | ✅ | ⬜ pending |
| 1-01-04 | 02 | 1 | OPS-03 | T-1-04 | SEC client enforces descriptive User-Agent + shaping + retry/backoff policy | unit+integration | `uv run pytest tests/storage/test_sec_client.py tests/storage/test_sec_submissions_client.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/storage/test_universe_filtering.py` — ING-05 universe eligibility and delisting cutoff boundaries
- [ ] `tests/worker/test_cold_start_ingestion.py` — ING-01 cold-start orchestration coverage
- [ ] `tests/storage/test_sec_client.py` — OPS-03 retry/backoff + shaping policy checks
- [ ] `tests/integration/test_universe_to_discovery_flow.py` — universe-to-dedupe integration path

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SEC fair-access compliance under concurrent worker load | OPS-03 | External SEC behavior and real throttling patterns are environment-dependent | Run representative cold-start in staging with multiple workers, verify no policy violations and stable request rates |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 180s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
