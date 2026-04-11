from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from src.pipeline.route_runtime import FilingBundle, RouteProcessor
from src.pipeline.types import FilingRecord


def _filing(accession_no: str, accepted_at: datetime) -> FilingRecord:
    return FilingRecord(
        accession_no=accession_no,
        cik="0000789019",
        ticker="MSFT",
        form_type="4",
        filed_at=None,
        accepted_at=accepted_at,
        period_end=None,
        is_amendment=False,
        amendment_no=None,
    )


class FakeSession:
    def __init__(self) -> None:
        self.rollback_calls = 0

    def rollback(self) -> None:
        self.rollback_calls += 1


class FakeRepo:
    def __init__(self, *, watermark: datetime | None = None, completion: object | None = None) -> None:
        self.session = FakeSession()
        self.watermark = watermark
        self.completion = completion
        self.logs: list[dict[str, object]] = []
        self.upserted_watermarks: list[tuple[str, str, datetime]] = []
        self.completed_routes: list[dict[str, object]] = []
        self.invalidations: list[tuple[str, str, str]] = []
        self.filing_attempts: list[dict[str, object]] = []

    def get_delisted_route_completion(self, *, composite_figi: str, cik: str, route: str) -> object | None:
        return self.completion

    def invalidate_delisted_route_completion(self, *, composite_figi: str, cik: str, route: str) -> None:
        self.invalidations.append((composite_figi, cik, route))

    def get_route_watermark(self, cik: str, route: str) -> datetime | None:
        return self.watermark

    def upsert_route_watermark(self, *, cik: str, route: str, accepted_at: datetime) -> None:
        self.upserted_watermarks.append((cik, route, accepted_at))

    def write_log(self, **kwargs: object) -> None:
        self.logs.append(dict(kwargs))

    def upsert_filing_attempt(self, **kwargs: object) -> None:
        self.filing_attempts.append(dict(kwargs))

    def mark_delisted_route_completed(
        self,
        *,
        composite_figi: str,
        cik: str,
        route: str,
        delisted_utc_snapshot: datetime | None,
        last_seen_accepted_at: datetime | None,
    ) -> None:
        self.completed_routes.append(
            {
                "composite_figi": composite_figi,
                "cik": cik,
                "route": route,
                "delisted_utc_snapshot": delisted_utc_snapshot,
                "last_seen_accepted_at": last_seen_accepted_at,
            }
        )


class FakePersistenceService:
    def __init__(self, *, failing_accession_no: str | None = None) -> None:
        self.failing_accession_no = failing_accession_no
        self.persisted_accessions: list[str] = []

    def persist_filing_bundle(self, *, filing: FilingRecord, route: str, facts: list[object], evidences: list[object]) -> None:
        del route, facts, evidences
        if filing.accession_no == self.failing_accession_no:
            raise RuntimeError("persist exploded")
        self.persisted_accessions.append(filing.accession_no)


def test_route_processor_continues_after_bundle_failure_and_advances_watermark_by_success() -> None:
    first_accepted_at = datetime(2024, 5, 1, tzinfo=timezone.utc)
    second_accepted_at = datetime(2024, 5, 2, tzinfo=timezone.utc)
    bundles = [
        FilingBundle(filing=_filing("0000000000-24-000001", first_accepted_at)),
        FilingBundle(filing=_filing("0000000000-24-000002", second_accepted_at)),
    ]
    repo = FakeRepo()
    persistence_service = FakePersistenceService(failing_accession_no="0000000000-24-000002")
    processor = RouteProcessor(
        repo=repo,
        persistence_service=persistence_service,
        start_date=date(2024, 1, 1),
        provider_bundle_builder=lambda **kwargs: bundles,
    )

    processor.run(
        security=SimpleNamespace(
            cik="0000789019",
            active=True,
            composite_figi="FIGI1",
            delisted_utc=None,
        ),
        route="owner",
        run_id="run-001",
    )

    assert persistence_service.persisted_accessions == ["0000000000-24-000001"]
    assert repo.session.rollback_calls == 1
    assert repo.upserted_watermarks == [("0000789019", "owner", first_accepted_at)]
    assert [log["message"] for log in repo.logs] == [
        "filing persisted",
        "filing persistence failed",
        "route processed: eligible=2 persisted=1 failed=1 skipped_before_watermark=0 skipped_ineligible=0",
    ]
    assert repo.logs[1]["error_type"] == "RuntimeError"
    assert repo.filing_attempts[:3] == [
        {
            "run_id": "run-001",
            "route": "owner",
            "accession_no": "0000000000-24-000001",
            "cik": "0000789019",
            "accepted_at": first_accepted_at,
            "status": "in_progress",
        },
        {
            "run_id": "run-001",
            "route": "owner",
            "accession_no": "0000000000-24-000001",
            "cik": "0000789019",
            "accepted_at": first_accepted_at,
            "status": "completed",
        },
        {
            "run_id": "run-001",
            "route": "owner",
            "accession_no": "0000000000-24-000002",
            "cik": "0000789019",
            "accepted_at": second_accepted_at,
            "status": "in_progress",
        },
    ]
    failed_attempt = repo.filing_attempts[3]
    assert failed_attempt["run_id"] == "run-001"
    assert failed_attempt["route"] == "owner"
    assert failed_attempt["accession_no"] == "0000000000-24-000002"
    assert failed_attempt["cik"] == "0000789019"
    assert failed_attempt["accepted_at"] == second_accepted_at
    assert failed_attempt["status"] == "failed"
    assert failed_attempt["error_type"] == "RuntimeError"
    assert "persist exploded" in str(failed_attempt["error_detail"])


