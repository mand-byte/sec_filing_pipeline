from dataclasses import dataclass
from datetime import datetime
from typing import Literal


RouteName = Literal["issuer", "owner", "holding"]


@dataclass(slots=True, frozen=True)
class FilingRecord:
    accession_no: str
    cik: str
    ticker: str | None
    form_type: str
    filed_at: datetime | None
    accepted_at: datetime
    period_end: datetime | None
    is_amendment: bool
    amendment_no: int | None
