from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from sqlalchemy import select

from src.db.models import GoldenCase, GoldenSubject, GoldenTruth
from src.pipeline.result_store import load_parsed_value


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
        """Return a JSON-serializable representation of the preferred truth row."""
        return asdict(self)


def _coerce_numeric(value: Decimal | float | int | None) -> float | None:
    """Normalize mixed numeric DB values to floats."""
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
    """Prefer manual-review ground truth, then fall back to parsed facts."""
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

    parsed = load_parsed_value(
        session=session,
        accession_no=accession_no,
        route=route,
        field_name=field_name,
        subject_key=subject_key,
    )
    if parsed is None:
        return None

    return PreferredTruth(
        accession_no=accession_no,
        route=route,
        field_name=field_name,
        subject_key=subject_key,
        source="parsed",
        truth_tier=None,
        truth_source=None,
        value_numeric=parsed.value_numeric,
        value_text=parsed.value_text,
        value_json=parsed.value_json,
        value_unit=parsed.value_unit,
    )
