import pytest
from lxml import etree

from src.parsers.ownership_xml import parse_ownership_xml


FORM4_XML = """
<ownershipDocument>
  <issuer>
    <issuerCik>0000320193</issuerCik>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0001214156</rptOwnerCik>
    </reportingOwnerId>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionAmounts>
        <transactionShares>
          <value>1234</value>
        </transactionShares>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""


def test_parse_ownership_xml_emits_xpath_backed_facts() -> None:
    parsed = parse_ownership_xml(
        accession_no="0000320193-24-000012",
        document_filename="primary_doc.xml",
        xml_text=FORM4_XML,
    )

    fact_names = {fact.fact_name for fact in parsed.facts}
    assert {"issuer_cik", "reporting_owner_cik", "transaction_shares"} <= fact_names

    shares_fact = next(
        fact for fact in parsed.facts if fact.fact_name == "transaction_shares"
    )
    assert shares_fact.snippet_locator.endswith(
        "/nonDerivativeTransaction/transactionAmounts/transactionShares/value"
    )
    assert shares_fact.parser_method == "structured_xml"


def test_parse_ownership_xml_rejects_entity_expansion_payload() -> None:
    xml_with_entity = """
<!DOCTYPE ownershipDocument [
  <!ENTITY xxe "expanded">
]>
<ownershipDocument>
  <issuer>
    <issuerCik>&xxe;</issuerCik>
  </issuer>
</ownershipDocument>
"""

    with pytest.raises(etree.XMLSyntaxError):
        parse_ownership_xml(
            accession_no="0000320193-24-000012",
            document_filename="primary_doc.xml",
            xml_text=xml_with_entity,
        )
