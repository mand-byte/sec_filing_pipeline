from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.db.base import Base
from src.db.models import FilingAttempt, PipelineLog, ReviewTask, RouteWatermark
from src.db.repositories import PipelineRepository
from src.pipeline.result_store import load_parsed_value
from src.pipeline.services import PersistenceService
from src.pipeline.route_runtime import FilingBundle, RouteProcessor
from src.pipeline.services import EvidenceInput, FactInput
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


def _owner_text_filing(accession_no: str, accepted_at: datetime) -> FilingRecord:
    return FilingRecord(
        accession_no=accession_no,
        cik="0000789019",
        ticker="MSFT",
        form_type="13D",
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


def _db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False)()


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


def test_route_processor_streams_provider_bundles_atomically_when_builder_supports_on_bundle() -> None:
    first_accepted_at = datetime(2024, 5, 1, tzinfo=timezone.utc)
    second_accepted_at = datetime(2024, 5, 2, tzinfo=timezone.utc)
    bundles = [
        FilingBundle(filing=_filing("0000000000-24-000101", first_accepted_at)),
        FilingBundle(filing=_filing("0000000000-24-000102", second_accepted_at)),
    ]
    events: list[str] = []

    class RecordingPersistenceService(FakePersistenceService):
        def persist_filing_bundle(self, *, filing: FilingRecord, route: str, facts: list[object], evidences: list[object]) -> None:
            events.append(f"persist:{filing.accession_no}")
            super().persist_filing_bundle(filing=filing, route=route, facts=facts, evidences=evidences)

    def streaming_builder(**kwargs):
        on_bundle = kwargs["on_bundle"]
        for bundle in bundles:
            events.append(f"build:{bundle.filing.accession_no}")
            on_bundle(bundle)
        return []

    repo = FakeRepo()
    persistence_service = RecordingPersistenceService()
    processor = RouteProcessor(
        repo=repo,
        persistence_service=persistence_service,
        start_date=date(2024, 1, 1),
        provider_bundle_builder=streaming_builder,
    )

    processor.run(
        security=SimpleNamespace(
            cik="0000789019",
            active=True,
            composite_figi="FIGI1",
            delisted_utc=None,
        ),
        route="owner",
        run_id="run-stream-001",
    )

    assert events == [
        "build:0000000000-24-000101",
        "persist:0000000000-24-000101",
        "build:0000000000-24-000102",
        "persist:0000000000-24-000102",
    ]
    assert persistence_service.persisted_accessions == [
        "0000000000-24-000101",
        "0000000000-24-000102",
    ]
    assert repo.upserted_watermarks == [
        ("0000789019", "owner", first_accepted_at),
        ("0000789019", "owner", second_accepted_at),
    ]


def test_route_processor_stops_atomic_stream_after_first_failure() -> None:
    first_accepted_at = datetime(2024, 5, 1, tzinfo=timezone.utc)
    second_accepted_at = datetime(2024, 5, 2, tzinfo=timezone.utc)
    third_accepted_at = datetime(2024, 5, 3, tzinfo=timezone.utc)
    bundles = [
        FilingBundle(filing=_filing("0000000000-24-000201", first_accepted_at)),
        FilingBundle(filing=_filing("0000000000-24-000202", second_accepted_at)),
        FilingBundle(filing=_filing("0000000000-24-000203", third_accepted_at)),
    ]
    events: list[str] = []

    def streaming_builder(**kwargs):
        on_bundle = kwargs["on_bundle"]
        for bundle in bundles:
            events.append(f"build:{bundle.filing.accession_no}")
            on_bundle(bundle)
        return []

    repo = FakeRepo()
    persistence_service = FakePersistenceService(failing_accession_no="0000000000-24-000202")
    processor = RouteProcessor(
        repo=repo,
        persistence_service=persistence_service,
        start_date=date(2024, 1, 1),
        provider_bundle_builder=streaming_builder,
    )

    processor.run(
        security=SimpleNamespace(
            cik="0000789019",
            active=True,
            composite_figi="FIGI1",
            delisted_utc=None,
        ),
        route="owner",
        run_id="run-stream-002",
    )

    assert events == [
        "build:0000000000-24-000201",
        "build:0000000000-24-000202",
    ]
    assert persistence_service.persisted_accessions == ["0000000000-24-000201"]
    assert repo.upserted_watermarks == [("0000789019", "owner", first_accepted_at)]
    assert [log["message"] for log in repo.logs] == [
        "filing persisted",
        "filing persistence failed",
        "route processed: eligible=2 persisted=1 failed=1 skipped_before_watermark=0 skipped_ineligible=0",
    ]
    assert [attempt["accession_no"] for attempt in repo.filing_attempts] == [
        "0000000000-24-000201",
        "0000000000-24-000201",
        "0000000000-24-000202",
        "0000000000-24-000202",
    ]


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


