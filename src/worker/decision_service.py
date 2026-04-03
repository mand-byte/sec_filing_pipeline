from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
from typing import Any, Callable

from src.domain.enums import (
    DecisionState,
    FallbackReason,
    ParseAttemptStatus,
    ParseFailureType,
    ParserMethod,
    RouteType,
)
from src.parsers.ownership_xml import ParsedOwnershipSubmission


@dataclass(frozen=True, slots=True)
class ParseRouteAttempt:
    id: str
    run_id: str
    route_type: str
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
    parser_method: str
    attempted_at_utc: datetime
    status: str
    failure_type: str | None
    error_message: str | None
    fallback_reason: str | None
    decision_state: str | None
    selected_candidate: bool


@dataclass(frozen=True, slots=True)
class DecisionResult:
    route_type: str
    final_decision_state: str
    selected_parser_method: str | None
    parsed_submission: ParsedOwnershipSubmission | None
    failure_reason: str | None


def _attempt_id(
    run_id: str,
    accession_no: str,
    document_id: str,
    parser_method: str,
    attempted_at_utc: datetime,
) -> str:
    material = (
        f"{run_id}:{accession_no}:{document_id}:{parser_method}:"
        f"{attempted_at_utc.isoformat()}"
    )
    return sha1(material.encode("utf-8")).hexdigest()


def _submission_is_acceptable(
    submission: ParsedOwnershipSubmission,
) -> tuple[bool, str | None]:
    has_missing_mandatory = any(
        not bool(fact.validation_results.get("mandatory_present", True))
        for fact in submission.facts
    )
    if has_missing_mandatory:
        return False, FallbackReason.STRUCTURED_XML_MISSING_MANDATORY.value

    has_invalid_numeric = any(
        fact.validation_results.get("is_numeric", True) is False
        for fact in submission.facts
    )
    if has_invalid_numeric:
        return False, FallbackReason.STRUCTURED_XML_NUMERIC_INVALID.value

    has_empty_value = any(not fact.fact_value for fact in submission.facts)
    if has_empty_value:
        return False, FallbackReason.STRUCTURED_XML_EMPTY_VALUE.value

    return True, None


class DecisionService:
    def __init__(
        self,
        structured_parser: Callable[[str], ParsedOwnershipSubmission],
        deterministic_parser: Callable[[str], ParsedOwnershipSubmission],
        attempt_log_repo: Any,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._structured_parser = structured_parser
        self._deterministic_parser = deterministic_parser
        self._attempt_log_repo = attempt_log_repo
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    def _append_attempt(
        self,
        document: Any,
        parser_method: str,
        status: str,
        failure_type: str | None,
        error_message: str | None,
        fallback_reason: str | None,
        decision_state: str | None,
        selected_candidate: bool,
    ) -> None:
        attempted_at_utc = self._now_fn()
        attempt = ParseRouteAttempt(
            id=_attempt_id(
                document.run_id,
                document.accession_no,
                document.document_id,
                parser_method,
                attempted_at_utc,
            ),
            run_id=document.run_id,
            route_type=RouteType.OWNER.value,
            filing_id=document.filing_id,
            accession_no=document.accession_no,
            cik=document.cik,
            document_id=document.document_id,
            document_type=document.document_type,
            document_filename=document.document_filename,
            document_path=document.document_path,
            snapshot_path=document.snapshot_path,
            source_url=document.source_url,
            sha256_hex=document.sha256_hex,
            byte_length=document.byte_length,
            parser_method=parser_method,
            attempted_at_utc=attempted_at_utc,
            status=status,
            failure_type=failure_type,
            error_message=error_message,
            fallback_reason=fallback_reason,
            decision_state=decision_state,
            selected_candidate=selected_candidate,
        )
        self._attempt_log_repo.append(attempt)

    def parse_document(self, document: Any, document_text: str) -> DecisionResult:
        try:
            structured = self._structured_parser(document_text)
            structured_ok, structured_reason = _submission_is_acceptable(structured)
            if structured_ok:
                self._append_attempt(
                    document=document,
                    parser_method=ParserMethod.STRUCTURED_XML.value,
                    status=ParseAttemptStatus.SUCCESS.value,
                    failure_type=None,
                    error_message=None,
                    fallback_reason=None,
                    decision_state=DecisionState.ACCEPTED.value,
                    selected_candidate=True,
                )
                return DecisionResult(
                    route_type=RouteType.OWNER.value,
                    final_decision_state=DecisionState.ACCEPTED.value,
                    selected_parser_method=ParserMethod.STRUCTURED_XML.value,
                    parsed_submission=structured,
                    failure_reason=None,
                )

            self._append_attempt(
                document=document,
                parser_method=ParserMethod.STRUCTURED_XML.value,
                status=ParseAttemptStatus.FAILED.value,
                failure_type=ParseFailureType.LOGIC.value,
                error_message="structured validation failed",
                fallback_reason=structured_reason,
                decision_state=DecisionState.NEEDS_REVIEW.value,
                selected_candidate=False,
            )
        except Exception as exc:  # noqa: BLE001
            self._append_attempt(
                document=document,
                parser_method=ParserMethod.STRUCTURED_XML.value,
                status=ParseAttemptStatus.FAILED.value,
                failure_type=ParseFailureType.PARSE.value,
                error_message=str(exc),
                fallback_reason=FallbackReason.STRUCTURED_XML_EXCEPTION.value,
                decision_state=DecisionState.NEEDS_REVIEW.value,
                selected_candidate=False,
            )

        try:
            deterministic = self._deterministic_parser(document_text)
            self._append_attempt(
                document=document,
                parser_method=ParserMethod.DETERMINISTIC_RULE.value,
                status=ParseAttemptStatus.SUCCESS.value,
                failure_type=None,
                error_message=None,
                fallback_reason=None,
                decision_state=DecisionState.NEEDS_REVIEW.value,
                selected_candidate=True,
            )
            return DecisionResult(
                route_type=RouteType.OWNER.value,
                final_decision_state=DecisionState.NEEDS_REVIEW.value,
                selected_parser_method=ParserMethod.DETERMINISTIC_RULE.value,
                parsed_submission=deterministic,
                failure_reason=None,
            )
        except Exception as exc:  # noqa: BLE001
            self._append_attempt(
                document=document,
                parser_method=ParserMethod.DETERMINISTIC_RULE.value,
                status=ParseAttemptStatus.FAILED.value,
                failure_type=ParseFailureType.PARSE.value,
                error_message=str(exc),
                fallback_reason=FallbackReason.ALL_METHODS_FAILED.value,
                decision_state=DecisionState.NEEDS_REVIEW.value,
                selected_candidate=False,
            )
            return DecisionResult(
                route_type=RouteType.OWNER.value,
                final_decision_state=DecisionState.NEEDS_REVIEW.value,
                selected_parser_method=None,
                parsed_submission=None,
                failure_reason=FallbackReason.ALL_METHODS_FAILED.value,
            )
