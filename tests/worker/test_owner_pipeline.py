from src.parsers.ownership_xml import ParsedOwnershipFact
from src.worker.owner_pipeline import build_fact_row, build_review_item


def test_build_fact_row_marks_complete_xml_fact_as_accepted() -> None:
    parsed_fact = ParsedOwnershipFact(
        fact_name="transaction_shares",
        fact_value="1234",
        parser_method="structured_xml",
        snippet_text="1234",
        snippet_locator="/ownershipDocument/nonDerivativeTable/nonDerivativeTransaction/transactionAmounts/transactionShares/value",
        document_filename="primary_doc.xml",
        validation_results={"is_numeric": True},
    )

    fact_row = build_fact_row(
        filing_id="filing-1",
        accession_no="0000320193-24-000012",
        parsed_fact=parsed_fact,
    )

    assert fact_row.decision_state == "accepted"
    assert fact_row.confidence_bucket == "high"


def test_build_review_item_for_missing_mandatory_value() -> None:
    parsed_fact = ParsedOwnershipFact(
        fact_name="reporting_owner_cik",
        fact_value="",
        parser_method="structured_xml",
        snippet_text="",
        snippet_locator="/ownershipDocument/reportingOwner/reportingOwnerId/rptOwnerCik",
        document_filename="primary_doc.xml",
        validation_results={"mandatory_present": False},
    )

    review_item = build_review_item(
        accession_no="0000320193-24-000012",
        parsed_fact=parsed_fact,
    )

    assert review_item.review_reason == "mandatory_field_missing"
    assert review_item.status == "open"
