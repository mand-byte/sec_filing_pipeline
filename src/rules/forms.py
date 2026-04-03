from datetime import date, datetime

from src.domain import CanonicalForm, RouteType

OWNER_FORMS = {"3", "4", "5", "13D", "13G", "144"}
HOLDINGS_FORMS = {"13F-HR"}


def canonicalize_form_type(form_type: str) -> CanonicalForm:
    raw = form_type.strip().upper()
    is_amendment = raw.endswith("/A")
    base = raw[:-2] if is_amendment else raw
    return CanonicalForm(raw=raw, base=base, is_amendment=is_amendment)


def route_for_form(form: CanonicalForm) -> RouteType:
    if form.base in OWNER_FORMS:
        return RouteType.OWNER
    if form.base in HOLDINGS_FORMS:
        return RouteType.HOLDINGS
    return RouteType.ISSUER


def choose_event_time(
    acceptance: datetime | None, filing_date: date
) -> datetime | date:
    if acceptance is not None:
        return acceptance
    return filing_date
