from dataclasses import dataclass
from datetime import datetime, timezone
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
    form_type_raw: str
    acceptance_datetime_utc: datetime
    primary_document: str
    attachments: list[DownloadedAttachment]


class _OwnerFilingDownloader(Protocol):
    def download_owner_filing(self, cik: str, accession_no: str) -> Any: ...


class _EdgarToolsDownloader:
    def download_owner_filing(self, cik: str, accession_no: str) -> Any:
        from edgar import Filing

        return Filing.get(cik=cik, accession_number=accession_no).obj()


def _read_required_str_attr(filing: Any, names: tuple[str, ...], *, field: str) -> str:
    for name in names:
        value = getattr(filing, name, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError(f"downloaded filing missing required {field}")


def _coerce_acceptance_datetime_utc(value: Any) -> datetime:
    parsed: datetime | None = None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if parsed is None:
        raise ValueError("downloaded filing missing required acceptance_datetime_utc")

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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
            form_type_raw=_read_required_str_attr(
                filing,
                ("form", "form_type"),
                field="form_type_raw",
            ),
            acceptance_datetime_utc=_coerce_acceptance_datetime_utc(
                getattr(filing, "acceptance_datetime", None)
                or getattr(filing, "acceptance_datetime_utc", None)
            ),
            primary_document=_read_required_str_attr(
                filing,
                ("primary_document", "primaryDocument", "document"),
                field="primary_document",
            ),
            attachments=attachments,
        )
