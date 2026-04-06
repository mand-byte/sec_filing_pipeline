from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import ExtractedFact, ExtractionEvidence, FilingDocument, ReviewTask
from src.pipeline.types import FilingRecord, RouteName


@dataclass(slots=True, frozen=True)
class FactInput:
    field_name: str
    value_numeric: float | None
    value_text: str | None
    value_json: str | None
    value_unit: str | None
    confidence: float | None
    extracted_at: datetime


@dataclass(slots=True, frozen=True)
class EvidenceInput:
    field_name: str
    locator_kind: str
    source_section: str | None
    source_item_no: str | None
    source_xpath: str | None
    xbrl_concept: str | None
    source_span: str
    raw_value: str | None
    normalized_value: str | None
    created_at: datetime


class PersistenceService:
    def __init__(self, session: Session):
        self.session = session

    def persist_filing_bundle(
        self,
        *,
        filing: FilingRecord,
        route: RouteName,
        facts: list[FactInput],
        evidences: list[EvidenceInput],
    ) -> None:
        if facts and not evidences:
            raise ValueError("at least one evidence")

        existing = self.session.scalar(
            select(FilingDocument).where(FilingDocument.accession_no == filing.accession_no)
        )
        if existing is None:
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
                    created_at=datetime.now(timezone.utc),
                )
            )

        for fact in facts:
            self.session.add(
                ExtractedFact(
                    accession_no=filing.accession_no,
                    route=route,
                    field_name=fact.field_name,
                    value_numeric=fact.value_numeric,
                    value_text=fact.value_text,
                    value_json=fact.value_json,
                    value_unit=fact.value_unit,
                    confidence=fact.confidence,
                    extracted_at=fact.extracted_at,
                )
            )

            if fact.confidence is not None and fact.confidence < 0.5:
                self.session.add(
                    ReviewTask(
                        accession_no=filing.accession_no,
                        route=route,
                        field_name=fact.field_name,
                        status="open",
                        priority="normal",
                        assignee=None,
                        created_at=datetime.now(timezone.utc),
                        resolved_at=None,
                    )
                )

        for evidence in evidences:
            self.session.add(
                ExtractionEvidence(
                    accession_no=filing.accession_no,
                    route=route,
                    field_name=evidence.field_name,
                    locator_kind=evidence.locator_kind,
                    source_section=evidence.source_section,
                    source_item_no=evidence.source_item_no,
                    source_xpath=evidence.source_xpath,
                    xbrl_concept=evidence.xbrl_concept,
                    source_span=evidence.source_span,
                    raw_value=evidence.raw_value,
                    normalized_value=evidence.normalized_value,
                    created_at=evidence.created_at,
                )
            )

        self.session.commit()
