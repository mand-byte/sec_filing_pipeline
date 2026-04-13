from datetime import datetime, timezone


def _normalize_to_utc(value: datetime) -> datetime:
    """Normalize datetimes to UTC for route eligibility comparisons."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def is_filing_eligible(
    active: bool,
    delisted_utc: datetime | None,
    accepted_at: datetime,
) -> bool:
    """Decide whether one filing should still be processed for a security."""
    if active:
        return True

    if delisted_utc is None:
        return True

    return _normalize_to_utc(accepted_at) <= _normalize_to_utc(delisted_utc)


def should_skip_delisted_route(
    active: bool,
    is_completed: bool,
    snapshot: datetime | None,
    current_delisted_utc: datetime | None,
) -> bool:
    """Decide whether a completed delisted route can be skipped unchanged."""
    if snapshot is None or current_delisted_utc is None:
        return (not active) and is_completed and snapshot == current_delisted_utc

    return (not active) and is_completed and (
        _normalize_to_utc(snapshot) == _normalize_to_utc(current_delisted_utc)
    )
