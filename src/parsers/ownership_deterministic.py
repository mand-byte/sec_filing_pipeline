import re

from src.domain.enums import ParserMethod
from src.parsers.ownership_xml import ParsedOwnershipFact, ParsedOwnershipSubmission


def _extract_line(pattern: str, source_text: str) -> tuple[str, str, str] | None:
    match = re.search(pattern, source_text, flags=re.IGNORECASE | re.MULTILINE)
    if match is None:
        return None
    value = match.group(1).strip()
    snippet_text = match.group(0).strip()
    snippet_locator = f"regex:{pattern}"
    return value, snippet_text, snippet_locator


def parse_ownership_deterministic(
    accession_no: str,
    document_filename: str,
    source_text: str,
) -> ParsedOwnershipSubmission:
    extracted = {
        "issuer_cik": _extract_line(
            r"^\s*Issuer\s+CIK\s*:\s*([0-9]+)\s*$", source_text
        ),
        "reporting_owner_cik": _extract_line(
            r"^\s*Reporting\s+Owner\s+CIK\s*:\s*([0-9]+)\s*$", source_text
        ),
        "transaction_shares": _extract_line(
            r"^\s*Transaction\s+Shares\s*:\s*([^\n\r]+)\s*$", source_text
        ),
    }

    if all(value is None for value in extracted.values()):
        raise ValueError("deterministic parser not applicable")

    facts: list[ParsedOwnershipFact] = []
    for fact_name, value in extracted.items():
        fact_value = ""
        snippet_text = ""
        snippet_locator = ""
        if value is not None:
            fact_value, snippet_text, snippet_locator = value

        validation_results = {"mandatory_present": bool(fact_value)}
        if fact_name == "transaction_shares":
            validation_results["is_numeric"] = fact_value.isdigit()

        facts.append(
            ParsedOwnershipFact(
                fact_name=fact_name,
                fact_value=fact_value,
                parser_method=ParserMethod.DETERMINISTIC_RULE.value,
                snippet_text=snippet_text,
                snippet_locator=snippet_locator,
                document_filename=document_filename,
                validation_results=validation_results,
            )
        )

    return ParsedOwnershipSubmission(
        accession_no=accession_no,
        document_filename=document_filename,
        facts=facts,
    )
