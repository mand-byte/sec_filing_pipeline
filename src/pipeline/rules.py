from datetime import datetime


def is_filing_eligible(
    active: bool,
    delisted_utc: datetime | None,
    accepted_at: datetime,
) -> bool:
    if active:
        return True

    if delisted_utc is None:
        return True

    return accepted_at <= delisted_utc


def should_skip_delisted_route(
    active: bool,
    is_completed: bool,
    snapshot: datetime | None,
    current_delisted_utc: datetime | None,
) -> bool:
    return (not active) and is_completed and snapshot == current_delisted_utc
