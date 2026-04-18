from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import (
    FilingDocument,
    GoldenCase,
    GoldenEvalRun,
    GoldenReviewPacket,
    GoldenSubject,
    GoldenTruth,
    ReviewDecision,
    ReviewTask,
)
from src.pipeline.review.error_codes import normalize_review_error_code
from src.pipeline.extraction.subject_keys import subject_type_for_key
from src.pipeline.result_store import clear_parsed_value, load_parsed_value, update_parsed_value


REVIEW_DECISIONS = {
    "accept": "ACCEPT",
    "corrected": "CORRECTED",
    "reject": "REJECT",
    "not_applicable": "NOT_APPLICABLE",
}


@dataclass(frozen=True)
class ReviewTaskSummary:
    task_id: int
    accession_no: str
    route: str
    field_name: str
    subject_key: str
    status: str
    priority: str
    reason: str | None
    assignee: str | None
    created_at: datetime


@dataclass(frozen=True)
class ReviewTaskDetail:
    task: ReviewTaskSummary
    filing: dict[str, Any] | None
    fact: dict[str, Any] | None
    primary_evidence: dict[str, Any] | None


class ReviewWorkflowError(ValueError):
    pass


def _task_summary(task: ReviewTask) -> ReviewTaskSummary:
    """Project the ORM task row into the lightweight summary dataclass."""
    return ReviewTaskSummary(
        task_id=task.task_id,
        accession_no=task.accession_no,
        route=task.route,
        field_name=task.field_name,
        subject_key=task.subject_key,
        status=task.status,
        priority=task.priority,
        reason=task.reason,
        assignee=task.assignee,
        created_at=task.created_at,
    )


def _normalize_decision(value: str) -> str:
    """Normalize and validate a review decision token."""
    normalized = value.strip().lower().replace("-", "_")
    if normalized not in REVIEW_DECISIONS:
        allowed = ", ".join(sorted(REVIEW_DECISIONS))
        raise ReviewWorkflowError(f"decision must be one of: {allowed}")
    return normalized


