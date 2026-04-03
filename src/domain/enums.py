from dataclasses import dataclass
from enum import Enum


class RouteType(str, Enum):
    ISSUER = "issuer"
    OWNER = "owner"
    HOLDINGS = "holdings"


class ParserMethod(str, Enum):
    STRUCTURED_XML = "structured_xml"
    DETERMINISTIC_RULE = "deterministic_rule"


class DecisionState(str, Enum):
    ACCEPTED = "accepted"
    ACCEPTED_WITH_WARNING = "accepted_with_warning"
    NEEDS_REVIEW = "needs_review"
    DROPPED = "dropped"


class ReviewReason(str, Enum):
    MANDATORY_FIELD_MISSING = "mandatory_field_missing"
    SOURCE_CONFLICT = "source_conflict"
    AMENDMENT_CONFLICT = "amendment_conflict"


@dataclass(frozen=True, slots=True)
class CanonicalForm:
    form_type_raw: str
    form_type_base: str
    is_amendment: bool
