from datetime import datetime

from src.domain import CanonicalForm, RouteType

OWNER_FORMS = {"3", "4", "5", "13D", "13G", "144"}
HOLDINGS_FORMS = {"13F-HR"}


def canonicalize_form_type(form_type_raw: str) -> CanonicalForm:
    normalized = form_type_raw.strip().upper()
    is_amendment = normalized.endswith("/A")
    base = normalized[:-2] if is_amendment else normalized
    return CanonicalForm(
        form_type_raw=normalized,
        form_type_base=base,
        is_amendment=is_amendment,
    )


def route_for_form(canonical_form: CanonicalForm) -> RouteType:
    if canonical_form.form_type_base in OWNER_FORMS:
        return RouteType.OWNER
    if canonical_form.form_type_base in HOLDINGS_FORMS:
        return RouteType.HOLDINGS
    return RouteType.ISSUER


def choose_event_time(
    acceptance_datetime_utc: datetime | None, filing_date: datetime | None
) -> datetime | None:
    if acceptance_datetime_utc is not None:
        return acceptance_datetime_utc
    return filing_date
