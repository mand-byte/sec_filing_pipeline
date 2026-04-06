from datetime import datetime, timezone

from src.pipeline.rules import is_filing_eligible, should_skip_delisted_route


def test_is_filing_eligible_returns_true_for_active_security():
    accepted_at = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    delisted_utc = datetime(2024, 12, 31, 0, 0, tzinfo=timezone.utc)

    assert is_filing_eligible(True, delisted_utc, accepted_at) is True


def test_is_filing_eligible_allows_inactive_filing_on_or_before_delisted_time():
    delisted_utc = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)

    assert is_filing_eligible(False, delisted_utc, delisted_utc) is True


def test_is_filing_eligible_rejects_inactive_filing_after_delisted_time():
    delisted_utc = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    accepted_at = datetime(2025, 1, 15, 10, 0, 1, tzinfo=timezone.utc)

    assert is_filing_eligible(False, delisted_utc, accepted_at) is False


def test_should_skip_delisted_route_only_when_inactive_completed_and_snapshot_matches():
    snapshot = datetime(2025, 2, 1, 0, 0, tzinfo=timezone.utc)

    assert should_skip_delisted_route(False, True, snapshot, snapshot) is True
    assert should_skip_delisted_route(True, True, snapshot, snapshot) is False
    assert should_skip_delisted_route(False, False, snapshot, snapshot) is False
    assert (
        should_skip_delisted_route(
            False,
            True,
            datetime(2025, 2, 1, 0, 0, tzinfo=timezone.utc),
            datetime(2025, 2, 2, 0, 0, tzinfo=timezone.utc),
        )
        is False
    )
