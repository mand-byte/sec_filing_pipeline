from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from types import SimpleNamespace
import sys

from src.pipeline.edgar_provider import fetch_filings_for_security


class FakeCompany:
    def __init__(self, cik: str):
        self.cik = cik

    def get_filings(self, *, form: list[str]) -> list[object]:
        assert "10-Q" in form
        return [
            SimpleNamespace(
                accession_no="0000000000-24-000001",
                form="10-Q/A",
                acceptance_datetime="2024-05-02T10:00:00Z",
                filing_date="2024-05-01",
                period_of_report="2024-03-31",
                amendment_no="2",
            )
        ]


class RaisingCompany:
    def __init__(self, cik: str):
        self.cik = cik

    def get_filings(self, *, form: list[str]) -> list[object]:
        del form
        raise RuntimeError("identity missing")


def test_fetch_filings_for_security_populates_filing_metadata(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "edgar", SimpleNamespace(Company=FakeCompany))

    envelopes = fetch_filings_for_security(
        security=SimpleNamespace(cik="0000789019"),
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
    )

    assert len(envelopes) == 1
    envelope = envelopes[0]
    assert envelope.filed_at == datetime(2024, 5, 1, tzinfo=timezone.utc)
    assert envelope.period_end == datetime(2024, 3, 31, tzinfo=timezone.utc)
    assert envelope.amendment_no == 2


