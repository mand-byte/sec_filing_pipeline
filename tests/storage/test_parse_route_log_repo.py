from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

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