def test_route_processor_can_ignore_existing_watermark_for_historical_backfill() -> None:
    accepted_at = datetime(2024, 5, 3, tzinfo=timezone.utc)
    repo = FakeRepo(watermark=datetime(2024, 5, 10, tzinfo=timezone.utc))
    persistence_service = FakePersistenceService()
    processor = RouteProcessor(
        repo=repo,
        persistence_service=persistence_service,
        start_date=date(2024, 1, 1),
        provider_bundle_builder=lambda **kwargs: [FilingBundle(filing=_filing("0000000000-24-000003B", accepted_at))],
        ignore_existing_watermarks=True,
    )

    processor.run(
        security=SimpleNamespace(
            cik="0000789019",
            active=True,
            composite_figi="FIGI1",
            delisted_utc=None,
        ),
        route="owner",
        run_id="run-backfill-001",
    )

    assert persistence_service.persisted_accessions == ["0000000000-24-000003B"]
    assert [attempt["status"] for attempt in repo.filing_attempts] == ["in_progress", "completed"]
    assert repo.logs[-1]["message"] == "route processed: eligible=1 persisted=1 failed=0 skipped_before_watermark=0 skipped_ineligible=0"


def test_route_processor_respects_optional_end_date() -> None:
    included_accepted_at = datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc)
    excluded_accepted_at = datetime(2024, 5, 2, 12, 0, tzinfo=timezone.utc)
    repo = FakeRepo()
    persistence_service = FakePersistenceService()
    processor = RouteProcessor(
        repo=repo,
        persistence_service=persistence_service,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 5, 1),
        provider_bundle_builder=lambda **kwargs: [
            FilingBundle(filing=_filing("0000000000-24-000003C", included_accepted_at)),
            FilingBundle(filing=_filing("0000000000-24-000003D", excluded_accepted_at)),
        ],
    )

    processor.run(
        security=SimpleNamespace(
            cik="0000789019",
            active=True,
            composite_figi="FIGI1",
            delisted_utc=None,
        ),
        route="owner",
        run_id="run-backfill-end-date-001",
    )

    assert persistence_service.persisted_accessions == ["0000000000-24-000003C"]
    assert [attempt["accession_no"] for attempt in repo.filing_attempts] == [
        "0000000000-24-000003C",
        "0000000000-24-000003C",
    ]
    assert repo.logs[-1]["message"] == "route processed: eligible=1 persisted=1 failed=0 skipped_before_watermark=0 skipped_ineligible=0"


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


