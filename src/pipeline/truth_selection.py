from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import ExtractedFact, GoldenCase, GoldenSubject, GoldenTruth


@dataclass(frozen=True)
class PreferredTruth:
    accession_no: str
    route: str
    field_name: str
    subject_key: str
    source: str
    truth_tier: str | None
    truth_source: str | None
    value_numeric: float | None
    value_text: str | None
    value_json: str | None
    value_unit: str | None

    def asdict(self) -> dict[str, object]:
        return asdict(self)


def _coerce_numeric(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def select_preferred_truth(
    *,
    session: Session,
    accession_no: str,
    route: str,
    field_name: str,
    subject_key: str = "document",
) -> PreferredTruth | None:
    manual_truth_row = session.execute(
        select(GoldenTruth, GoldenCase, GoldenSubject)
        .join(GoldenCase, GoldenCase.case_id == GoldenTruth.case_id)
        .join(GoldenSubject, GoldenSubject.id == GoldenTruth.subject_id)
        .where(
            GoldenCase.accession_no == accession_no,
            GoldenSubject.subject_key == subject_key,
            GoldenTruth.field_name == field_name,
            GoldenTruth.truth_tier == "gold",
            GoldenTruth.truth_source == "manual_review",
        )
        .order_by(GoldenTruth.created_at.desc(), GoldenTruth.id.desc())
    ).first()
    if manual_truth_row is not None:
        truth, _, _ = manual_truth_row
        return PreferredTruth(
            accession_no=accession_no,
            route=route,
            field_name=field_name,
            subject_key=subject_key,
            source="ground_truth",
            truth_tier=truth.truth_tier,
            truth_source=truth.truth_source,
            value_numeric=_coerce_numeric(truth.value_numeric),
            value_text=truth.value_text,
            value_json=truth.value_json,
            value_unit=truth.value_unit,
        )

    fact = session.scalar(
        select(ExtractedFact).where(
            ExtractedFact.accession_no == accession_no,
            ExtractedFact.route == route,
            ExtractedFact.field_name == field_name,
            ExtractedFact.subject_key == subject_key,
        )
    )
    if fact is None:
        return None

    return PreferredTruth(
        accession_no=accession_no,
        route=route,
        field_name=field_name,
        subject_key=subject_key,
        source="parsed",
        truth_tier=None,
        truth_source=None,
        value_numeric=fact.value_numeric,
        value_text=fact.value_text,
        value_json=fact.value_json,
        value_unit=fact.value_unit,
    )
