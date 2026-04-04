from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.domain.enums import RouteType
from src.storage.owner_discovery import DiscoveryCursor, DiscoveredFiling, discover_owner_filings
from src.worker.owner_pipeline import ingest_downloaded_owner_filing_bundle


@dataclass(frozen=True, slots=True)
class OwnerSyncResult:
    discovered_count: int
    processed_count: int
    last_accession_no: str | None


def _ensure_utc_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _newest_discovered_filing(discovered: list[DiscoveredFiling]) -> DiscoveredFiling:
    return max(
        discovered,
        key=lambda item: (item.acceptance_datetime_utc, item.accession_no),
    )


class OwnerSyncService:
    def __init__(
        self,
        ingestion_state_repo,
        submissions_client,
        sec_download_adapter,
        ingest_bundle_fn: Callable[..., int] = ingest_downloaded_owner_filing_bundle,
        discover_owner_filings_fn: Callable[
            [str, dict, DiscoveryCursor | None],
            list[DiscoveredFiling],
        ] = discover_owner_filings,
        now_fn: Callable[[], datetime] | None = None,
        session: Any = None,
        parse_route_logger: Any = None,
        raw_store: Any = None,
    ) -> None:
        self._ingestion_state_repo = ingestion_state_repo
        self._submissions_client = submissions_client
        self._sec_download_adapter = sec_download_adapter
        self._ingest_bundle_fn = ingest_bundle_fn
        self._discover_owner_filings_fn = discover_owner_filings_fn
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self._session = session
        self._parse_route_logger = parse_route_logger
        self._raw_store = raw_store

    def sync_owner(
        self,
        cik: str,
        run_id: str,
        *,
        session: Any = None,
        parse_route_logger: Any = None,
        raw_store: Any = None,
    ) -> OwnerSyncResult:
        canonical_cik = str(cik).strip().zfill(10)
        state = self._ingestion_state_repo.get_or_create(
            cik=canonical_cik,
            route_type=RouteType.OWNER.value,
        )
        cursor = DiscoveryCursor(
            last_acceptance_datetime_utc=_ensure_utc_aware(
                state.last_acceptance_datetime_utc
            ),
            last_accession_no=state.last_accession_no,
        )

        payload = self._submissions_client.fetch_company_submissions(cik=canonical_cik)
        discovered = self._discover_owner_filings_fn(
            cik=canonical_cik,
            payload=payload,
            cursor=cursor,
        )

        if not discovered:
            return OwnerSyncResult(
                discovered_count=0,
                processed_count=0,
                last_accession_no=None,
            )

        attempted_at_utc = self._now_fn()
        effective_session = session if session is not None else self._session
        effective_parse_route_logger = (
            parse_route_logger
            if parse_route_logger is not None
            else self._parse_route_logger
        )
        effective_raw_store = raw_store if raw_store is not None else self._raw_store

        processed_count = 0

        for filing in discovered:
            bundle = self._sec_download_adapter.download_owner_filing_bundle(
                cik=canonical_cik,
                accession_no=filing.accession_no,
            )
            processed_count += int(
                self._ingest_bundle_fn(
                    session=effective_session,
                    parse_route_logger=effective_parse_route_logger,
                    raw_store=effective_raw_store,
                    bundle=bundle,
                    run_id=run_id,
                    attempted_at_utc=attempted_at_utc,
                    discovered_filing=filing,
                )
            )

        newest = _newest_discovered_filing(discovered)
        self._ingestion_state_repo.advance(
            state=state,
            accession_no=newest.accession_no,
            acceptance_datetime_utc=newest.acceptance_datetime_utc,
        )

        return OwnerSyncResult(
            discovered_count=len(discovered),
            processed_count=processed_count,
            last_accession_no=newest.accession_no,
        )
