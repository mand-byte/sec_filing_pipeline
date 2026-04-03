import json
import time
from urllib.request import Request, urlopen

from src.core.config import settings


class SecClient:
    def __init__(
        self,
        user_agent: str | None = None,
        rate_limit_per_second: float | None = None,
    ) -> None:
        self.user_agent = user_agent or settings.SEC_API_USER_AGENT
        self.rate_limit_per_second = (
            rate_limit_per_second or settings.SEC_RATE_LIMIT_PER_SECOND
        )
        self._last_request_monotonic = 0.0

    def get_json(self, url: str) -> dict:
        delay_seconds = 1 / self.rate_limit_per_second
        elapsed_seconds = time.monotonic() - self._last_request_monotonic
        if elapsed_seconds < delay_seconds:
            time.sleep(delay_seconds - elapsed_seconds)

        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
            },
        )
        with urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))

        self._last_request_monotonic = time.monotonic()
        return payload
