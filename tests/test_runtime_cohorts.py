from __future__ import annotations

from src.pipeline.runtime_cohorts import load_backfill_cohorts


def test_load_backfill_cohorts_exposes_phase_seed_sets() -> None:
    cohorts = load_backfill_cohorts()

    assert set(cohorts) == {"phase1_deterministic", "phase2_financial"}
    assert cohorts["phase1_deterministic"].tickers == ("MSFT", "AAPL", "AMZN", "NVDA", "TSLA")
    assert cohorts["phase1_deterministic"].routes == ("issuer", "owner", "holding")
    assert cohorts["phase2_financial"].tickers == ("JPM", "BAC", "WFC", "GS", "MS", "C", "JEF", "LAZ")
    assert cohorts["phase2_financial"].routes == ("issuer",)
