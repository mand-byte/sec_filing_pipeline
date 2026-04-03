from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.base import Base
from src.models.parse_route_log import ParseRouteLog
from src.storage.parse_route_log_repo import ParseRouteLogRepository


@dataclass(frozen=True, slots=True)
class _Row:
    id: str
    accession_no: str
    document_id: str
    document_type: str
    attempted_at_utc: datetime
    failure_type: str | None


class _FakeSession:
    def __init__(self) -> None:
        self.rows: list[_Row] = []


def test_query_filters_by_document_type_attempt_window_and_failure_type() -> None:
    base_time = datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc)
    session = _FakeSession()
    repo = ParseRouteLogRepository(session)

    session.rows.extend(
        [
            _Row(
                id="match-1",
                accession_no="0000320193-24-000012",
                document_id="doc-1",
                document_type="4",
                attempted_at_utc=base_time + timedelta(minutes=5),
                failure_type="parse",
            ),
            _Row(
                id="match-2",
                accession_no="0000320193-24-000013",
                document_id="doc-2",
                document_type="4",
                attempted_at_utc=base_time + timedelta(minutes=20),
                failure_type="parse",
            ),
            _Row(
                id="wrong-type",
                accession_no="0000320193-24-000014",
                document_id="doc-3",
                document_type="8-K",
                attempted_at_utc=base_time + timedelta(minutes=8),
                failure_type="parse",
            ),
            _Row(
                id="wrong-window",
                accession_no="0000320193-24-000015",
                document_id="doc-4",
                document_type="4",
                attempted_at_utc=base_time + timedelta(hours=2),
                failure_type="parse",
            ),
            _Row(
                id="wrong-failure",
                accession_no="0000320193-24-000016",
                document_id="doc-5",
                document_type="4",
                attempted_at_utc=base_time + timedelta(minutes=7),
                failure_type="logic",
            ),
        ]
    )

    rows = repo.query(
        document_type="4",
        start_utc=base_time,
        end_utc=base_time + timedelta(minutes=30),
        failure_type="parse",
        limit=10,
        offset=0,
    )

    assert [row.id for row in rows] == ["match-1", "match-2"]


def test_timeline_returns_one_document_pair_in_chronological_order() -> None:
    base_time = datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc)
    session = _FakeSession()
    repo = ParseRouteLogRepository(session)

    session.rows.extend(
        [
            _Row(
                id="later",
                accession_no="0000320193-24-000012",
                document_id="doc-1",
                document_type="4",
                attempted_at_utc=base_time + timedelta(minutes=20),
                failure_type="parse",
            ),
            _Row(
                id="other-accession",
                accession_no="0000320193-24-000013",
                document_id="doc-1",
                document_type="4",
                attempted_at_utc=base_time + timedelta(minutes=1),
                failure_type="parse",
            ),
            _Row(
                id="earlier",
                accession_no="0000320193-24-000012",
                document_id="doc-1",
                document_type="4",
                attempted_at_utc=base_time + timedelta(minutes=3),
                failure_type="parse",
            ),
            _Row(
                id="other-document",
                accession_no="0000320193-24-000012",
                document_id="doc-2",
                document_type="4",
                attempted_at_utc=base_time + timedelta(minutes=4),
                failure_type="parse",
            ),
            _Row(
                id="middle",
                accession_no="0000320193-24-000012",
                document_id="doc-1",
                document_type="4",
                attempted_at_utc=base_time + timedelta(minutes=10),
                failure_type="parse",
            ),
        ]
    )

    rows = repo.timeline(
        accession_no="0000320193-24-000012",
        document_id="doc-1",
    )

    assert [row.id for row in rows] == ["earlier", "middle", "later"]


def test_query_with_none_failure_type_does_not_filter_by_failure_type() -> None:
    base_time = datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc)
    session = _FakeSession()
    repo = ParseRouteLogRepository(session)

    session.rows.extend(
        [
            _Row(
                id="failure-parse",
                accession_no="0000320193-24-000012",
                document_id="doc-1",
                document_type="4",
                attempted_at_utc=base_time + timedelta(minutes=1),
                failure_type="parse",
            ),
            _Row(
                id="failure-logic",
                accession_no="0000320193-24-000013",
                document_id="doc-2",
                document_type="4",
                attempted_at_utc=base_time + timedelta(minutes=2),
                failure_type="logic",
            ),
            _Row(
                id="failure-none",
                accession_no="0000320193-24-000014",
                document_id="doc-3",
                document_type="4",
                attempted_at_utc=base_time + timedelta(minutes=3),
                failure_type=None,
            ),
        ]
    )

    rows = repo.query(
        document_type="4",
        start_utc=base_time,
        end_utc=base_time + timedelta(minutes=10),
        failure_type=None,
        limit=10,
        offset=0,
    )

    assert [row.id for row in rows] == [
        "failure-parse",
        "failure-logic",
        "failure-none",
    ]


