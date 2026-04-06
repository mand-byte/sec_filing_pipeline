from sqlalchemy import Integer, String, UniqueConstraint


def _named_unique_constraints(table):
    unique_constraints = [
        c for c in table.constraints if isinstance(c, UniqueConstraint)
    ]
    return {
        constraint.name: tuple(column.name for column in constraint.columns)
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
    constraints = _named_unique_constraints(extracted_fact)

    assert constraints["uq_fact_accession_route_field"] == (
        "accession_no",
        "route",
        "field_name",
    )


def test_route_watermark_unique_constraint_on_cik_route():
    from src.db.base import Base
    import src.db.models  # noqa: F401

    route_watermark = Base.metadata.tables["route_watermark"]
    constraints = _named_unique_constraints(route_watermark)

    assert constraints["uq_route_watermark_cik_route"] == ("cik", "route")


def test_delisted_route_completion_unique_constraint_on_figi_cik_route():
    from src.db.base import Base
    import src.db.models  # noqa: F401

    delisted_route_completion = Base.metadata.tables["delisted_route_completion"]
    constraints = _named_unique_constraints(delisted_route_completion)

    assert constraints["uq_delisted_completion_key"] == (
        "composite_figi",
        "cik",
        "route",
    )


def test_security_master_contract_nullability_and_lengths():
    from src.db.base import Base
    import src.db.models  # noqa: F401

    security_master = Base.metadata.tables["security_master"]

    assert isinstance(security_master.c.composite_figi.type, String)
    assert security_master.c.composite_figi.type.length == 12

    assert isinstance(security_master.c.cik.type, String)
    assert security_master.c.cik.type.length == 10
    assert security_master.c.cik.nullable is False


def test_security_master_has_index_on_cik():
    from src.db.base import Base
    import src.db.models  # noqa: F401

    security_master = Base.metadata.tables["security_master"]
    index_column_sets = {
        tuple(column.name for column in index.columns)
        for index in security_master.indexes
    }

    assert ("cik",) in index_column_sets


def test_filing_document_accepted_at_is_non_nullable():
    from src.db.base import Base
    import src.db.models  # noqa: F401

    filing_document = Base.metadata.tables["filing_document"]

    assert filing_document.c.accepted_at.nullable is False


def test_extraction_evidence_required_fields_are_non_nullable():
    from src.db.base import Base
    import src.db.models  # noqa: F401

    extraction_evidence = Base.metadata.tables["extraction_evidence"]

    assert extraction_evidence.c.locator_kind.nullable is False
    assert extraction_evidence.c.source_span.nullable is False


def test_pipeline_log_run_id_route_stage_are_non_nullable():
    from src.db.base import Base
    import src.db.models  # noqa: F401

    pipeline_log = Base.metadata.tables["pipeline_log"]

    assert pipeline_log.c.run_id.nullable is False
    assert pipeline_log.c.route.nullable is False
    assert pipeline_log.c.stage.nullable is False


def test_review_task_priority_is_string_not_integer():
    from src.db.base import Base
    import src.db.models  # noqa: F401

    review_task = Base.metadata.tables["review_task"]

    assert isinstance(review_task.c.priority.type, String)
    assert not isinstance(review_task.c.priority.type, Integer)


def test_review_decision_reviewer_is_non_nullable_string_64():
    from src.db.base import Base
    import src.db.models  # noqa: F401

    review_decision = Base.metadata.tables["review_decision"]

    assert isinstance(review_decision.c.reviewer.type, String)
    assert review_decision.c.reviewer.type.length == 64
    assert review_decision.c.reviewer.nullable is False


def test_task2_selected_pk_fk_columns_use_integer_widths():
    from src.db.base import Base
    import src.db.models  # noqa: F401

    route_watermark = Base.metadata.tables["route_watermark"]
    delisted_route_completion = Base.metadata.tables["delisted_route_completion"]
    extracted_fact = Base.metadata.tables["extracted_fact"]
    review_task = Base.metadata.tables["review_task"]
    review_decision = Base.metadata.tables["review_decision"]

    assert isinstance(route_watermark.c.id.type, Integer)
    assert isinstance(delisted_route_completion.c.id.type, Integer)
    assert isinstance(extracted_fact.c.id.type, Integer)
    assert isinstance(review_task.c.task_id.type, Integer)
    assert isinstance(review_decision.c.task_id.type, Integer)
