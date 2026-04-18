from __future__ import annotations

import math

from sqlalchemy.orm import Session

from src.pipeline.result_store import issuer_field_count, numeric_history_values, template_field_count


class SqlAlchemyReviewStats:
    def __init__(self, session: Session):
        """Back the review-gate heuristics with SQLAlchemy queries."""
        self.session = session

    def issuer_field_count(self, cik: str, route: str, field_name: str) -> int:
        """Count historical facts for one issuer/route/field combination."""
        return issuer_field_count(
            session=self.session,
            cik=cik,
            route=route,
            field_name=field_name,
        )

    def template_field_count(self, template_hash: str, route: str, field_name: str) -> int:
        """Count how often one extraction template produced this field."""
        return template_field_count(
            session=self.session,
            template_hash=template_hash,
            route=route,
            field_name=field_name,
        )

    def zscore(self, value_numeric: float, route: str, field_name: str) -> float | None:
        """Measure how extreme a numeric value is relative to past facts."""
        rows = numeric_history_values(
            session=self.session,
            route=route,
            field_name=field_name,
        )

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
