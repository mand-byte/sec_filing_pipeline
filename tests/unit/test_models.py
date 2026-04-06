from datetime import datetime
from typing import get_args, get_type_hints

from sqlalchemy import Float, UniqueConstraint


class _SettingsStub:
    def __init__(self, pg_dsn: str):
        self.pg_dsn = pg_dsn


def _mapped_annotation(model: type, field_name: str):
    hints = get_type_hints(model, include_extras=True)
    return get_args(hints[field_name])[0]


def _unique_key_columns(table):
    unique_constraints = [
        c for c in table.constraints if isinstance(c, UniqueConstraint)
    ]
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in unique_constraints
    }


def test_models_register_required_tables():
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

    assert expected_tables == set(Base.metadata.tables.keys())


def test_models_include_required_task2_columns():
    from src.db.base import Base
    import src.db.models  # noqa: F401

    expected_columns = {
        "security_master": {
            "composite_figi",
            "ticker",
            "cik",
            "active",
            "delisted_utc",
            "last_updated_utc",
        },
        "route_watermark": {
            "id",
            "cik",
            "route",
            "last_accepted_at",
            "updated_at",
        },
        "delisted_route_completion": {
            "id",
            "composite_figi",
            "cik",
            "route",
            "delisted_utc_snapshot",
            "last_seen_accepted_at",
            "is_completed",
            "completed_at",
            "updated_at",
        },
        "filing_document": {
            "accession_no",
            "cik",
            "ticker",
            "form_type",
            "filed_at",
            "accepted_at",
            "period_end",
            "is_amendment",
            "amendment_no",
            "created_at",
        },
        "extracted_fact": {
            "id",
            "accession_no",
            "route",
            "field_name",
            "value_numeric",
            "value_text",
            "value_json",
            "value_unit",
            "confidence",
            "extracted_at",
        },
        "extraction_evidence": {
            "id",
            "accession_no",
            "route",
            "field_name",
            "locator_kind",
            "source_section",
            "source_item_no",
            "source_xpath",
            "xbrl_concept",
            "source_span",
            "raw_value",
            "normalized_value",
            "created_at",
        },
        "pipeline_log": {
            "id",
            "run_id",
            "route",
            "cik",
            "accession_no",
            "stage",
            "level",
            "message",
            "error_type",
            "created_at",
        },
        "review_task": {
            "task_id",
            "accession_no",
            "route",
            "field_name",
            "status",
            "priority",
            "assignee",
            "created_at",
            "resolved_at",
        },
        "review_decision": {
            "id",
            "task_id",
            "decision",
            "corrected_value_json",
            "comment",
            "reviewer",
            "decided_at",
        },
    }

    for table_name, required in expected_columns.items():
        columns = set(Base.metadata.tables[table_name].columns.keys())
        assert required.issubset(columns), f"{table_name} missing required columns"


def test_extracted_fact_unique_constraint_on_accession_route_field_name():
    from src.db.base import Base
    import src.db.models  # noqa: F401

    extracted_fact = Base.metadata.tables["extracted_fact"]

    assert ("accession_no", "route", "field_name") in _unique_key_columns(extracted_fact)


def test_route_watermark_unique_constraint_on_cik_route():
    from src.db.base import Base
    import src.db.models  # noqa: F401

    route_watermark = Base.metadata.tables["route_watermark"]

    assert ("cik", "route") in _unique_key_columns(route_watermark)


def test_delisted_route_completion_unique_constraint_on_figi_cik_route():
    from src.db.base import Base
    import src.db.models  # noqa: F401

    delisted_route_completion = Base.metadata.tables["delisted_route_completion"]

    assert ("composite_figi", "cik", "route") in _unique_key_columns(delisted_route_completion)


def test_value_numeric_annotation_and_column_type_are_float():
    from src.db.base import Base
    from src.db.models import ExtractedFact

    extracted_fact = Base.metadata.tables["extracted_fact"]

    assert _mapped_annotation(ExtractedFact, "value_numeric") == float | None
    assert isinstance(extracted_fact.c.value_numeric.type, Float)


def test_datetime_annotations_are_python_datetime_types():
    from src.db.models import (
        DelistedRouteCompletion,
        FilingDocument,
        SecurityMaster,
    )

    assert _mapped_annotation(SecurityMaster, "last_updated_utc") == datetime
    assert _mapped_annotation(SecurityMaster, "delisted_utc") == datetime | None
    assert _mapped_annotation(FilingDocument, "accepted_at") == datetime | None
    assert _mapped_annotation(DelistedRouteCompletion, "updated_at") == datetime


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
