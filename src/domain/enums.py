from dataclasses import dataclass
from enum import Enum


class RouteType(str, Enum):
    ISSUER = "issuer"
    OWNER = "owner"
    HOLDINGS = "holdings"


class ParserMethod(str, Enum):
    STRUCTURED_XML = "structured_xml"
    DETERMINISTIC_RULE = "deterministic_rule"


class ParseAttemptStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class ParseFailureType(str, Enum):
    NETWORK = "network"
    PARSE = "parse"
    LOGIC = "logic"


class FallbackReason(str, Enum):
    STRUCTURED_XML_EXCEPTION = "structured_xml_exception"
    STRUCTURED_XML_MISSING_MANDATORY = "structured_xml_missing_mandatory"
    STRUCTURED_XML_NUMERIC_INVALID = "structured_xml_numeric_invalid"
    STRUCTURED_XML_EMPTY_VALUE = "structured_xml_empty_value"
    DETERMINISTIC_RULE_EXCEPTION = "deterministic_rule_exception"
    DETERMINISTIC_RULE_NOT_APPLICABLE = "deterministic_rule_not_applicable"
    ALL_METHODS_FAILED = "all_methods_failed"


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
