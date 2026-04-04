from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.base import Base
from src.models.filing import FilingDocument, FilingIndex
from src.storage.filing_repo import FilingRepository


@dataclass(frozen=True)
class _GetCall:
    model_cls: type[object]
    identifier: str


class _FakeSession:
    def __init__(self) -> None:
        self.filing_indexes: list[FilingIndex] = []
        self.filing_documents: list[FilingDocument] = []
        self._new: list[FilingIndex | FilingDocument] = []
        self.get_calls: list[_GetCall] = []
        self.add_calls: list[object] = []

    @property
    def new(self) -> list[FilingIndex | FilingDocument]:
        """Model SQLAlchemy's session.new for pending rows."""
        return self._new

    def get(
        self, model_cls: type[object], identifier: str
    ) -> FilingIndex | FilingDocument | None:
        self.get_calls.append(_GetCall(model_cls=model_cls, identifier=identifier))

        if model_cls is FilingIndex:
            rows = self.filing_indexes
            id_attr = "filing_id"
        elif model_cls is FilingDocument:
            rows = self.filing_documents
            id_attr = "document_id"
        else:
            raise AssertionError(f"unexpected model class: {model_cls}")

        for row in rows:
            if getattr(row, id_attr) == identifier:
                return row
        return None

    def add(self, row: FilingIndex | FilingDocument) -> None:
        self.add_calls.append(row)
        self._new.append(row)

        if isinstance(row, FilingIndex):
            self.filing_indexes.append(row)
            return
        if isinstance(row, FilingDocument):
            self.filing_documents.append(row)
            return
        raise AssertionError(f"unexpected row type: {type(row)}")


def test_add_filing_index_if_missing_idempotent_uses_get() -> None:
    session = _FakeSession()
    repo = FilingRepository(session)

    row = FilingIndex(
        filing_id="owner:0000320193:0000320193-24-000001",
        cik="0000320193",
        accession_no="0000320193-24-000001",
        form_type_raw="4",
        form_type_base="4",
        is_amendment=False,
        route_type="owner",
        acceptance_datetime_utc=datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc),
        filing_date=datetime(2024, 4, 3).date(),
        primary_document="ownership.xml",
        amendment_group_key="owner:0000320193:0000320193-24-000001",
        amendment_sequence=0,
    )

    repo.add_filing_index_if_missing(row)
    repo.add_filing_index_if_missing(row)

    assert len(session.filing_indexes) == 1
    # First call: get() checks db, returns None -> add row
    # Second call: _pending_row() finds row in session.new -> returns early, no get() call
    assert len(session.get_calls) == 1
    assert session.get_calls[0].model_cls is FilingIndex
    assert session.get_calls[0].identifier == row.filing_id
    assert len(session.add_calls) == 1
    assert session.add_calls[0] is row


def test_add_document_if_missing_idempotent_uses_get() -> None:
    session = _FakeSession()
    repo = FilingRepository(session)

    row = FilingDocument(
        document_id="doc-123",
        filing_id="owner:0000320193:0000320193-24-000001",
        accession_no="0000320193-24-000001",
        filename="ownership.xml",
        content_type="text/xml",
        sha256_hex="a" * 64,
        byte_length=1000,
        raw_path="/raw/path.xml",
        decoded_text_path=None,
        parser_snapshot_path=None,
    )

    repo.add_document_if_missing(row)
    repo.add_document_if_missing(row)

    assert len(session.filing_documents) == 1
    # First call: get() checks db, returns None -> add row
    # Second call: _pending_row() finds row in session.new -> returns early, no get() call
    assert len(session.get_calls) == 1
    assert session.get_calls[0].model_cls is FilingDocument
    assert session.get_calls[0].identifier == row.document_id
    assert len(session.add_calls) == 1
    assert session.add_calls[0] is row


def test_add_filing_index_creates_row_when_not_exists() -> None:
    session = _FakeSession()
    repo = FilingRepository(session)

    row = FilingIndex(
        filing_id="owner:0000320193:0000320193-24-000001",
        cik="0000320193",
        accession_no="0000320193-24-000001",
        form_type_raw="4",
        form_type_base="4",
        is_amendment=False,
        route_type="owner",
        acceptance_datetime_utc=datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc),
        filing_date=datetime(2024, 4, 3).date(),
        primary_document="ownership.xml",
        amendment_group_key="owner:0000320193:0000320193-24-000001",
        amendment_sequence=0,
    )

    repo.add_filing_index_if_missing(row)

    assert session.filing_indexes[0].filing_id == "owner:0000320193:0000320193-24-000001"


def test_sqlalchemy_add_filing_index_is_idempotent_before_commit() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, future=True)()
    repo = FilingRepository(session)

    row = FilingIndex(
        filing_id="owner:0000320193:0000320193-24-000001",
        cik="0000320193",
        accession_no="0000320193-24-000001",
        form_type_raw="4",
        form_type_base="4",
        is_amendment=False,
        route_type="owner",
        acceptance_datetime_utc=datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc),
        filing_date=datetime(2024, 4, 3).date(),
        primary_document="ownership.xml",
        amendment_group_key="owner:0000320193:0000320193-24-000001",
        amendment_sequence=0,
    )
    row_duplicate = FilingIndex(
        filing_id="owner:0000320193:0000320193-24-000001",
        cik="0000320193",
        accession_no="0000320193-24-000001",
        form_type_raw="4",
        form_type_base="4",
        is_amendment=False,
        route_type="owner",
        acceptance_datetime_utc=datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc),
        filing_date=datetime(2024, 4, 3).date(),
        primary_document="ownership.xml",
        amendment_group_key="owner:0000320193:0000320193-24-000001",
        amendment_sequence=0,
    )

    repo.add_filing_index_if_missing(row)
    repo.add_filing_index_if_missing(row_duplicate)

    assert len(session.new) == 1

    session.commit()

    count = session.query(FilingIndex).count()
    assert count == 1


