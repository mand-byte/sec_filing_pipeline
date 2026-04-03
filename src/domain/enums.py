from dataclasses import dataclass
from enum import Enum


class RouteType(str, Enum):
    ISSUER = "ISSUER"
    OWNER = "OWNER"
    HOLDINGS = "HOLDINGS"


class ParserMethod(str, Enum):
    XML = "XML"
    HTML = "HTML"
    TEXT = "TEXT"


class DecisionState(str, Enum):
    AUTO = "AUTO"
    REVIEW = "REVIEW"


class ReviewReason(str, Enum):
    UNSUPPORTED_FORM = "UNSUPPORTED_FORM"
    PARSE_ERROR = "PARSE_ERROR"
    MISSING_EVENT_TIME = "MISSING_EVENT_TIME"


@dataclass(frozen=True, slots=True)
class CanonicalForm:
    raw: str
    base: str
    is_amendment: bool
