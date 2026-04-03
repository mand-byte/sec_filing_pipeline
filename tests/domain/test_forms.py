from datetime import date, datetime, timezone

from src.domain import RouteType
from src.rules.forms import canonicalize_form_type, choose_event_time, route_for_form


def test_canonicalize_form_type_detects_amendment() -> None:
    canonical = canonicalize_form_type("4/A")

    assert canonical.raw == "4/A"
    assert canonical.base == "4"
    assert canonical.is_amendment is True


def test_route_for_form_owner() -> None:
    route = route_for_form(canonicalize_form_type("4"))

    assert route is RouteType.OWNER


def test_choose_event_time_prefers_acceptance() -> None:
    acceptance = datetime(2026, 1, 2, 13, 30, tzinfo=timezone.utc)
    filing_date = date(2026, 1, 1)

    assert choose_event_time(acceptance, filing_date) == acceptance