def test_sqlalchemy_add_filing_index_if_missing_persists() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    repo = FilingRepository(session)

    row = FilingIndex(
        filing_id="owner:0000320193:0000320193-24-000001",
        cik="0000320193",
        accession_no="0000320193-24-000001",
        form_type_raw="4",
        form_type_base="4",
        is_amendment=False,
        route_type="owner",
        acceptance_datetime_utc=datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc),
        filing_date=datetime(2024, 4, 3).date(),
        primary_document="ownership.xml",
        amendment_group_key="owner:0000320193:0000320193-24-000001",
        amendment_sequence=0,
    )

    repo.add_filing_index_if_missing(row)
    session.commit()

    reloaded = session.get(FilingIndex, "owner:0000320193:0000320193-24-000001")
    assert reloaded is not None
    assert reloaded.accession_no == "0000320193-24-000001"


def test_sqlalchemy_add_document_is_idempotent_before_commit() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, future=True)()
    repo = FilingRepository(session)

    row = FilingDocument(
        document_id="doc-123",
        filing_id="owner:0000320193:0000320193-24-000001",
        accession_no="0000320193-24-000001",
        filename="ownership.xml",
        content_type="text/xml",
        sha256_hex="a" * 64,
        byte_length=1000,
        raw_path="/raw/path.xml",
        decoded_text_path=None,
        parser_snapshot_path=None,
    )
    row_duplicate = FilingDocument(
        document_id="doc-123",
        filing_id="owner:0000320193:0000320193-24-000001",
        accession_no="0000320193-24-000001",
        filename="ownership2.xml",
        content_type="text/xml",
        sha256_hex="b" * 64,
        byte_length=2000,
        raw_path="/raw/path2.xml",
        decoded_text_path=None,
        parser_snapshot_path=None,
    )

    repo.add_document_if_missing(row)
    repo.add_document_if_missing(row_duplicate)

    assert len(session.new) == 1

    session.commit()

    count = session.query(FilingDocument).count()
    assert count == 1


def test_sqlalchemy_add_document_if_missing_persists() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    repo = FilingRepository(session)

    row = FilingDocument(
        document_id="doc-123",
        filing_id="owner:0000320193:0000320193-24-000001",
        accession_no="0000320193-24-000001",
        filename="ownership.xml",
        content_type="text/xml",
        sha256_hex="a" * 64,
        byte_length=1000,
        raw_path="/raw/path.xml",
        decoded_text_path=None,
        parser_snapshot_path=None,
    )

    repo.add_document_if_missing(row)
    session.commit()

    reloaded = session.get(FilingDocument, "doc-123")
    assert reloaded is not None
    assert reloaded.filename == "ownership.xml"


def test_sqlalchemy_add_filing_index_idempotent_uses_get() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    repo = FilingRepository(session)

    row = FilingIndex(
        filing_id="owner:0000320193:0000320193-24-000001",
        cik="0000320193",
        accession_no="0000320193-24-000001",
        form_type_raw="4",
        form_type_base="4",
        is_amendment=False,
        route_type="owner",
        acceptance_datetime_utc=datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc),
        filing_date=datetime(2024, 4, 3).date(),
        primary_document="ownership.xml",
        amendment_group_key="owner:0000320193:0000320193-24-000001",
        amendment_sequence=0,
    )

    repo.add_filing_index_if_missing(row)
    session.commit()

    row_duplicate = FilingIndex(
        filing_id="owner:0000320193:0000320193-24-000001",
        cik="0000320193",
        accession_no="0000320193-24-000001",
        form_type_raw="4",
        form_type_base="4",
        is_amendment=False,
        route_type="owner",
        acceptance_datetime_utc=datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc),
        filing_date=datetime(2024, 4, 3).date(),
        primary_document="ownership.xml",
        amendment_group_key="owner:0000320193:0000320193-24-000001",
        amendment_sequence=0,
    )

    repo.add_filing_index_if_missing(row_duplicate)
    session.commit()

    count = session.query(FilingIndex).count()
    assert count == 1


def test_sqlalchemy_add_document_idempotent_uses_get() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    repo = FilingRepository(session)

    row = FilingDocument(
        document_id="doc-123",
        filing_id="owner:0000320193:0000320193-24-000001",
        accession_no="0000320193-24-000001",
        filename="ownership.xml",
        content_type="text/xml",
        sha256_hex="a" * 64,
        byte_length=1000,
        raw_path="/raw/path.xml",
        decoded_text_path=None,
        parser_snapshot_path=None,
    )

    repo.add_document_if_missing(row)
    session.commit()

    row_duplicate = FilingDocument(
        document_id="doc-123",
        filing_id="owner:0000320193:0000320193-24-000001",
        accession_no="0000320193-24-000001",
        filename="ownership2.xml",
        content_type="text/xml",
        sha256_hex="b" * 64,
        byte_length=2000,
        raw_path="/raw/path2.xml",
        decoded_text_path=None,
        parser_snapshot_path=None,
    )

    repo.add_document_if_missing(row_duplicate)
    session.commit()

    count = session.query(FilingDocument).count()
    assert count == 1
    reloaded = session.get(FilingDocument, "doc-123")
    assert reloaded.filename == "ownership.xml"