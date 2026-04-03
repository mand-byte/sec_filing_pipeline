from dataclasses import dataclass
from datetime import datetime, timezone

from src.domain.enums import DecisionState, ParserMethod, RouteType
from src.parsers.ownership_xml import ParsedOwnershipFact, ParsedOwnershipSubmission
from src.worker.decision_service import DecisionService, ParseRouteAttempt


@dataclass(frozen=True, slots=True)
class _DocumentContext:
    run_id: str
    filing_id: str
    accession_no: str
    cik: str
    document_id: str
    document_type: str
    document_filename: str
    document_path: str
    snapshot_path: str | None
    source_url: str | None
    sha256_hex: str
    byte_length: int


class _FakeAttemptRepo:
    def __init__(self) -> None:
        self.rows: list[ParseRouteAttempt] = []

    def append(self, row: ParseRouteAttempt) -> None:
        self.rows.append(row)


def _structured_submission(*, mandatory_present: bool) -> ParsedOwnershipSubmission:
    return ParsedOwnershipSubmission(
        accession_no="0000320193-24-000012",
        document_filename="primary_doc.xml",
        facts=[
            ParsedOwnershipFact(
                fact_name="issuer_cik",
                fact_value="0000320193",
                parser_method=ParserMethod.STRUCTURED_XML.value,
                snippet_text="0000320193",
                snippet_locator="/ownershipDocument/issuer/issuerCik",
                document_filename="primary_doc.xml",
                validation_results={"mandatory_present": mandatory_present},
            )
        ],
    )


def _deterministic_submission() -> ParsedOwnershipSubmission:
    return ParsedOwnershipSubmission(
        accession_no="0000320193-24-000012",
        document_filename="primary_doc.txt",
        facts=[
            ParsedOwnershipFact(
                fact_name="issuer_cik",
                fact_value="0000320193",
                parser_method=ParserMethod.DETERMINISTIC_RULE.value,
                snippet_text="Issuer CIK: 0000320193",
                snippet_locator="line:1",
                document_filename="primary_doc.txt",
                validation_results={"mandatory_present": True},
            )
        ],
    )


def _doc() -> _DocumentContext:
    return _DocumentContext(
        run_id="run-1",
        filing_id="filing-1",
        accession_no="0000320193-24-000012",
        cik="0000320193",
        document_id="doc-1",
        document_type="4",
        document_filename="primary_doc.xml",
        document_path="raw/0000320193/0000320193-24-000012/doc-1.xml",
        snapshot_path=None,
        source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019324000012/xslF345X05/doc.xml",
        sha256_hex="a" * 64,
        byte_length=123,
    )


def test_decision_chain_structured_success_accepts_and_logs_only_structured() -> None:
    repo = _FakeAttemptRepo()

    def structured_parser(_: str) -> ParsedOwnershipSubmission:
        return _structured_submission(mandatory_present=True)

    def deterministic_parser(_: str) -> ParsedOwnershipSubmission:
        raise AssertionError("deterministic fallback must not run")

    service = DecisionService(
        structured_parser=structured_parser,
        deterministic_parser=deterministic_parser,
        attempt_log_repo=repo,
        now_fn=lambda: datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc),
    )

    result = service.parse_document(
        document=_doc(), document_text="<ownershipDocument />"
    )

    assert result.final_decision_state == DecisionState.ACCEPTED.value
    assert result.selected_parser_method == ParserMethod.STRUCTURED_XML.value
    assert [row.parser_method for row in repo.rows] == [
        ParserMethod.STRUCTURED_XML.value
    ]
    assert [row.status for row in repo.rows] == ["success"]


def test_decision_chain_structured_fail_then_deterministic_success_needs_review() -> (
    None
):
    repo = _FakeAttemptRepo()

    def structured_parser(_: str) -> ParsedOwnershipSubmission:
        return _structured_submission(mandatory_present=False)

    def deterministic_parser(_: str) -> ParsedOwnershipSubmission:
        return _deterministic_submission()

    service = DecisionService(
        structured_parser=structured_parser,
        deterministic_parser=deterministic_parser,
        attempt_log_repo=repo,
        now_fn=lambda: datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc),
    )

    result = service.parse_document(document=_doc(), document_text="ownership text")

    assert result.final_decision_state == DecisionState.NEEDS_REVIEW.value
    assert result.selected_parser_method == ParserMethod.DETERMINISTIC_RULE.value
    assert [row.parser_method for row in repo.rows] == [
        ParserMethod.STRUCTURED_XML.value,
        ParserMethod.DETERMINISTIC_RULE.value,
    ]
    assert [row.status for row in repo.rows] == ["failed", "success"]
    assert repo.rows[0].fallback_reason == "structured_xml_missing_mandatory"


def test_decision_chain_all_methods_fail_returns_needs_review_with_failure_details() -> (
    None
):
    repo = _FakeAttemptRepo()

    def structured_parser(_: str) -> ParsedOwnershipSubmission:
        raise ValueError("invalid xml")

    def deterministic_parser(_: str) -> ParsedOwnershipSubmission:
        raise ValueError("not applicable")

    service = DecisionService(
        structured_parser=structured_parser,
        deterministic_parser=deterministic_parser,
        attempt_log_repo=repo,
        now_fn=lambda: datetime(2024, 4, 3, 12, 0, tzinfo=timezone.utc),
    )

    result = service.parse_document(document=_doc(), document_text="ownership text")

    assert result.final_decision_state == DecisionState.NEEDS_REVIEW.value
    assert result.selected_parser_method is None
    assert result.failure_reason == "all_methods_failed"
    assert [row.parser_method for row in repo.rows] == [
        ParserMethod.STRUCTURED_XML.value,
        ParserMethod.DETERMINISTIC_RULE.value,
    ]
    assert [row.status for row in repo.rows] == ["failed", "failed"]
    assert repo.rows[0].failure_type == "parse"
    assert repo.rows[1].fallback_reason == "all_methods_failed"
    assert repo.rows[1].decision_state == DecisionState.NEEDS_REVIEW.value
    assert result.route_type == RouteType.OWNER.value
