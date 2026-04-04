from datetime import datetime, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from src.models import Base
from src.models import filing, parse_route_log, registry, review, state  # noqa: F401
from src.models.filing import ExtractedFact
from src.models.review import ReviewQueueItem
from src.models.state import IngestionState
from src.storage.ingestion_state_repo import IngestionStateRepository
from src.storage.parse_route_log_repo import ParseRouteLogRepository
from src.storage.raw_store import RawStore
from src.storage.sec_download_adapter import (
    DownloadedAttachment,
    DownloadedFilingBundle,
)
from src.worker.owner_pipeline import replay_owner_accession
from src.worker.owner_sync_service import OwnerSyncService


class _SubmissionClient:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.calls: list[str] = []

    def fetch_company_submissions(self, cik: str) -> dict:
        self.calls.append(cik)
        return self._payload


class _DownloadAdapter:
    def __init__(self, bundles_by_accession: dict[str, DownloadedFilingBundle]) -> None:
        self._bundles_by_accession = bundles_by_accession
        self.calls: list[tuple[str, str]] = []

    def download_owner_filing_bundle(self, cik: str, accession_no: str) -> DownloadedFilingBundle:
        self.calls.append((cik, accession_no))
        return self._bundles_by_accession[accession_no]


def _owner_payload_for_single_accession() -> dict:
    return {
        "filings": {
            "recent": {
                "form": ["4"],
                "accessionNumber": ["0000320193-24-000012"],
                "acceptanceDateTime": ["2024-04-02T10:00:00Z"],
                "primaryDocument": ["ownership.xml"],
            }
        }
    }


def _bundle_for_accession(accession_no: str) -> DownloadedFilingBundle:
    return DownloadedFilingBundle(
        cik="0000320193",
        accession_no=accession_no,
        form_type_raw="4",
        acceptance_datetime_utc=datetime(2024, 4, 2, 10, 0, tzinfo=timezone.utc),
        primary_document="ownership.xml",
        attachments=[
            DownloadedAttachment(
                filename="ownership.xml",
                content_type="text/xml",
                content=(
                    "<ownershipDocument>"
                    "<issuer><issuerCik>0000320193</issuerCik></issuer>"
                    "<reportingOwner><reportingOwnerId><rptOwnerCik>0001214156</rptOwnerCik></reportingOwnerId></reportingOwner>"
                    # Omit transaction_shares to trigger mandatory_present=False -> ReviewQueueItem
                    "<nonDerivativeTable><nonDerivativeTransaction><transactionAmounts><transactionShares/></transactionAmounts></nonDerivativeTransaction></nonDerivativeTable>"
                    "</ownershipDocument>"
                ).encode("utf-8"),
            )
        ],
    )


def test_owner_phase_a1_incremental_sync_and_replay_are_idempotent(tmp_path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()

    raw_store = RawStore(tmp_path)
    parse_route_repo = ParseRouteLogRepository(session)
    state_repo = IngestionStateRepository(session)

    submissions_client = _SubmissionClient(_owner_payload_for_single_accession())
    adapter = _DownloadAdapter(
        bundles_by_accession={"0000320193-24-000012": _bundle_for_accession("0000320193-24-000012")}
    )

    service = OwnerSyncService(
        ingestion_state_repo=state_repo,
        submissions_client=submissions_client,
        sec_download_adapter=adapter,
        session=session,
        parse_route_logger=parse_route_repo,
        raw_store=raw_store,
        now_fn=lambda: datetime(2026, 4, 3, 14, 0, tzinfo=timezone.utc),
    )

    first = service.sync_owner(cik="320193", run_id="run-cold-start")
    session.commit()

    assert first.discovered_count == 1
    assert first.processed_count == 1
    assert first.last_accession_no == "0000320193-24-000012"

    persisted_state = session.get(IngestionState, ("0000320193", "owner"))
    assert persisted_state is not None
    assert persisted_state.last_accession_no == "0000320193-24-000012"
    assert persisted_state.last_acceptance_datetime_utc is not None

    fact_count_after_first = session.scalar(select(func.count(ExtractedFact.fact_id)))
    review_count_after_first = session.scalar(
        select(func.count(ReviewQueueItem.review_item_id))
    )

    # Verify that the validation-failure XML created a ReviewQueueItem
    assert review_count_after_first > 0, "Test setup: should create ReviewQueueItem for missing mandatory field"

    second = service.sync_owner(cik="320193", run_id="run-incremental")
    session.commit()

    assert second.discovered_count == 0
    assert second.processed_count == 0
    assert second.last_accession_no is None

    assert fact_count_after_first == session.scalar(
        select(func.count(ExtractedFact.fact_id))
    )
    assert review_count_after_first == session.scalar(
        select(func.count(ReviewQueueItem.review_item_id))
    )

    assert adapter.calls == [
        ("0000320193", "0000320193-24-000012"),
    ]

    replay_processed = replay_owner_accession(
        session=session,
        parse_route_logger=parse_route_repo,
        raw_store=raw_store,
        sec_download_adapter=adapter,
        cik="0000320193",
        accession_no="0000320193-24-000012",
        run_id="run-replay",
        attempted_at_utc=datetime(2026, 4, 3, 14, 30, tzinfo=timezone.utc),
    )
    session.commit()

    assert replay_processed == 1

    assert fact_count_after_first == session.scalar(
        select(func.count(ExtractedFact.fact_id))
    )
    assert review_count_after_first == session.scalar(
        select(func.count(ReviewQueueItem.review_item_id))
    )

    assert len(adapter.calls) == 2
    assert adapter.calls[-1] == ("0000320193", "0000320193-24-000012")
