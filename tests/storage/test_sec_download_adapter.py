from datetime import datetime, timezone

import pytest

from src.storage.sec_download_adapter import (
    DownloadedAttachment,
    DownloadedFilingBundle,
    SecDownloadAdapter,
)


class _FakeAttachment:
    def __init__(self, filename: str, content_type: str, content: bytes) -> None:
        self.filename = filename
        self.content_type = content_type
        self.content = content


class _FakeFiling:
    def __init__(
        self,
        attachments: list[_FakeAttachment],
        *,
        form: str = "4",
        acceptance_datetime: datetime | str = datetime(
            2024, 4, 3, 12, 30, tzinfo=timezone.utc
        ),
        primary_document: str = "ownership.xml",
    ) -> None:
        self.attachments = attachments
        self.form = form
        self.acceptance_datetime = acceptance_datetime
        self.primary_document = primary_document


class _FakeDownloader:
    def __init__(
        self, filing: _FakeFiling | None = None, error: Exception | None = None
    ) -> None:
        self._filing = filing
        self._error = error

    def download_owner_filing(self, cik: str, accession_no: str) -> _FakeFiling:
        if self._error is not None:
            raise self._error
        assert self._filing is not None
        return self._filing


def test_download_owner_filing_bundle_returns_all_typed_attachments() -> None:
    filing = _FakeFiling(
        attachments=[
            _FakeAttachment("ownership.xml", "text/xml", b"<xml/>"),
            _FakeAttachment("index.json", "application/json", b"{}"),
        ]
    )
    adapter = SecDownloadAdapter(sec_downloader=_FakeDownloader(filing=filing))

    bundle = adapter.download_owner_filing_bundle(
        cik="0000320193",
        accession_no="0000320193-24-000012",
    )

    assert isinstance(bundle, DownloadedFilingBundle)
    assert bundle.cik == "0000320193"
    assert bundle.accession_no == "0000320193-24-000012"
    assert bundle.form_type_raw == "4"
    assert bundle.acceptance_datetime_utc == datetime(
        2024, 4, 3, 12, 30, tzinfo=timezone.utc
    )
    assert bundle.primary_document == "ownership.xml"
    assert bundle.attachments == [
        DownloadedAttachment(
            filename="ownership.xml",
            content_type="text/xml",
            content=b"<xml/>",
        ),
        DownloadedAttachment(
            filename="index.json",
            content_type="application/json",
            content=b"{}",
        ),
    ]


@pytest.mark.parametrize(
    "error",
    [
        OSError("temporary DNS failure"),
        type("NetworkFailure", (Exception,), {})("service unavailable"),
    ],
)
def test_download_owner_filing_bundle_maps_network_errors_to_runtime_error(
    error: Exception,
) -> None:
    adapter = SecDownloadAdapter(sec_downloader=_FakeDownloader(error=error))

    with pytest.raises(RuntimeError, match="network"):
        adapter.download_owner_filing_bundle(
            cik="0000320193",
            accession_no="0000320193-24-000012",
        )


def test_download_owner_filing_bundle_parses_string_acceptance_datetime() -> None:
    filing = _FakeFiling(
        attachments=[_FakeAttachment("ownership.xml", "text/xml", b"<xml/>")],
        form="4/A",
        acceptance_datetime="2024-04-03T12:30:00Z",
        primary_document="ownership.xml",
    )
    adapter = SecDownloadAdapter(sec_downloader=_FakeDownloader(filing=filing))

    bundle = adapter.download_owner_filing_bundle(
        cik="0000320193",
        accession_no="0000320193-24-000012",
    )

    assert bundle.form_type_raw == "4/A"
    assert bundle.acceptance_datetime_utc == datetime(
        2024, 4, 3, 12, 30, tzinfo=timezone.utc
    )


def test_download_owner_filing_bundle_requires_metadata_fields() -> None:
    class _MissingMetadataFiling:
        attachments = []

    adapter = SecDownloadAdapter(
        sec_downloader=_FakeDownloader(filing=_MissingMetadataFiling())
    )

    with pytest.raises(ValueError, match="form_type_raw"):
        adapter.download_owner_filing_bundle(
            cik="0000320193",
            accession_no="0000320193-24-000012",
        )
