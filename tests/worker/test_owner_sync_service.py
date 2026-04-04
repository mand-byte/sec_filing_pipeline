from dataclasses import dataclass
from datetime import datetime, timezone

from src.models.state import IngestionState
from src.storage.owner_discovery import DiscoveryCursor, DiscoveredFiling
from src.storage.sec_download_adapter import DownloadedFilingBundle
from src.worker.owner_sync_service import OwnerSyncService


@dataclass
class _Adapter:
    bundles_by_accession: dict[str, DownloadedFilingBundle]

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def download_owner_filing_bundle(self, cik: str, accession_no: str) -> DownloadedFilingBundle:
        self.calls.append((cik, accession_no))
        return self.bundles_by_accession[accession_no]


class _SubmissionClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[str] = []

    def fetch_company_submissions(self, cik: str) -> dict:
        self.calls.append(cik)
        return self.payload


class _StateRepo:
    def __init__(self, state: IngestionState) -> None:
        self.state = state
        self.advance_calls: list[tuple[str, datetime]] = []

    def get_or_create(self, cik: str, route_type: str) -> IngestionState:
        assert cik == self.state.cik
        assert route_type == "owner"
        return self.state

    def advance(
        self,
        state: IngestionState,
        accession_no: str,
        acceptance_datetime_utc: datetime,
    ) -> IngestionState:
        self.advance_calls.append((accession_no, acceptance_datetime_utc))
        state.last_accession_no = accession_no
        state.last_acceptance_datetime_utc = acceptance_datetime_utc
        return state


def _empty_payload() -> dict:
    return {
        "filings": {
            "recent": {
                "form": [],
                "accessionNumber": [],
                "acceptanceDateTime": [],
                "primaryDocument": [],
            }
        }
    }


def test_owner_sync_returns_counts_and_does_not_advance_on_empty_discovery() -> None:
    state = IngestionState(
        cik="0000320193",
        route_type="owner",
        last_acceptance_datetime_utc=None,
        last_accession_no=None,
    )
    state_repo = _StateRepo(state)
    submissions_client = _SubmissionClient(_empty_payload())

    service = OwnerSyncService(
        ingestion_state_repo=state_repo,
        submissions_client=submissions_client,
        sec_download_adapter=_Adapter(bundles_by_accession={}),
        ingest_bundle_fn=lambda **_: 0,
        now_fn=lambda: datetime(2026, 4, 3, 14, 0, tzinfo=timezone.utc),
    )

    result = service.sync_owner(cik="320193", run_id="run-1")

    assert result.discovered_count == 0
    assert result.processed_count == 0
    assert result.last_accession_no is None
    assert submissions_client.calls == ["0000320193"]
    assert state_repo.advance_calls == []


def test_owner_sync_discovers_downloads_ingests_and_advances_cursor() -> None:
    canonical_cik = "0000320193"
    discovered = [
        DiscoveredFiling(
            cik="0000320193",
            accession_no="0000320193-24-000012",
            form_type_raw="4",
            acceptance_datetime_utc=datetime(2024, 4, 2, 10, 0, tzinfo=timezone.utc),
            primary_document="doc-12.xml",
        ),
        DiscoveredFiling(
            cik="0000320193",
            accession_no="0000320193-24-000013",
            form_type_raw="4/A",
            acceptance_datetime_utc=datetime(2024, 4, 3, 12, 30, tzinfo=timezone.utc),
            primary_document="doc-13.xml",
        ),
    ]

    state = IngestionState(
        cik="0000320193",
        route_type="owner",
        last_acceptance_datetime_utc=datetime(2024, 4, 1, 9, 0, tzinfo=timezone.utc),
        last_accession_no="0000320193-24-000011",
    )
    state_repo = _StateRepo(state)
    submissions_client = _SubmissionClient(payload={"any": "payload"})

    bundle_12 = DownloadedFilingBundle(
        cik="0000320193",
        accession_no="0000320193-24-000012",
        form_type_raw="4",
        acceptance_datetime_utc=datetime(2024, 4, 2, 10, 0, tzinfo=timezone.utc),
        primary_document="doc-12.xml",
        attachments=[],
    )
    bundle_13 = DownloadedFilingBundle(
        cik="0000320193",
        accession_no="0000320193-24-000013",
        form_type_raw="4/A",
        acceptance_datetime_utc=datetime(2024, 4, 3, 12, 30, tzinfo=timezone.utc),
        primary_document="doc-13.xml",
        attachments=[],
    )
    adapter = _Adapter(
        bundles_by_accession={
            "0000320193-24-000012": bundle_12,
            "0000320193-24-000013": bundle_13,
        }
    )

    ingest_calls: list[dict] = []

    def _ingest_bundle(**kwargs) -> int:
        ingest_calls.append(kwargs)
        return 3 if kwargs["bundle"].accession_no.endswith("12") else 2

    discovery_calls: list[tuple[str, dict, DiscoveryCursor | None]] = []

    def _discover(cik: str, payload: dict, cursor: DiscoveryCursor | None):
        discovery_calls.append((cik, payload, cursor))
        return discovered

    service = OwnerSyncService(
        ingestion_state_repo=state_repo,
        submissions_client=submissions_client,
        sec_download_adapter=adapter,
        ingest_bundle_fn=_ingest_bundle,
        discover_owner_filings_fn=_discover,
        now_fn=lambda: datetime(2026, 4, 3, 14, 0, tzinfo=timezone.utc),
    )

    result = service.sync_owner(cik="320193", run_id="run-2")

    assert result.discovered_count == 2
    assert result.processed_count == 5
    assert result.last_accession_no == "0000320193-24-000013"

    assert submissions_client.calls == [canonical_cik]
    assert len(discovery_calls) == 1
    discovery_cik, discovery_payload, discovery_cursor = discovery_calls[0]
    assert discovery_cik == canonical_cik
    assert discovery_payload == {"any": "payload"}
    assert discovery_cursor == DiscoveryCursor(
        last_acceptance_datetime_utc=datetime(2024, 4, 1, 9, 0, tzinfo=timezone.utc),
        last_accession_no="0000320193-24-000011",
    )

    assert adapter.calls == [
        (canonical_cik, "0000320193-24-000012"),
        (canonical_cik, "0000320193-24-000013"),
    ]
    assert len(ingest_calls) == 2
    assert [
        (call["bundle"].cik, call["bundle"].accession_no)
        for call in ingest_calls
    ] == [
        (canonical_cik, "0000320193-24-000012"),
        (canonical_cik, "0000320193-24-000013"),
    ]
    assert [
        (call["discovered_filing"].cik, call["discovered_filing"].accession_no)
        for call in ingest_calls
    ] == [
        (canonical_cik, "0000320193-24-000012"),
        (canonical_cik, "0000320193-24-000013"),
    ]
    assert all(call["run_id"] == "run-2" for call in ingest_calls)
    assert state_repo.advance_calls == [
        ("0000320193-24-000013", datetime(2024, 4, 3, 12, 30, tzinfo=timezone.utc))
    ]
