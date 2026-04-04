from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.models.base import Base
from src.models.state import IngestionState
from src.storage.ingestion_state_repo import IngestionStateRepository


class _FakeSession:
    def __init__(self) -> None:
        self.ingestion_states: list[IngestionState] = []


def test_get_or_create_returns_existing_row() -> None:
    session = _FakeSession()
    repo = IngestionStateRepository(session)

    existing_state = IngestionState(cik="0000320193", route_type="owner")
    session.ingestion_states.append(existing_state)

    result = repo.get_or_create("0000320193", "owner")

    assert result is existing_state


def test_get_or_create_creates_new_row_when_not_found() -> None:
    session = _FakeSession()
    repo = IngestionStateRepository(session)

    result = repo.get_or_create("0000320193", "owner")

    assert result.cik == "0000320193"
    assert result.route_type == "owner"
    assert result in session.ingestion_states


def test_advance_updates_state_with_newer_acceptance() -> None:
    session = _FakeSession()
    repo = IngestionStateRepository(session)

    state = IngestionState(cik="0000320193", route_type="owner")
    session.ingestion_states.append(state)

    base_time = datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc)
    later_time = datetime(2024, 4, 3, 14, 0, tzinfo=timezone.utc)

    result = repo.advance(state, "0000320193-24-000001", base_time)
    assert result.last_accession_no == "0000320193-24-000001"
    assert result.last_acceptance_datetime_utc == base_time

    result = repo.advance(state, "0000320193-24-000002", later_time)
    assert result.last_accession_no == "0000320193-24-000002"
    assert result.last_acceptance_datetime_utc == later_time


def test_advance_does_not_update_with_older_acceptance() -> None:
    session = _FakeSession()
    repo = IngestionStateRepository(session)

    state = IngestionState(cik="0000320193", route_type="owner")
    session.ingestion_states.append(state)

    base_time = datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc)
    later_time = datetime(2024, 4, 3, 14, 0, tzinfo=timezone.utc)

    repo.advance(state, "0000320193-24-000002", later_time)
    result = repo.advance(state, "0000320193-24-000001", base_time)

    assert result.last_accession_no == "0000320193-24-000002"
    assert result.last_acceptance_datetime_utc == later_time


def test_advance_updates_state_for_equal_acceptance_with_higher_accession() -> None:
    session = _FakeSession()
    repo = IngestionStateRepository(session)

    state = IngestionState(cik="0000320193", route_type="owner")
    session.ingestion_states.append(state)

    acceptance_time = datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc)

    repo.advance(state, "0000320193-24-000001", acceptance_time)
    result = repo.advance(state, "0000320193-24-000002", acceptance_time)

    assert result.last_accession_no == "0000320193-24-000002"
    assert result.last_acceptance_datetime_utc == acceptance_time


def test_sqlalchemy_get_or_create_is_idempotent_before_commit() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, future=True)()
    repo = IngestionStateRepository(session)

    state1 = repo.get_or_create("0000320193", "owner")
    state2 = repo.get_or_create("0000320193", "owner")

    assert state1 is state2
    assert len(session.new) == 1

    session.commit()

    states = session.execute(select(IngestionState)).scalars().all()
    assert len(states) == 1
    assert states[0].cik == "0000320193"
    assert states[0].route_type == "owner"


def test_sqlalchemy_get_or_create_persists_and_retrieves() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    repo = IngestionStateRepository(session)

    state1 = repo.get_or_create("0000320193", "owner")
    session.commit()

    state2 = repo.get_or_create("0000320193", "owner")
    session.commit()

    assert state1 is state2
    assert state1.cik == "0000320193"
    assert state1.route_type == "owner"


def test_sqlalchemy_advance_updates_row() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    repo = IngestionStateRepository(session)

    state = repo.get_or_create("0000320193", "owner")
    session.commit()

    base_time = datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc)

    repo.advance(state, "0000320193-24-000001", base_time)
    session.commit()

    from src.models.state import IngestionState

    reloaded = session.execute(
        select(IngestionState).where(
            IngestionState.cik == "0000320193", IngestionState.route_type == "owner"
        )
    ).scalar_one()

    assert reloaded.last_accession_no == "0000320193-24-000001"
    assert reloaded.last_acceptance_datetime_utc is not None
    assert reloaded.last_acceptance_datetime_utc.replace(tzinfo=None) == base_time.replace(tzinfo=None)


def test_advance_after_persist_and_reload_with_aware_datetime() -> None:
    """Regression test: advance() must handle naive datetimes from SQLite reload.

    When state is persisted and reloaded, last_acceptance_datetime_utc may come back
    as a naive datetime (no timezone). Callers pass UTC-aware datetimes. This test
    ensures the comparison does not raise TypeError.
    """
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    repo = IngestionStateRepository(session)

    state = repo.get_or_create("0000320193", "owner")
    session.commit()

    # First advance with aware datetime
    base_time = datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc)
    repo.advance(state, "0000320193-24-000001", base_time)
    session.commit()

    # Expire all to force reload from DB (simulating fresh session)
    session.expire_all()

    # Retrieve and advance again with aware datetime - this must not raise TypeError
    from src.models.state import IngestionState

    reloaded = session.execute(
        select(IngestionState).where(
            IngestionState.cik == "0000320193", IngestionState.route_type == "owner"
        )
    ).scalar_one()

    later_time = datetime(2024, 4, 3, 14, 0, tzinfo=timezone.utc)
    # This should not raise TypeError: can't compare offset-naive and offset-aware datetimes
    result = repo.advance(reloaded, "0000320193-24-000002", later_time)

    assert result.last_accession_no == "0000320193-24-000002"
    assert result.last_acceptance_datetime_utc == later_time