def test_timeline_orders_equal_timestamps_by_id() -> None:
    base_time = datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc)
    session = _FakeSession()
    repo = ParseRouteLogRepository(session)

    session.rows.extend(
        [
            _Row(
                id="c",
                accession_no="0000320193-24-000012",
                document_id="doc-1",
                document_type="4",
                attempted_at_utc=base_time,
                failure_type="parse",
            ),
            _Row(
                id="a",
                accession_no="0000320193-24-000012",
                document_id="doc-1",
                document_type="4",
                attempted_at_utc=base_time,
                failure_type="parse",
            ),
            _Row(
                id="b",
                accession_no="0000320193-24-000012",
                document_id="doc-1",
                document_type="4",
                attempted_at_utc=base_time,
                failure_type="parse",
            ),
        ]
    )

    rows = repo.timeline(
        accession_no="0000320193-24-000012",
        document_id="doc-1",
    )

    assert [row.id for row in rows] == ["a", "b", "c"]


def test_sqlalchemy_append_and_query_persist_and_filter() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    repo = ParseRouteLogRepository(session)
    base_time = datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc)

    repo.append(
        ParseRouteLog(
            id="id-1",
            run_id="run-1",
            route_type="owner",
            filing_id="filing-1",
            accession_no="0000320193-24-000012",
            cik="0000320193",
            document_id="doc-1",
            document_type="4",
            document_filename="ownership.xml",
            document_path="raw/path/one.xml",
            snapshot_path=None,
            source_url=None,
            sha256_hex="a" * 64,
            byte_length=10,
            parser_method="structured_xml",
            attempted_at_utc=base_time,
            status="failed",
            failure_type="parse",
            error_message="parse error",
            fallback_reason="structured_xml_exception",
            decision_state="needs_review",
            selected_candidate=False,
        )
    )
    repo.append(
        ParseRouteLog(
            id="id-2",
            run_id="run-1",
            route_type="owner",
            filing_id="filing-1",
            accession_no="0000320193-24-000012",
            cik="0000320193",
            document_id="doc-2",
            document_type="4",
            document_filename="ownership2.xml",
            document_path="raw/path/two.xml",
            snapshot_path=None,
            source_url=None,
            sha256_hex="b" * 64,
            byte_length=20,
            parser_method="deterministic_rule",
            attempted_at_utc=base_time + timedelta(minutes=1),
            status="success",
            failure_type=None,
            error_message=None,
            fallback_reason=None,
            decision_state="accepted",
            selected_candidate=True,
        )
    )
    session.commit()

    rows = repo.query(
        document_type="4",
        start_utc=base_time - timedelta(minutes=1),
        end_utc=base_time + timedelta(minutes=2),
        failure_type="parse",
        limit=10,
        offset=0,
    )

    assert [row.id for row in rows] == ["id-1"]


def test_sqlalchemy_timeline_orders_by_attempted_at_then_id() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    repo = ParseRouteLogRepository(session)
    base_time = datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc)

    session.add_all(
        [
            ParseRouteLog(
                id="c",
                run_id="run-1",
                route_type="owner",
                filing_id="filing-1",
                accession_no="0000320193-24-000012",
                cik="0000320193",
                document_id="doc-1",
                document_type="4",
                document_filename="c.xml",
                document_path="raw/c.xml",
                snapshot_path=None,
                source_url=None,
                sha256_hex="c" * 64,
                byte_length=10,
                parser_method="structured_xml",
                attempted_at_utc=base_time,
                status="failed",
                failure_type="logic",
                error_message="logic",
                fallback_reason="structured_xml_missing_mandatory",
                decision_state="needs_review",
                selected_candidate=False,
            ),
            ParseRouteLog(
                id="a",
                run_id="run-1",
                route_type="owner",
                filing_id="filing-1",
                accession_no="0000320193-24-000012",
                cik="0000320193",
                document_id="doc-1",
                document_type="4",
                document_filename="a.xml",
                document_path="raw/a.xml",
                snapshot_path=None,
                source_url=None,
                sha256_hex="a" * 64,
                byte_length=10,
                parser_method="structured_xml",
                attempted_at_utc=base_time,
                status="failed",
                failure_type="logic",
                error_message="logic",
                fallback_reason="structured_xml_missing_mandatory",
                decision_state="needs_review",
                selected_candidate=False,
            ),
            ParseRouteLog(
                id="b",
                run_id="run-1",
                route_type="owner",
                filing_id="filing-1",
                accession_no="0000320193-24-000012",
                cik="0000320193",
                document_id="doc-1",
                document_type="4",
                document_filename="b.xml",
                document_path="raw/b.xml",
                snapshot_path=None,
                source_url=None,
                sha256_hex="b" * 64,
                byte_length=10,
                parser_method="deterministic_rule",
                attempted_at_utc=base_time + timedelta(minutes=1),
                status="success",
                failure_type=None,
                error_message=None,
                fallback_reason=None,
                decision_state="needs_review",
                selected_candidate=True,
            ),
        ]
    )
    session.commit()

    rows = repo.timeline(
        accession_no="0000320193-24-000012",
        document_id="doc-1",
    )

    assert [row.id for row in rows] == ["a", "c", "b"]
