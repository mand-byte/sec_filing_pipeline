from dataclasses import dataclass
from datetime import datetime, timezone
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import ExtractedFact, ExtractionEvidence, FilingDocument, ReviewTask
from src.pipeline.types import FilingRecord, RouteName


@dataclass(frozen=True)
class FactInput:
    field_name: str
    subject_key: str = "document"
    value_numeric: float | None = None
    value_text: str | None = None
    value_json: str | None = None
    value_unit: str | None = None
    confidence: float | None = None
    review_priority: str | None = None
    review_reason: str | None = None


@dataclass(frozen=True)
class EvidenceInput:
    field_name: str
    locator_kind: str
    source_span: str
    subject_key: str = "document"
    source_section: str | None = None
    source_item_no: str | None = None
    source_xpath: str | None = None
    xbrl_concept: str | None = None
    source_locator_json: str | None = None
    source_heading_path_json: str | None = None
    source_block_offsets_json: str | None = None
    adequacy_signals_json: str | None = None
    retry_history_json: str | None = None
    selection_trace_json: str | None = None
    raw_value: str | None = None
    normalized_value: str | None = None


class PersistenceService:
    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _bounded_text(value: str | None, *, limit: int) -> str | None:
        if value is None:
            return None
        text = str(value)
        return text[:limit]

    @staticmethod
    def _effective_source_locator_json(evidence: EvidenceInput) -> str:
        if evidence.source_locator_json is not None:
            return evidence.source_locator_json

        return json.dumps(
            {
                "locator_kind": evidence.locator_kind,
                "source_span": evidence.source_span,
                "source_section": evidence.source_section,
                "source_item_no": evidence.source_item_no,
                "source_xpath": evidence.source_xpath,
                "xbrl_concept": evidence.xbrl_concept,
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    def persist_numeric_field(
        self,
        *,
        filing: FilingRecord,
        route: RouteName | str,
        field_name: str,
        value_numeric: float | int,
        locator_kind: str,
        locator_path: str,
        raw_value: str | float | int,
    ) -> None:
        self.persist_filing_bundle(
            filing=filing,
            route=route,
            facts=[
                FactInput(
                    field_name=field_name,
                    value_numeric=float(value_numeric),
                    confidence=0.99,
                )
            ],
            evidences=[
                EvidenceInput(
                    field_name=field_name,
                    locator_kind=locator_kind,
                    source_span=locator_path,
                    raw_value=str(raw_value),
                    normalized_value=str(value_numeric),
                )
            ],
        )

    def persist_filing_bundle(
        self,
        *,
        filing: FilingRecord,
        route: RouteName | str,
        facts: list[FactInput],
        evidences: list[EvidenceInput],
    ) -> None:
        if facts and not evidences:
            raise ValueError("at least one evidence")

        if facts:
            evidence_keys = {(evidence.field_name, evidence.subject_key) for evidence in evidences}
            missing_evidence = [
                (fact.field_name, fact.subject_key)
                for fact in facts
                if (fact.field_name, fact.subject_key) not in evidence_keys
            ]
            if missing_evidence:
                raise ValueError("at least one evidence")

        now = datetime.now(timezone.utc)

        existing_doc = self.session.scalar(
            select(FilingDocument).where(FilingDocument.accession_no == filing.accession_no)
        )
        if existing_doc is None:
            self.session.add(
                FilingDocument(
                    accession_no=filing.accession_no,
                    cik=filing.cik,
                    ticker=filing.ticker,
                    form_type=filing.form_type,
                    filed_at=filing.filed_at,
                    accepted_at=filing.accepted_at,
                    period_end=filing.period_end,
                    is_amendment=filing.is_amendment,
                    amendment_no=filing.amendment_no,
                    created_at=now,
                )
            )
            self.session.flush()

        evidence_rows_by_key: dict[tuple[str, str], ExtractionEvidence] = {}
        for evidence in evidences:
            source_locator_json = self._effective_source_locator_json(evidence)
            existing_evidence = self.session.scalar(
                select(ExtractionEvidence).where(
                    ExtractionEvidence.accession_no == filing.accession_no,
                    ExtractionEvidence.route == route,
                    ExtractionEvidence.field_name == evidence.field_name,
                    ExtractionEvidence.subject_key == evidence.subject_key,
                    ExtractionEvidence.locator_kind == evidence.locator_kind,
                    ExtractionEvidence.source_span == evidence.source_span,
                    ExtractionEvidence.source_section == evidence.source_section,
                    ExtractionEvidence.source_item_no == evidence.source_item_no,
                    ExtractionEvidence.source_xpath == evidence.source_xpath,
                    ExtractionEvidence.xbrl_concept == evidence.xbrl_concept,
                    ExtractionEvidence.raw_value == evidence.raw_value,
                    ExtractionEvidence.normalized_value == evidence.normalized_value,
                    ExtractionEvidence.source_locator_json == source_locator_json,
                    ExtractionEvidence.source_heading_path_json == evidence.source_heading_path_json,
                    ExtractionEvidence.source_block_offsets_json == evidence.source_block_offsets_json,
                    ExtractionEvidence.adequacy_signals_json == evidence.adequacy_signals_json,
                    ExtractionEvidence.retry_history_json == evidence.retry_history_json,
                    ExtractionEvidence.selection_trace_json == evidence.selection_trace_json,
                )
            )
            evidence_row = existing_evidence
            if evidence_row is None:
                evidence_row = ExtractionEvidence(
                    accession_no=filing.accession_no,
                    route=route,
                    field_name=evidence.field_name,
                    subject_key=evidence.subject_key,
                    locator_kind=evidence.locator_kind,
                    source_section=self._bounded_text(evidence.source_section, limit=128),
                    source_item_no=self._bounded_text(evidence.source_item_no, limit=32),
                    source_xpath=evidence.source_xpath,
                    xbrl_concept=self._bounded_text(evidence.xbrl_concept, limit=128),
                    source_span=evidence.source_span,
                    source_locator_json=source_locator_json,
                    source_heading_path_json=evidence.source_heading_path_json,
                    source_block_offsets_json=evidence.source_block_offsets_json,
                    adequacy_signals_json=evidence.adequacy_signals_json,
                    retry_history_json=evidence.retry_history_json,
                    selection_trace_json=evidence.selection_trace_json,
                    raw_value=evidence.raw_value,
                    normalized_value=evidence.normalized_value,
                    created_at=now,
                )
                self.session.add(evidence_row)

            evidence_rows_by_key[(evidence.field_name, evidence.subject_key)] = evidence_row

        self.session.flush()

        for fact in facts:
            existing_fact = self.session.scalar(
                select(ExtractedFact).where(
                    ExtractedFact.accession_no == filing.accession_no,
                    ExtractedFact.route == route,
                    ExtractedFact.field_name == fact.field_name,
                    ExtractedFact.subject_key == fact.subject_key,
                )
            )

            if existing_fact is None:
                self.session.add(
                    ExtractedFact(
                        accession_no=filing.accession_no,
                        route=route,
                        field_name=fact.field_name,
                        subject_key=fact.subject_key,
                        value_numeric=fact.value_numeric,
                        value_text=fact.value_text,
                        value_json=fact.value_json,
                        value_unit=fact.value_unit,
                        confidence=fact.confidence,
                        extracted_at=now,
                    )
                )
            else:
                existing_fact.value_numeric = fact.value_numeric
                existing_fact.value_text = fact.value_text
                existing_fact.value_json = fact.value_json
                existing_fact.value_unit = fact.value_unit
                existing_fact.confidence = fact.confidence
                existing_fact.extracted_at = now

            if fact.confidence is not None and fact.confidence < 0.5:
                evidence_row = evidence_rows_by_key.get((fact.field_name, fact.subject_key))
                existing_review_task = self.session.scalar(
                    select(ReviewTask).where(
                        ReviewTask.accession_no == filing.accession_no,
                        ReviewTask.route == route,
                        ReviewTask.field_name == fact.field_name,
                        ReviewTask.subject_key == fact.subject_key,
                        ReviewTask.status == "open",
                    )
                )
                if existing_review_task is None:
                    self.session.add(
                        ReviewTask(
                            accession_no=filing.accession_no,
                            route=route,
                            field_name=fact.field_name,
                            subject_key=fact.subject_key,
                            primary_evidence_id=evidence_row.id if evidence_row is not None else None,
                            status="open",
                            priority=fact.review_priority or "high",
                            reason=fact.review_reason,
                            assignee=None,
                            created_at=now,
                            resolved_at=None,
                        )
                    )

        self.session.commit()
