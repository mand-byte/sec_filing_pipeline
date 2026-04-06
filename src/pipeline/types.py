from dataclasses import dataclass
from datetime import datetime
from typing import Literal


RouteName = Literal["issuer", "owner", "holding"]


@dataclass(slots=True, frozen=True)
class FilingRecord:
    composite_figi: str
    cik: str
    ticker: str | None
    accession_no: str
    route: RouteName
    accepted_at: datetime
    active: bool
    delisted_utc: datetime | None