def test_fetch_filings_for_security_applies_identity_and_surfaces_provider_error(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_set_identity(identity: str) -> None:
        captured["identity"] = identity

    monkeypatch.setitem(
        sys.modules,
        "edgar",
        SimpleNamespace(Company=RaisingCompany, set_identity=fake_set_identity),
    )

    try:
        fetch_filings_for_security(
            security=SimpleNamespace(cik="0000789019"),
            route="issuer",
            start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
            identity="Example Ops ops@example.test",
        )
    except RuntimeError as exc:
        assert "edgar fetch failed" in str(exc)
        assert "identity missing" in str(exc)
    else:
        raise AssertionError("expected runtime provider error")

    assert captured["identity"] == "Example Ops ops@example.test"


class EndDateCompany:
    def __init__(self, cik: str):
        self.cik = cik

    def get_filings(self, *, form: list[str]) -> list[object]:
        assert "10-Q" in form
        return [
            SimpleNamespace(
                accession_no="0000000000-24-000010",
                form="10-Q",
                acceptance_datetime="2024-05-02T10:00:00Z",
            ),
            SimpleNamespace(
                accession_no="0000000000-24-000011",
                form="10-Q",
                acceptance_datetime="2024-05-03T10:00:00Z",
            ),
        ]


def test_fetch_filings_for_security_respects_optional_end_accepted_at(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "edgar", SimpleNamespace(Company=EndDateCompany))

    envelopes = fetch_filings_for_security(
        security=SimpleNamespace(cik="0000789019"),
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        end_accepted_at=datetime(2024, 5, 2, 23, 59, 59, tzinfo=timezone.utc),
    )

    assert [envelope.accession_no for envelope in envelopes] == ["0000000000-24-000010"]


class ExpensiveMetadataFiling:
    accession_no = "0000000000-24-000020"
    form = "10-Q"
    acceptance_datetime = "2024-05-02T10:00:00Z"
    filing_date = "2024-05-01"
    amendment_no = "2"

    @property
    def period_of_report(self):
        raise RuntimeError("network timeout")


class ExpensiveMetadataCompany:
    def __init__(self, cik: str):
        self.cik = cik

    def get_filings(self, *, form: list[str]) -> list[object]:
        assert "10-Q" in form
        return [ExpensiveMetadataFiling()]


def test_fetch_filings_for_security_tolerates_expensive_period_metadata(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "edgar", SimpleNamespace(Company=ExpensiveMetadataCompany))

    envelopes = fetch_filings_for_security(
        security=SimpleNamespace(cik="0000789019"),
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
    )

    assert len(envelopes) == 1
    assert envelopes[0].period_end is None
    assert envelopes[0].amendment_no == 2


def test_fetch_filings_for_security_can_enable_local_filing_download(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    class LocalDownloadCompany:
        def __init__(self, cik: str):
            self.cik = cik

        def get_filings(self, *, form: list[str]) -> object:
            assert "10-Q" in form
            class LocalFiling(SimpleNamespace):
                def full_text_submission(self_nonlocal) -> str:
                    captured.setdefault("downloaded_accessions", []).append(self_nonlocal.accession_no)
                    return f"FULL {self_nonlocal.accession_no}"

            return [
                LocalFiling(
                    accession_no="0000000000-95-000999",
                    form="10-Q",
                    acceptance_datetime="1995-09-15T08:03:38Z",
                    filing_date="1995-09-08",
                ),
                LocalFiling(
                    accession_no="0000000000-24-000001",
                    form="10-Q/A",
                    acceptance_datetime="2024-05-02T10:00:00Z",
                    filing_date="2024-05-01",
                    period_of_report="2024-03-31",
                    amendment_no="2",
                ),
            ]

    def fake_use_local_storage(path: str) -> None:
        captured["use_local_storage"] = path

    fake_edgar_module = SimpleNamespace(
        Company=LocalDownloadCompany,
        use_local_storage=fake_use_local_storage,
    )
    monkeypatch.setitem(sys.modules, "edgar", fake_edgar_module)

    local_dir = tmp_path / "edgar_local"
    envelopes = fetch_filings_for_security(
        security=SimpleNamespace(cik="0000789019"),
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        download_filings_to_local=True,
        local_data_dir=local_dir,
    )

    assert len(envelopes) == 1
    assert os.environ["EDGAR_USE_LOCAL_DATA"] == "1"
    assert os.environ["EDGAR_LOCAL_DATA_DIR"] == str(local_dir.resolve())
    assert captured["use_local_storage"] == str(local_dir.resolve())
    assert captured["downloaded_accessions"] == ["0000000000-24-000001"]
    assert (local_dir / "filings" / "20240501" / "0000000000-24-000001.nc").exists()
    assert not (local_dir / "filings" / "19950915" / "0000000000-95-000999.corr01").exists()


def test_fetch_filings_for_security_can_write_via_cloud_storage(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}
    remote_store: dict[str, str] = {}

    class CloudFiling(SimpleNamespace):
        def full_text_submission(self_nonlocal) -> str:
            captured.setdefault("downloaded_accessions", []).append(self_nonlocal.accession_no)
            return f"REMOTE {self_nonlocal.accession_no}"

    class CloudCompany:
        def __init__(self, cik: str):
            self.cik = cik

        def get_filings(self, *, form: list[str]) -> object:
            assert "10-Q" in form
            return [
                CloudFiling(
                    accession_no="0000000000-24-000030",
                    form="10-Q",
                    acceptance_datetime="2024-05-04T10:00:00Z",
                    filing_date="2024-05-03",
                )
            ]

    class FakeCloudPath:
        def __init__(self, *parts: str):
            self.key = "/".join(str(part).strip("/") for part in parts if str(part).strip("/"))

        def exists(self) -> bool:
            return self.key in remote_store

        def write_text(self, data: str, encoding: str = "utf-8") -> int:
            del encoding
            remote_store[self.key] = data
            return len(data)

    def fake_use_local_storage(path: str) -> None:
        captured["use_local_storage"] = path

    def fake_use_cloud_storage(uri: str, *, client_kwargs=None, verify=True) -> None:
        captured["use_cloud_storage"] = {
            "uri": uri,
            "client_kwargs": client_kwargs,
            "verify": verify,
        }

    fake_edgar_module = SimpleNamespace(
        Company=CloudCompany,
        use_local_storage=fake_use_local_storage,
        use_cloud_storage=fake_use_cloud_storage,
    )
    monkeypatch.setitem(sys.modules, "edgar", fake_edgar_module)
    monkeypatch.setitem(sys.modules, "edgar.filesystem", SimpleNamespace(EdgarPath=FakeCloudPath))

    local_dir = tmp_path / "edgar_local"
    envelopes = fetch_filings_for_security(
        security=SimpleNamespace(cik="0000789019"),
        route="issuer",
        start_accepted_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        download_filings_to_local=True,
        local_data_dir=local_dir,
        use_cloud_storage=True,
        cloud_uri="s3://sec-filing/",
        cloud_endpoint_url="http://192.168.1.2:10017",
        cloud_access_id="hubber",
        cloud_access_key="by1t7grk",
    )

    assert len(envelopes) == 1
    assert captured["downloaded_accessions"] == ["0000000000-24-000030"]
    assert captured["use_cloud_storage"] == {
        "uri": "s3://sec-filing/",
        "client_kwargs": {
            "endpoint_url": "http://192.168.1.2:10017",
            "aws_access_key_id": "hubber",
            "aws_secret_access_key": "by1t7grk",
        },
        "verify": False,
    }
    assert remote_store["filings/20240503/0000000000-24-000030.nc"] == "REMOTE 0000000000-24-000030"
