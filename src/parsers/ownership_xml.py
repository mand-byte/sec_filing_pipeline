from dataclasses import dataclass

from lxml import etree

from src.domain.enums import ParserMethod


@dataclass(frozen=True)
class ParsedOwnershipFact:
    fact_name: str
    fact_value: str
    parser_method: str
    snippet_text: str
    snippet_locator: str
    document_filename: str
    validation_results: dict


@dataclass(frozen=True)
class ParsedOwnershipSubmission:
    accession_no: str
    document_filename: str
    facts: list[ParsedOwnershipFact]


def _first_text(root: etree._Element, xpath: str) -> str:
    values = root.xpath(xpath)
    if not values:
        return ""
    node = values[0]
    if isinstance(node, etree._Element):
        return (node.text or "").strip()
    return str(node).strip()


def parse_ownership_xml(
    accession_no: str,
    document_filename: str,
    xml_text: str,
) -> ParsedOwnershipSubmission:
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        recover=False,
        huge_tree=False,
    )
    root = etree.fromstring(xml_text.encode("utf-8"), parser=parser)
    if root.getroottree().docinfo.doctype:
        raise etree.XMLSyntaxError("DOCTYPE is not allowed", 0, 0, 0)

    fields = {
        "issuer_cik": "/ownershipDocument/issuer/issuerCik",
        "reporting_owner_cik": "/ownershipDocument/reportingOwner/reportingOwnerId/rptOwnerCik",
        "transaction_shares": "/ownershipDocument/nonDerivativeTable/nonDerivativeTransaction/transactionAmounts/transactionShares/value",
    }

    facts: list[ParsedOwnershipFact] = []
    for fact_name, xpath in fields.items():
        value = _first_text(root, xpath)
        facts.append(
            ParsedOwnershipFact(
                fact_name=fact_name,
                fact_value=value,
                parser_method=ParserMethod.STRUCTURED_XML.value,
                snippet_text=value,
                snippet_locator=xpath,
                document_filename=document_filename,
                validation_results={
                    "mandatory_present": bool(value),
                    "is_numeric": value.isdigit()
                    if fact_name == "transaction_shares"
                    else True,
                },
            )
        )

    return ParsedOwnershipSubmission(
        accession_no=accession_no,
        document_filename=document_filename,
        facts=facts,
    )
