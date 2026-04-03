from hashlib import sha1

from src.domain.enums import DecisionState, ReviewReason
from src.models.filing import ExtractedFact
from src.models.review import ReviewQueueItem
from src.parsers.ownership_xml import ParsedOwnershipFact


def _fact_id(accession_no: str, fact_name: str, snippet_locator: str) -> str:
    return sha1(
        f"{accession_no}:{fact_name}:{snippet_locator}".encode("utf-8")
    ).hexdigest()


def build_fact_row(
    filing_id: str,
    accession_no: str,
    parsed_fact: ParsedOwnershipFact,
) -> ExtractedFact:
    is_complete = bool(parsed_fact.validation_results.get("mandatory_present", True))
    is_numeric_ok = parsed_fact.validation_results.get("is_numeric", True)
    accepted = is_complete and is_numeric_ok

    return ExtractedFact(
        fact_id=_fact_id(
            accession_no, parsed_fact.fact_name, parsed_fact.snippet_locator
        ),
        filing_id=filing_id,
        accession_no=accession_no,
        fact_name=parsed_fact.fact_name,
        fact_value=parsed_fact.fact_value,
        parser_method=parsed_fact.parser_method,
        confidence_score=0.99 if accepted else 0.30,
        confidence_bucket="high" if accepted else "low",
        decision_state=(
            DecisionState.ACCEPTED.value
            if accepted
            else DecisionState.NEEDS_REVIEW.value
        ),
        snippet_text=parsed_fact.snippet_text,
        snippet_locator=parsed_fact.snippet_locator,
        document_filename=parsed_fact.document_filename,
        validation_results=parsed_fact.validation_results,
        attempted_methods=[parsed_fact.parser_method],
    )


def build_review_item(
    accession_no: str, parsed_fact: ParsedOwnershipFact
) -> ReviewQueueItem:
    return ReviewQueueItem(
        review_item_id=_fact_id(
            accession_no, parsed_fact.fact_name, parsed_fact.snippet_locator
        ),
        accession_no=accession_no,
        fact_id=None,
        review_reason=ReviewReason.MANDATORY_FIELD_MISSING.value,
        payload={
            "fact_name": parsed_fact.fact_name,
            "snippet_locator": parsed_fact.snippet_locator,
            "validation_results": parsed_fact.validation_results,
        },
        status="open",
        note=None,
    )
