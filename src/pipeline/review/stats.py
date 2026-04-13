from __future__ import annotations

import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.db.models import ExtractedFact, ExtractionEvidence, FilingDocument


class SqlAlchemyReviewStats:
    def __init__(self, session: Session):
        """Back the review-gate heuristics with SQLAlchemy queries."""
        self.session = session

    def issuer_field_count(self, cik: str, route: str, field_name: str) -> int:
        """Count historical facts for one issuer/route/field combination."""
        count = self.session.scalar(
            select(func.count())
            .select_from(ExtractedFact)
            .join(FilingDocument, FilingDocument.accession_no == ExtractedFact.accession_no)
            .where(
                FilingDocument.cik == cik,
                ExtractedFact.route == route,
                ExtractedFact.field_name == field_name,
            )
        )
        return int(count or 0)

    def template_field_count(self, template_hash: str, route: str, field_name: str) -> int:
        """Count how often one extraction template produced this field."""
        count = self.session.scalar(
            select(func.count()).select_from(ExtractionEvidence).where(
                ExtractionEvidence.source_xpath == template_hash,
                ExtractionEvidence.route == route,
                ExtractionEvidence.field_name == field_name,
            )
        )
        return int(count or 0)

    def zscore(self, value_numeric: float, route: str, field_name: str) -> float | None:
        """Measure how extreme a numeric value is relative to past facts."""
        rows = self.session.execute(
            select(ExtractedFact.value_numeric, ExtractedFact.value_text).where(
                ExtractedFact.route == route,
                ExtractedFact.field_name == field_name,
            )
        ).all()

        numeric_values: list[float] = []
        for row in rows:
            row_value_numeric = row[0]
            row_value_text = row[1]
            if isinstance(row_value_numeric, (int, float)) and not isinstance(row_value_numeric, bool):
                numeric_values.append(float(row_value_numeric))
                continue
            if isinstance(row_value_text, str):
                text_length = len(row_value_text.strip())
                if text_length > 0:
                    numeric_values.append(float(text_length))

        if len(numeric_values) < 2:
            return None

        mean = sum(numeric_values) / len(numeric_values)
        variance = sum((value - mean) ** 2 for value in numeric_values) / len(numeric_values)
        if variance <= 0:
            return None

        std_dev = math.sqrt(variance)
        return abs((value_numeric - mean) / std_dev)
