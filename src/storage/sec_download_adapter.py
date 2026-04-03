from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class DownloadedAttachment:
    filename: str
    content_type: str
    content: bytes


@dataclass(frozen=True, slots=True)
class DownloadedFilingBundle:
    cik: str
    accession_no: str
    attachments: list[DownloadedAttachment]


class _OwnerFilingDownloader(Protocol):
    def download_owner_filing(self, cik: str, accession_no: str) -> Any: ...


class _EdgarToolsDownloader:
    def download_owner_filing(self, cik: str, accession_no: str) -> Any:
        from edgar import Filing

        return Filing.get(cik=cik, accession_number=accession_no).obj()


class SecDownloadAdapter:
    def __init__(self, sec_downloader: _OwnerFilingDownloader | None = None) -> None:
        self._sec_downloader = sec_downloader or _EdgarToolsDownloader()

    def download_owner_filing_bundle(
        self,
        cik: str,
        accession_no: str,
    ) -> DownloadedFilingBundle:
        try:
            filing = self._sec_downloader.download_owner_filing(cik, accession_no)
        except Exception as exc:
            if isinstance(exc, OSError) or "network" in exc.__class__.__name__.lower():
                raise RuntimeError("network download failure") from exc
            raise

        attachments = [
            DownloadedAttachment(
                filename=attachment.filename,
                content_type=attachment.content_type,
                content=attachment.content,
            )
            for attachment in filing.attachments
        ]

        return DownloadedFilingBundle(
            cik=cik,
            accession_no=accession_no,
            attachments=attachments,
        )