def test_route_processor_db_backed_run_persists_attempts_logs_and_watermark() -> None:
    session = _db_session()
    repo = PipelineRepository(session)
    persistence = PersistenceService(session)
    accepted_at = datetime(2024, 5, 6, tzinfo=timezone.utc)
    bundle = FilingBundle(
        filing=_filing("0000000000-24-000010", accepted_at),
        facts=[
            FactInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                value_numeric=100.0,
                confidence=0.99,
            )
        ],
        evidences=[
            EvidenceInput(
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                locator_kind="obj",
                source_span="transactions[0].shares",
                raw_value="100",
                normalized_value="100.0",
            )
        ],
    )
    processor = RouteProcessor(
        repo=repo,
        persistence_service=persistence,
        start_date=date(2024, 1, 1),
        provider_bundle_builder=lambda **kwargs: [bundle],
    )

    processor.run(
        security=SimpleNamespace(
            cik="0000789019",
            active=True,
            composite_figi="FIGI1",
            delisted_utc=None,
        ),
        route="owner",
        run_id="run-db-001",
    )

    attempts = session.query(FilingAttempt).order_by(FilingAttempt.id.asc()).all()
    logs = session.query(PipelineLog).order_by(PipelineLog.id.asc()).all()
    watermark = session.query(RouteWatermark).one()

    assert [attempt.status for attempt in attempts] == ["completed"]
    assert attempts[0].run_id == "run-db-001"
    assert attempts[0].accession_no == "0000000000-24-000010"
    assert [log.message for log in logs] == [
        "filing persisted",
        "route processed: eligible=1 persisted=1 failed=0 skipped_before_watermark=0 skipped_ineligible=0",
    ]
    assert watermark.cik == "0000789019"
    assert watermark.route == "owner"
    assert watermark.last_accepted_at == accepted_at.replace(tzinfo=None)


def test_route_processor_db_backed_failure_persists_error_detail_and_skips_watermark() -> None:
    session = _db_session()
    repo = PipelineRepository(session)
    accepted_at = datetime(2024, 5, 7, tzinfo=timezone.utc)
    bundle = FilingBundle(
        filing=_filing("0000000000-24-000011", accepted_at),
        facts=[],
        evidences=[],
    )

    class ExplodingPersistenceService:
        def persist_filing_bundle(self, *, filing: FilingRecord, route: str, facts: list[object], evidences: list[object]) -> None:
            del filing, route, facts, evidences
            raise RuntimeError("db-backed persist exploded")

    processor = RouteProcessor(
        repo=repo,
        persistence_service=ExplodingPersistenceService(),
        start_date=date(2024, 1, 1),
        provider_bundle_builder=lambda **kwargs: [bundle],
    )

    processor.run(
        security=SimpleNamespace(
            cik="0000789019",
            active=True,
            composite_figi="FIGI1",
            delisted_utc=None,
        ),
        route="owner",
        run_id="run-db-002",
    )

    attempts = session.query(FilingAttempt).order_by(FilingAttempt.id.asc()).all()
    logs = session.query(PipelineLog).order_by(PipelineLog.id.asc()).all()
    watermarks = session.query(RouteWatermark).all()

    assert [attempt.status for attempt in attempts] == ["failed"]
    assert attempts[0].error_type == "RuntimeError"
    assert "db-backed persist exploded" in str(attempts[0].error_detail)
    assert [log.message for log in logs] == [
        "filing persistence failed",
        "route processed: eligible=1 persisted=0 failed=1 skipped_before_watermark=0 skipped_ineligible=0",
    ]
    assert logs[0].error_type == "RuntimeError"
    assert "db-backed persist exploded" in str(logs[0].error_detail)
    assert watermarks == []


