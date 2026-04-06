from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import ExtractedFact, ExtractionEvidence, FilingDocument, ReviewTask
from src.pipeline.types import FilingRecord, RouteName


@dataclass(slots=True, frozen=True)
class FactInput:
    field_name: str
    value_numeric: float | None = None
    value_text: str | None = None
    value_json: str | None = None
    value_unit: str | None = None
    confidence: float | None = None


@dataclass(slots=True, frozen=True)
class EvidenceInput:
    field_name: str
    locator_kind: str
    source_span: str
    source_section: str | None = None
    source_item_no: str | None = None
    source_xpath: str | None = None
    xbrl_concept: str | None = None
    raw_value: str | None = None
    normalized_value: str | None = None


class PersistenceService:
    def __init__(self, session: Session):
        self.session = session

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

        for fact in facts:
            existing_fact = self.session.scalar(
                select(ExtractedFact).where(
                    ExtractedFact.accession_no == filing.accession_no,
                    ExtractedFact.route == route,
                    ExtractedFact.field_name == fact.field_name,
                )
            )

            if existing_fact is None:
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
                self.session.add(
                    ReviewTask(
                        accession_no=filing.accession_no,
                        route=route,
                        field_name=fact.field_name,
                        status="open",
                        priority="high",
                        assignee=None,
                        created_at=now,
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
                    created_at=now,
                )
            )

        self.session.commit()
