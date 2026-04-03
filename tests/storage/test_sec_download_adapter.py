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
    def __init__(self, attachments: list[_FakeAttachment]) -> None:
        self.attachments = attachments


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