def test_route_processor_logs_provider_bundle_builder_failure_and_continues() -> None:
    repo = FakeRepo()
    persistence_service = FakePersistenceService()
    processor = RouteProcessor(
        repo=repo,
        persistence_service=persistence_service,
        start_date=date(2024, 1, 1),
        provider_bundle_builder=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("fetch exploded")),
    )

    processor.run(
        security=SimpleNamespace(
            cik="0000789019",
            active=True,
            composite_figi="FIGI1",
            delisted_utc=None,
        ),
        route="issuer",
        run_id="run-provider-failure",
    )

    assert repo.logs == [
        {
            "run_id": "run-provider-failure",
            "route": "issuer",
            "cik": "0000789019",
            "stage": "extract",
            "level": "ERROR",
            "message": "provider bundle build failed",
            "accession_no": None,
            "error_type": "RuntimeError",
            "error_detail": repo.logs[0]["error_detail"],
        },
        {
            "run_id": "run-provider-failure",
            "route": "issuer",
            "stage": "route",
            "level": "INFO",
            "message": "route processed: eligible=0 persisted=0 failed=0 skipped_before_watermark=0 skipped_ineligible=0",
            "cik": "0000789019",
            "accession_no": None,
            "error_type": None,
            "error_detail": None,
        },
    ]
    assert "fetch exploded" in str(repo.logs[0]["error_detail"])


def test_route_processor_marks_provider_uncertain_text_fact_for_review_even_when_template_seen() -> None:
    session = _db_session()
    repo = PipelineRepository(session)
    persistence = PersistenceService(session)
    previous_accepted_at = datetime(2024, 5, 5, tzinfo=timezone.utc)
    previous_filing = _owner_text_filing("0000000000-24-000020", previous_accepted_at)
    persistence.persist_filing_bundle(
        filing=previous_filing,
        route="owner",
        facts=[
            FactInput(
                field_name="beneficial_ownership_intent_quant",
                subject_key="document",
                value_text="passive",
                value_json='{"group_formed": false, "horizon": "medium", "stance": "passive"}',
                confidence=0.99,
            )
        ],
        evidences=[
            EvidenceInput(
                field_name="beneficial_ownership_intent_quant",
                subject_key="document",
                locator_kind="section_window",
                source_span="0:7",
                source_section="Purpose of Transaction",
                source_xpath="sections[Purpose of Transaction]",
                adequacy_signals_json='{"confidence":0.95,"sufficient_context":true,"multiple_candidate_targets":false}',
                retry_history_json="[]",
                selection_trace_json='{"selected_value":"passive"}',
                raw_value="passive",
                normalized_value="passive",
            )
        ],
    )

    accepted_at = datetime(2024, 5, 6, tzinfo=timezone.utc)
    bundle = FilingBundle(
        filing=_owner_text_filing("0000000000-24-000021", accepted_at),
        facts=[
            FactInput(
                field_name="beneficial_ownership_intent_quant",
                subject_key="document",
                value_text="passive",
                value_json='{"group_formed": false, "horizon": "medium", "stance": "passive"}',
                confidence=0.99,
            )
        ],
        evidences=[
            EvidenceInput(
                field_name="beneficial_ownership_intent_quant",
                subject_key="document",
                locator_kind="section_window",
                source_span="0:7",
                source_section="Purpose of Transaction",
                source_xpath="sections[Purpose of Transaction]",
                adequacy_signals_json='{"confidence":0.2,"sufficient_context":true,"multiple_candidate_targets":false}',
                retry_history_json='[{"attempt":1,"action":"initial"}]',
                selection_trace_json='{"selected_value":"passive"}',
                raw_value="passive",
                normalized_value="passive",
            )
        ],
    )
    processor = RouteProcessor(
        repo=repo,
        persistence_service=persistence,
        start_date=date(2024, 1, 1),
        provider_bundle_builder=lambda **kwargs: [bundle],
    )

    processor.run(
        security=SimpleNamespace(
            cik="0000789019",
            active=True,
            composite_figi="FIGI1",
            delisted_utc=None,
        ),
        route="owner",
        run_id="run-db-provider-uncertain",
    )

    fact = load_parsed_value(
        session=session,
        accession_no="0000000000-24-000021",
        route="owner",
        field_name="beneficial_ownership_intent_quant",
        subject_key="document",
    )
    review_tasks = session.query(ReviewTask).filter(ReviewTask.accession_no == "0000000000-24-000021").all()

    assert fact is not None
    assert len(review_tasks) == 1
    assert review_tasks[0].reason == "provider_low_confidence"