def test_route_processor_marks_delisted_route_completion_with_latest_success() -> None:
    accepted_at = datetime(2024, 5, 3, tzinfo=timezone.utc)
    delisted_utc = datetime(2024, 5, 4, tzinfo=timezone.utc)
    repo = FakeRepo()
    persistence_service = FakePersistenceService()
    processor = RouteProcessor(
        repo=repo,
        persistence_service=persistence_service,
        start_date=date(2024, 1, 1),
        provider_bundle_builder=lambda **kwargs: [FilingBundle(filing=_filing("0000000000-24-000003", accepted_at))],
    )

    processor.run(
        security=SimpleNamespace(
            cik="0000789019",
            active=False,
            composite_figi="FIGI1",
            delisted_utc=delisted_utc,
        ),
        route="owner",
        run_id="run-002",
    )

    assert persistence_service.persisted_accessions == ["0000000000-24-000003"]
    assert repo.upserted_watermarks == [("0000789019", "owner", accepted_at)]
    assert repo.completed_routes == [
        {
            "composite_figi": "FIGI1",
            "cik": "0000789019",
            "route": "owner",
            "delisted_utc_snapshot": delisted_utc,
            "last_seen_accepted_at": accepted_at,
        }
    ]


def test_route_processor_invalidates_stale_delisted_completion_when_security_reactivates() -> None:
    completion = SimpleNamespace(
        is_completed=True,
        delisted_utc_snapshot=datetime(2024, 4, 30, tzinfo=timezone.utc),
    )
    repo = FakeRepo(completion=completion)
    persistence_service = FakePersistenceService()
    processor = RouteProcessor(
        repo=repo,
        persistence_service=persistence_service,
        start_date=date(2024, 1, 1),
        provider_bundle_builder=lambda **kwargs: [],
    )

    processor.run(
        security=SimpleNamespace(
            cik="0000789019",
            active=True,
            composite_figi="FIGI1",
            delisted_utc=None,
        ),
        route="holding",
        run_id="run-003",
    )

    assert repo.invalidations == [("FIGI1", "0000789019", "holding")]
    assert repo.logs == [
        {
            "run_id": "run-003",
            "route": "holding",
            "stage": "route",
            "level": "INFO",
            "message": "route processed: eligible=0 persisted=0 failed=0 skipped_before_watermark=0 skipped_ineligible=0",
            "cik": "0000789019",
            "accession_no": None,
            "error_type": None,
            "error_detail": None,
        }
    ]


def test_route_processor_logs_skip_reason_for_completed_delisted_route() -> None:
    completion = SimpleNamespace(
        is_completed=True,
        delisted_utc_snapshot=datetime(2024, 5, 4, tzinfo=timezone.utc),
    )
    repo = FakeRepo(completion=completion)
    persistence_service = FakePersistenceService()
    processor = RouteProcessor(
        repo=repo,
        persistence_service=persistence_service,
        start_date=date(2024, 1, 1),
        provider_bundle_builder=lambda **kwargs: [
            FilingBundle(
                filing=_filing(
                    "0000000000-24-000004",
                    datetime(2024, 5, 5, tzinfo=timezone.utc),
                )
            )
        ],
    )

    processor.run(
        security=SimpleNamespace(
            cik="0000789019",
            active=False,
            composite_figi="FIGI1",
            delisted_utc=datetime(2024, 5, 4, tzinfo=timezone.utc),
        ),
        route="issuer",
        run_id="run-004",
    )

    assert persistence_service.persisted_accessions == []
    assert repo.upserted_watermarks == []
    assert repo.logs == [
        {
            "run_id": "run-004",
            "route": "issuer",
            "stage": "route",
            "level": "INFO",
            "message": "route skipped: delisted route already completed",
            "cik": "0000789019",
            "accession_no": None,
            "error_type": None,
            "error_detail": None,
        }
    ]
