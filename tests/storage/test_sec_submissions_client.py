import pytest

from src.core.config import settings
import src.storage.sec_submissions_client as sec_submissions_client_module
from src.storage.sec_submissions_client import SecSubmissionsClient


class _RecorderSecClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.urls: list[str] = []

    def get_json(self, url: str) -> dict:
        self.urls.append(url)
        return self.payload


def test_fetch_company_submissions_zero_pads_cik_and_uses_sec_client() -> None:
    recorder = _RecorderSecClient(payload={"filings": {"recent": {}}})
    client = SecSubmissionsClient(sec_client=recorder)

    payload = client.fetch_company_submissions(cik="320193")

    assert payload == {"filings": {"recent": {}}}
    assert recorder.urls == ["https://data.sec.gov/submissions/CIK0000320193.json"]


def test_fetch_company_submissions_uses_project_default_user_agent() -> None:
    constructor_calls: list[tuple[str | None]] = []

    class _CtorRecorderSecClient:
        def __init__(self, user_agent: str | None = None) -> None:
            constructor_calls.append((user_agent,))

        def get_json(self, url: str) -> dict:
            return {"url": url}

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        sec_submissions_client_module,
        "SecClient",
        _CtorRecorderSecClient,
    )
    try:
        client = SecSubmissionsClient()
        client.fetch_company_submissions(cik="0000320193")
    finally:
        monkeypatch.undo()

    assert constructor_calls == [(settings.SEC_API_USER_AGENT,)]


def test_fetch_company_submissions_maps_oserror() -> None:
    class _RaisingSecClient:
        def get_json(self, _url: str) -> dict:
            raise OSError("temporary DNS failure")

    client = SecSubmissionsClient(sec_client=_RaisingSecClient())

    with pytest.raises(RuntimeError, match="submissions download failure"):
        client.fetch_company_submissions(cik="0000320193")