def _normalize_corrected_payload(value: str | None) -> dict[str, Any] | None:
    """Decode the optional corrected-value JSON payload."""
    if value is None:
        return None
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ReviewWorkflowError(f"invalid corrected payload json: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ReviewWorkflowError("corrected payload must decode to a JSON object")
    return dict(payload)


def _normalize_reviewer(value: str) -> str:
    """Normalize and validate the reviewer name."""
    normalized = value.strip()
    if not normalized:
        raise ReviewWorkflowError("reviewer is required")
    return normalized


def _coerce_numeric(value: object) -> float | None:
    """Coerce corrected numeric payload values into floats."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ReviewWorkflowError("value_numeric cannot be boolean")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError as exc:
            raise ReviewWorkflowError("value_numeric must be numeric") from exc
    raise ReviewWorkflowError("value_numeric must be numeric")


def _subject_type_for(*, route: str, subject_key: str) -> str:
    """Resolve the golden-subject type for one route/subject-key pair."""
    return subject_type_for_key(route=route, subject_key=subject_key)


def _decimal_or_none(value: object) -> Decimal | None:
    """Coerce mixed numeric truth values into `Decimal` for storage."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ReviewWorkflowError("boolean cannot be stored as numeric truth")
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            return Decimal(cleaned)
        except Exception as exc:  # pragma: no cover - defensive conversion branch
            raise ReviewWorkflowError("invalid decimal truth value") from exc
    raise ReviewWorkflowError("unsupported numeric truth value type")


class ReviewWorkflowService:
    def __init__(self, session: Session):
        """Manage review task listing, assignment, resolution, and capture."""
        self.session = session

    def list_tasks(
        self,
        *,
        status: str = "open",
        route: str | None = None,
        limit: int = 100,
    ) -> list[ReviewTaskSummary]:
        """List review tasks with optional status and route filters."""
        stmt = select(ReviewTask).order_by(ReviewTask.created_at.asc(), ReviewTask.task_id.asc())
        if status:
            stmt = stmt.where(ReviewTask.status == status)
        if route:
            stmt = stmt.where(ReviewTask.route == route)
        rows = self.session.scalars(stmt.limit(limit)).all()
        return [_task_summary(row) for row in rows]

    def get_task_detail(self, *, task_id: int) -> ReviewTaskDetail:
        """Load one review task with filing, fact, and primary-evidence payloads."""
        task = self.session.get(ReviewTask, task_id)
        if task is None:
            raise ReviewWorkflowError(f"review task not found: {task_id}")

        filing = self.session.scalar(
            select(FilingDocument).where(FilingDocument.accession_no == task.accession_no)
        )
        parsed = load_parsed_value(
            session=self.session,
            accession_no=task.accession_no,
            route=task.route,
            field_name=task.field_name,
            subject_key=task.subject_key,
        )

        filing_payload = None
        if filing is not None:
            filing_payload = {
                "accession_no": filing.accession_no,
                "cik": filing.cik,
                "ticker": filing.ticker,
                "form_type": filing.form_type,
                "filed_at": filing.filed_at.isoformat() if filing.filed_at else None,
                "accepted_at": filing.accepted_at.isoformat() if filing.accepted_at else None,
                "period_end": filing.period_end.isoformat() if filing.period_end else None,
                "is_amendment": filing.is_amendment,
                "amendment_no": filing.amendment_no,
            }

        fact_payload = None
        if parsed is not None:
            fact_payload = {
                "value_numeric": parsed.value_numeric,
                "value_text": parsed.value_text,
                "value_json": parsed.value_json,
                "value_unit": parsed.value_unit,
                "confidence": parsed.confidence,
            }

        evidence_payload = None
        if parsed is not None and parsed.evidence_payload is not None:
            evidence_payload = dict(parsed.evidence_payload)

        return ReviewTaskDetail(
            task=_task_summary(task),
            filing=filing_payload,
            fact=fact_payload,
            primary_evidence=evidence_payload,
        )

    def assign_task(self, *, task_id: int, assignee: str) -> ReviewTaskSummary:
        """Assign one review task to the provided assignee."""
        task = self.session.get(ReviewTask, task_id)
        if task is None:
            raise ReviewWorkflowError(f"review task not found: {task_id}")
        task.assignee = assignee.strip() or None
        self.session.commit()
        return _task_summary(task)

    def resolve_task(
        self,
        *,
        task_id: int,
        decision: str,
        reviewer: str,
        comment: str | None = None,
        corrected_json: str | None = None,
        error_code: str | None = None,
    ) -> ReviewTaskSummary:
        """Resolve one open review task and persist any fix-once side effects."""
        task = self.session.get(ReviewTask, task_id)
        if task is None:
            raise ReviewWorkflowError(f"review task not found: {task_id}")
        if task.status != "open":
            raise ReviewWorkflowError(f"review task is not open: {task_id}")

        normalized_reviewer = _normalize_reviewer(reviewer)
        normalized_decision = _normalize_decision(decision)
        normalized_error_code = None
        if isinstance(error_code, str) and error_code.strip():
            try:
                normalized_error_code = normalize_review_error_code(error_code)
            except ValueError as exc:
                raise ReviewWorkflowError(str(exc)) from exc
        if normalized_decision != "accept" and normalized_error_code is None:
            raise ReviewWorkflowError("non-accept decisions require --error-code")
        corrected_payload = _normalize_corrected_payload(corrected_json)
        parsed = load_parsed_value(
            session=self.session,
            accession_no=task.accession_no,
            route=task.route,
            field_name=task.field_name,
            subject_key=task.subject_key,
        )
        now = datetime.now(timezone.utc)

        if normalized_decision == "corrected":
            if parsed is None:
                raise ReviewWorkflowError("cannot correct a missing fact row")
            if corrected_payload is None:
                raise ReviewWorkflowError("corrected decision requires --corrected-json")
            if "value_numeric" in corrected_payload:
                corrected_payload["value_numeric"] = _coerce_numeric(corrected_payload.get("value_numeric"))
            corrected_payload["confidence"] = 1.0
            update_parsed_value(
                session=self.session,
                accession_no=task.accession_no,
                route=task.route,
                field_name=task.field_name,
                subject_key=task.subject_key,
                corrected_payload=corrected_payload,
            )
        elif normalized_decision in {"reject", "not_applicable"}:
            if parsed is not None:
                clear_parsed_value(
                    session=self.session,
                    accession_no=task.accession_no,
                    route=task.route,
                    field_name=task.field_name,
                    subject_key=task.subject_key,
                )

        if normalized_decision != "accept":
            self._capture_golden_regression_seed(
                task=task,
                parsed=parsed,
                corrected_payload=corrected_payload,
                comment=comment,
                reviewer=normalized_reviewer,
                error_code=normalized_error_code,
                decided_at=now,
                decision=normalized_decision,
            )

        self.session.add(
            ReviewDecision(
                task_id=task.task_id,
                decision=REVIEW_DECISIONS[normalized_decision],
                error_code=normalized_error_code,
                corrected_value_json=json.dumps(corrected_payload, ensure_ascii=False) if corrected_payload is not None else None,
                comment=comment,
                reviewer=normalized_reviewer,
                decided_at=now,
            )
        )
        task.status = normalized_decision
        task.resolved_at = now
        if not task.assignee:
            task.assignee = normalized_reviewer
        self.session.commit()
        return _task_summary(task)

    def _capture_golden_regression_seed(
        self,
        *,
        task: ReviewTask,
        parsed: Any | None,
        corrected_payload: dict[str, Any] | None,
        comment: str | None,
        reviewer: str,
        error_code: str,
        decided_at: datetime,
        decision: str,
    ) -> None:
        """Capture a golden regression packet for non-accept review outcomes."""
        filing = self.session.scalar(
            select(FilingDocument).where(FilingDocument.accession_no == task.accession_no)
        )

        case_id = f"manual-review::{task.accession_no}"
        case = self.session.get(GoldenCase, case_id)
        if case is None:
            if filing is None:
                raise ReviewWorkflowError("cannot build golden case without filing document")
            case = GoldenCase(
                case_id=case_id,
                accession_no=filing.accession_no,
                cik=filing.cik,
                form_type=filing.form_type,
                accepted_at=filing.accepted_at,
                truth_cutoff_at=decided_at,
                is_amendment=filing.is_amendment,
                amendment_no=filing.amendment_no,
                source_accession_no=filing.accession_no,
                source_snapshot_hash=None,
                created_at=decided_at,
            )
            self.session.add(case)
            self.session.flush()

        subject = self.session.scalar(
            select(GoldenSubject).where(
                GoldenSubject.case_id == case_id,
                GoldenSubject.subject_key == task.subject_key,
            )
        )
        if subject is None:
            subject = GoldenSubject(
                case_id=case_id,
                subject_type=_subject_type_for(route=task.route, subject_key=task.subject_key),
                subject_key=task.subject_key,
                parent_subject_key=None,
                ordinal=None,
                created_at=decided_at,
            )
            self.session.add(subject)
            self.session.flush()

        if decision in {"corrected", "not_applicable"}:
            truth = self.session.scalar(
                select(GoldenTruth).where(
                    GoldenTruth.case_id == case_id,
                    GoldenTruth.subject_id == subject.id,
                    GoldenTruth.field_name == task.field_name,
                    GoldenTruth.truth_tier == "gold",
                    GoldenTruth.truth_source == "manual_review",
                )
            )
            truth_numeric = None
            truth_text = None
            truth_json = None
            truth_unit = None
            is_applicable = decision != "not_applicable"
            if decision == "corrected":
                source_payload = corrected_payload or {}
                if "value_numeric" in source_payload:
                    truth_numeric = _decimal_or_none(source_payload.get("value_numeric"))
                elif parsed is not None:
                    truth_numeric = _decimal_or_none(parsed.value_numeric)
                truth_text = source_payload.get("value_text", parsed.value_text if parsed is not None else None)
                value_json = source_payload.get("value_json", parsed.value_json if parsed is not None else None)
                truth_json = value_json if isinstance(value_json, str) or value_json is None else json.dumps(value_json, ensure_ascii=False)
                truth_unit = source_payload.get("value_unit", parsed.value_unit if parsed is not None else None)

            if truth is None:
                truth = GoldenTruth(
                    case_id=case_id,
                    subject_id=subject.id,
                    field_name=task.field_name,
                    truth_tier="gold",
                    truth_source="manual_review",
                    is_applicable=is_applicable,
                    value_numeric=truth_numeric,
                    value_text=truth_text,
                    value_json=truth_json,
                    value_unit=truth_unit,
                    created_at=decided_at,
                )
                self.session.add(truth)
            else:
                truth.is_applicable = is_applicable
                truth.value_numeric = truth_numeric
                truth.value_text = truth_text
                truth.value_json = truth_json
                truth.value_unit = truth_unit

        run_id = f"review-capture::{task.task_id}"
        eval_run = self.session.get(GoldenEvalRun, run_id)
        if eval_run is None:
            eval_run = GoldenEvalRun(
                run_id=run_id,
                config_path="manual-review",
                git_sha=None,
                summary_json=json.dumps({"source": "review_workflow"}, ensure_ascii=False),
                created_at=decided_at,
            )
            self.session.add(eval_run)
            self.session.flush()

        packet = self.session.scalar(
            select(GoldenReviewPacket).where(
                GoldenReviewPacket.run_id == run_id,
                GoldenReviewPacket.case_id == case_id,
                GoldenReviewPacket.subject_id == subject.id,
                GoldenReviewPacket.field_name == task.field_name,
            )
        )
        packet_payload = {
            "error_code": error_code,
            "decision": decision,
            "reviewer": reviewer,
            "comment": comment,
            "task": {
                "task_id": task.task_id,
                "accession_no": task.accession_no,
                "route": task.route,
                "field_name": task.field_name,
                "subject_key": task.subject_key,
            },
            "fact": {
                "value_numeric": parsed.value_numeric if parsed is not None else None,
                "value_text": parsed.value_text if parsed is not None else None,
                "value_json": parsed.value_json if parsed is not None else None,
                "value_unit": parsed.value_unit if parsed is not None else None,
            },
            "corrected_payload": corrected_payload,
            "primary_evidence": parsed.evidence_payload if parsed is not None else None,
        }
        packet_json = json.dumps(packet_payload, ensure_ascii=False)
        if packet is None:
            self.session.add(
                GoldenReviewPacket(
                    run_id=run_id,
                    case_id=case_id,
                    subject_id=subject.id,
                    field_name=task.field_name,
                    packet_json=packet_json,
                    created_at=decided_at,
                )
            )
        else:
            packet.packet_json = packet_json


def review_task_detail_asdict(detail: ReviewTaskDetail) -> dict[str, Any]:
    """Convert a detailed review payload into a JSON-serializable dictionary."""
    payload = asdict(detail)
    payload["task"]["created_at"] = detail.task.created_at.isoformat()
    return payload
