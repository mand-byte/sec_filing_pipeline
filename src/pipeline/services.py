from dataclasses import dataclass
from datetime import datetime, timezone
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import (
    ExtractedFact,
    ExtractionEvidence,
    FilingDocument,
    Holding13FPosition,
    Holding13FSummary,
    ReviewTask,
)
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
        """Persist extracted facts, evidences, and review tasks into the DB."""
        self.session = session

    @staticmethod
    def _bounded_text(value: str | None, *, limit: int) -> str | None:
        """Trim text fields to the database column limit when present."""
        if value is None:
            return None
        text = str(value)
        return text[:limit]

    @staticmethod
    def _effective_source_locator_json(evidence: EvidenceInput) -> str:
        """Reuse explicit locator JSON or derive a stable fallback payload."""
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

    def _upsert_filing_document(self, *, filing: FilingRecord, now: datetime) -> None:
        """Ensure the shared filing_document row exists before result persistence."""
        existing_doc = self.session.scalar(
            select(FilingDocument).where(FilingDocument.accession_no == filing.accession_no)
        )
        if existing_doc is not None:
            return
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

    def _upsert_open_review_task(
        self,
        *,
        filing: FilingRecord,
        route: RouteName | str,
        fact: FactInput,
        now: datetime,
        primary_evidence_id: int | None = None,
    ) -> None:
        """Create one open review task when low-confidence output requires human review."""
        existing_review_task = self.session.scalar(
            select(ReviewTask).where(
                ReviewTask.accession_no == filing.accession_no,
                ReviewTask.route == route,
                ReviewTask.field_name == fact.field_name,
                ReviewTask.subject_key == fact.subject_key,
                ReviewTask.status == "open",
            )
        )
        if existing_review_task is not None:
            return
        self.session.add(
            ReviewTask(
                accession_no=filing.accession_no,
                route=route,
                field_name=fact.field_name,
                subject_key=fact.subject_key,
                primary_evidence_id=primary_evidence_id,
                status="open",
                priority=fact.review_priority or "high",
                reason=fact.review_reason,
                assignee=None,
                created_at=now,
                resolved_at=None,
            )
        )

    @staticmethod
    def _is_holding_13f_bundle(*, route: RouteName | str, filing: FilingRecord) -> bool:
        """Return True when a filing should persist through the specialized 13F tables."""
        return str(route) == "holding" and filing.form_type.strip().upper().startswith("13F-HR")

    @staticmethod
    def _evidence_payload(evidence: EvidenceInput) -> dict[str, object | None]:
        """Convert one evidence input into the compact persisted JSON payload."""
        return {
            "locator_kind": evidence.locator_kind,
            "source_section": evidence.source_section,
            "source_item_no": evidence.source_item_no,
            "source_xpath": evidence.source_xpath,
            "xbrl_concept": evidence.xbrl_concept,
            "source_span": evidence.source_span,
            "source_locator_json": evidence.source_locator_json,
            "source_heading_path_json": evidence.source_heading_path_json,
            "source_block_offsets_json": evidence.source_block_offsets_json,
            "adequacy_signals_json": evidence.adequacy_signals_json,
            "retry_history_json": evidence.retry_history_json,
            "selection_trace_json": evidence.selection_trace_json,
            "raw_value": evidence.raw_value,
            "normalized_value": evidence.normalized_value,
        }

    def _persist_holding_13f_bundle(
        self,
        *,
        filing: FilingRecord,
        route: RouteName | str,
        facts: list[FactInput],
        evidences: list[EvidenceInput],
        now: datetime,
    ) -> None:
        """Persist 13F holding outputs into specialized summary + position tables."""
        del route
        self._upsert_filing_document(filing=filing, now=now)

        evidence_map_by_subject: dict[str, dict[str, list[dict[str, object | None]]]] = {}
        for evidence in evidences:
            subject_map = evidence_map_by_subject.setdefault(evidence.subject_key, {})
            field_payloads = subject_map.setdefault(evidence.field_name, [])
            field_payloads.append(self._evidence_payload(evidence))

        summary_values: dict[str, object | None] = {}
        summary_facts = {
            fact.field_name: fact
            for fact in facts
            if fact.subject_key == "document"
        }
        position_values: dict[str, dict[str, object | None]] = {}
        for fact in facts:
            if fact.subject_key == "document":
                summary_values[fact.field_name] = fact.value_numeric if fact.value_numeric is not None else (
                    fact.value_text if fact.value_text is not None else fact.value_json
                )
            elif fact.subject_key.startswith("position:"):
                position_map = position_values.setdefault(fact.subject_key, {})
                position_map[fact.field_name] = fact.value_numeric if fact.value_numeric is not None else (
                    fact.value_text if fact.value_text is not None else fact.value_json
                )

            if fact.confidence is not None and fact.confidence < 0.5:
                self._upsert_open_review_task(
                    filing=filing,
                    route="holding",
                    fact=fact,
                    now=now,
                    primary_evidence_id=None,
                )

        self.session.query(Holding13FPosition).filter(
            Holding13FPosition.accession_no == filing.accession_no
        ).delete(synchronize_session=False)
        self.session.query(Holding13FSummary).filter(
            Holding13FSummary.accession_no == filing.accession_no
        ).delete(synchronize_session=False)

        summary_evidence_map = evidence_map_by_subject.get("document", {})
        self.session.add(
            Holding13FSummary(
                accession_no=filing.accession_no,
                info_table_entry_total=(
                    float(summary_values["info_table_entry_total"])
                    if summary_values.get("info_table_entry_total") is not None
                    else None
                ),
                info_table_value_total_usd=(
                    float(summary_values["info_table_value_total_usd"])
                    if summary_values.get("info_table_value_total_usd") is not None
                    else None
                ),
                other_included_managers_count=(
                    float(summary_values["other_included_managers_count"])
                    if summary_values.get("other_included_managers_count") is not None
                    else None
                ),
                manager_structure_quant_text=summary_facts["manager_structure_quant"].value_text if "manager_structure_quant" in summary_facts else None,
                manager_structure_quant_json=summary_facts["manager_structure_quant"].value_json if "manager_structure_quant" in summary_facts else None,
                amendment_scope_quant_text=summary_facts["amendment_scope_quant"].value_text if "amendment_scope_quant" in summary_facts else None,
                amendment_scope_quant_json=summary_facts["amendment_scope_quant"].value_json if "amendment_scope_quant" in summary_facts else None,
                evidence_map_json=json.dumps(summary_evidence_map, ensure_ascii=False, sort_keys=True)
                if summary_evidence_map
                else None,
                extracted_at=now,
            )
        )

        for subject_key, values in sorted(
            position_values.items(),
            key=lambda item: int(item[0].split(":", 1)[1]) if ":" in item[0] and item[0].split(":", 1)[1].isdigit() else 0,
        ):
            position_index = int(subject_key.split(":", 1)[1]) if ":" in subject_key and subject_key.split(":", 1)[1].isdigit() else 0
            evidence_map = evidence_map_by_subject.get(subject_key, {})
            self.session.add(
                Holding13FPosition(
                    accession_no=filing.accession_no,
                    subject_key=subject_key,
                    position_index=position_index,
                    position_value_usd=float(values["position_value_usd"]) if values.get("position_value_usd") is not None else None,
                    shares_or_principal_amount=float(values["shares_or_principal_amount"]) if values.get("shares_or_principal_amount") is not None else None,
                    sole_voting_auth_shares=float(values["sole_voting_auth_shares"]) if values.get("sole_voting_auth_shares") is not None else None,
                    shared_voting_auth_shares=float(values["shared_voting_auth_shares"]) if values.get("shared_voting_auth_shares") is not None else None,
                    none_voting_auth_shares=float(values["none_voting_auth_shares"]) if values.get("none_voting_auth_shares") is not None else None,
                    evidence_map_json=json.dumps(evidence_map, ensure_ascii=False, sort_keys=True) if evidence_map else None,
                    extracted_at=now,
                )
            )

        self.session.commit()

    def _persist_generic_bundle(
        self,
        *,
        filing: FilingRecord,
        route: RouteName | str,
        facts: list[FactInput],
        evidences: list[EvidenceInput],
        now: datetime,
    ) -> None:
        """Persist non-specialized filings through the legacy generic fact/evidence tables."""
        self._upsert_filing_document(filing=filing, now=now)

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
                self._upsert_open_review_task(
                    filing=filing,
                    route=route,
                    fact=fact,
                    now=now,
                    primary_evidence_id=evidence_row.id if evidence_row is not None else None,
                )

        self.session.commit()

    def persist_filing_bundle(
        self,
        *,
        filing: FilingRecord,
        route: RouteName | str,
        facts: list[FactInput],
        evidences: list[EvidenceInput],
    ) -> None:
        """Upsert one filing's extracted facts and linked evidence rows."""
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
        if self._is_holding_13f_bundle(route=route, filing=filing):
            self._persist_holding_13f_bundle(
                filing=filing,
                route=route,
                facts=facts,
                evidences=evidences,
                now=now,
            )
            return

        self._persist_generic_bundle(
            filing=filing,
            route=route,
            facts=facts,
            evidences=evidences,
            now=now,
        )
