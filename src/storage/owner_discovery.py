from dataclasses import dataclass
from datetime import datetime

from src.domain.enums import RouteType
from src.rules.forms import canonicalize_form_type, route_for_form


@dataclass(frozen=True)
class DiscoveryCursor:
    last_acceptance_datetime_utc: datetime | None
    last_accession_no: str | None


@dataclass(frozen=True)
class DiscoveredFiling:
    cik: str
    accession_no: str
    form_type_raw: str
    acceptance_datetime_utc: datetime
    primary_document: str


def discover_owner_filings(
    cik: str,
    payload: dict,
    cursor: DiscoveryCursor | None,
) -> list[DiscoveredFiling]:
    recent = payload.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    acceptance_times = recent.get("acceptanceDateTime", [])
    primary_documents = recent.get("primaryDocument", [])

    discovered: list[DiscoveredFiling] = []
    for form, accession_no, acceptance_raw, primary_document in zip(
        forms,
        accessions,
        acceptance_times,
        primary_documents,
        strict=True,
    ):
        canonical = canonicalize_form_type(form)
        if route_for_form(canonical) is not RouteType.OWNER:
            continue

        acceptance_datetime_utc = datetime.fromisoformat(
            acceptance_raw.replace("Z", "+00:00")
        )

        if cursor is not None and cursor.last_acceptance_datetime_utc is not None:
            if acceptance_datetime_utc < cursor.last_acceptance_datetime_utc:
                continue
            if (
                acceptance_datetime_utc == cursor.last_acceptance_datetime_utc
                and accession_no <= (cursor.last_accession_no or "")
            ):
                continue

        discovered.append(
            DiscoveredFiling(
                cik=cik,
                accession_no=accession_no,
                form_type_raw=form,
                acceptance_datetime_utc=acceptance_datetime_utc,
                primary_document=primary_document,
            )
        )

    return discovered
