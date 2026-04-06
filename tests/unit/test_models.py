from sqlalchemy import UniqueConstraint


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

    assert ("accession_no", "route", "field_name") in unique_key_columns
