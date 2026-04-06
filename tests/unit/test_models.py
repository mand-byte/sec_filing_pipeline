from datetime import datetime
from decimal import Decimal
from typing import get_args, get_type_hints

from sqlalchemy import BigInteger, Numeric, UniqueConstraint


class _SettingsStub:
    def __init__(self, pg_dsn: str):
        self.pg_dsn = pg_dsn


def _mapped_annotation(model: type, field_name: str):
    hints = get_type_hints(model, include_extras=True)
    return get_args(hints[field_name])[0]


def test_models_register_expected_tables():
    from src.db.base import Base
    import src.db.models  # noqa: F401

    expected_tables = {
        "security_master",
        "route_watermark",
        "delisted_route_completion",
        "filing_document",
        "extracted_fact",
        "extraction_evidence",
        "pipeline_log",
        "review_task",
        "review_decision",
    }

    assert expected_tables.issubset(set(Base.metadata.tables.keys()))


def test_extracted_fact_unique_constraint_on_accession_route_field_name():
    from src.db.base import Base
    import src.db.models  # noqa: F401

    extracted_fact = Base.metadata.tables["extracted_fact"]
    unique_constraints = [
        c for c in extracted_fact.constraints if isinstance(c, UniqueConstraint)
    ]

    unique_key_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in unique_constraints
    }
    unique_constraint_names = {constraint.name for constraint in unique_constraints}

    assert ("accession_no", "route", "field_name") in unique_key_columns
    assert "uq_extracted_fact_accession_route_field" in unique_constraint_names


def test_review_task_and_review_decision_use_bigint_ids():
    from src.db.base import Base
    import src.db.models  # noqa: F401

    review_task = Base.metadata.tables["review_task"]
    review_decision = Base.metadata.tables["review_decision"]

    assert isinstance(review_task.c.id.type, BigInteger)
    assert isinstance(review_task.c.extracted_fact_id.type, BigInteger)
    assert isinstance(review_decision.c.id.type, BigInteger)
    assert isinstance(review_decision.c.review_task_id.type, BigInteger)


def test_numeric_and_datetime_annotations_are_python_types():
    from src.db.models import ExtractedFact, ReviewDecision, SecurityMaster

    assert _mapped_annotation(ExtractedFact, "numeric_value") == Decimal | None
    assert _mapped_annotation(SecurityMaster, "created_at") == datetime
    assert _mapped_annotation(ExtractedFact, "as_of_date") == datetime | None
    assert _mapped_annotation(ReviewDecision, "decided_at") == datetime


def test_extracted_fact_numeric_column_stays_numeric_with_decimal_semantics():
    from src.db.base import Base
    import src.db.models  # noqa: F401

    extracted_fact = Base.metadata.tables["extracted_fact"]

    assert isinstance(extracted_fact.c.numeric_value.type, Numeric)
    assert extracted_fact.c.numeric_value.type.asdecimal is True


def test_engine_and_session_factory_are_cached_by_dsn():
    from src.db.session import get_engine, get_session_factory

    first_settings = _SettingsStub("sqlite+pysqlite:///:memory:")
    second_settings = _SettingsStub("sqlite+pysqlite:///:memory:")

    first_engine = get_engine(first_settings)
    second_engine = get_engine(second_settings)
    first_factory = get_session_factory(first_settings)
    second_factory = get_session_factory(second_settings)

    assert first_engine is second_engine
    assert first_factory is second_factory
