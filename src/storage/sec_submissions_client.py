from src.core.config import settings
from src.storage.sec_client import SecClient

_DATA_SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"


class SecSubmissionsClient:
    def __init__(
        self,
        user_agent: str | None = None,
        sec_client: SecClient | None = None,
    ) -> None:
        self._sec_client = sec_client or SecClient(
            user_agent=user_agent or settings.SEC_API_USER_AGENT
        )

    def fetch_company_submissions(self, cik: str) -> dict:
        normalized_cik = str(cik).strip().zfill(10)
        url = _DATA_SEC_SUBMISSIONS_URL.format(cik=normalized_cik)

        try:
            return self._sec_client.get_json(url)
        except OSError as exc:
            raise RuntimeError("submissions download failure") from exc
