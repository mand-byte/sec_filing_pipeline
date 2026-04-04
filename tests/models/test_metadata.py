from src.domain.enums import (
    FallbackReason,
    ParseAttemptStatus,
    ParseFailureType,
    ReviewReason,
)
from src.models import Base  # noqa: F401
from src.models import filing, parse_route_log, registry, review, state  # noqa: F401


def test_models_base_module_is_importable():
    from src.models.base import Base as BaseFromModule

    assert BaseFromModule is Base


def test_metadata_contains_required_phase0_tables():
    table_names = set(Base.metadata.tables)

    assert {
        "ingestion_state",
        "filing_index",
        "filing_document",
        "extracted_fact",
        "review_queue",
        "parser_registry",
        "model_registry",
    } <= table_names


def test_ingestion_state_primary_key_is_cik_plus_route_type():
    table = Base.metadata.tables["ingestion_state"]
    primary_key_names = {column.name for column in table.primary_key.columns}

    assert primary_key_names == {"cik", "route_type"}


def test_phase3_enums_match_fixed_taxonomy() -> None:
    assert {item.value for item in ParseFailureType} == {"network", "parse", "logic"}
    assert {item.value for item in ParseAttemptStatus} == {
        "success",
        "failed",
        "skipped",
    }
    assert {item.value for item in FallbackReason} == {
        "structured_xml_exception",
        "structured_xml_missing_mandatory",
        "structured_xml_numeric_invalid",
        "structured_xml_empty_value",
        "deterministic_rule_exception",
        "deterministic_rule_not_applicable",
        "all_methods_failed",
    }


def test_review_reason_taxonomy_covers_owner_phase_a1() -> None:
    assert {
        "mandatory_field_missing",
        "source_conflict",
        "amendment_conflict",
        "parser_disagreement",
        "unsupported_layout",
        "low_confidence",
    } <= {item.value for item in ReviewReason}


def test_owner_fact_and_review_tables_expose_traceability_columns() -> None:
    fact_table = Base.metadata.tables["extracted_fact"]
    review_table = Base.metadata.tables["review_queue"]

    assert {"cik", "document_id", "run_id", "fallback_reason"} <= set(
        fact_table.columns.keys()
    )
    assert {
        "filing_id",
        "document_id",
        "run_id",
        "parser_method",
        "decision_state",
    } <= set(review_table.columns.keys())


def test_owner_phase_a1_traceability_columns_are_nullable_for_now() -> None:
    fact_table = Base.metadata.tables["extracted_fact"]
    review_table = Base.metadata.tables["review_queue"]

    assert fact_table.columns["cik"].nullable is True
    assert fact_table.columns["document_id"].nullable is True
    assert fact_table.columns["run_id"].nullable is True
    assert review_table.columns["filing_id"].nullable is True
    assert review_table.columns["document_id"].nullable is True
    assert review_table.columns["run_id"].nullable is True
    assert review_table.columns["decision_state"].nullable is True


def test_parse_route_log_table_has_required_columns() -> None:
    table = Base.metadata.tables["parse_route_log"]
    expected = {
        "id",
        "run_id",
        "route_type",
        "filing_id",
        "accession_no",
        "cik",
        "document_id",
        "document_type",
        "document_filename",
        "document_path",
        "snapshot_path",
        "source_url",
        "sha256_hex",
        "byte_length",
        "parser_method",
        "attempted_at_utc",
        "status",
        "failure_type",
        "error_message",
        "fallback_reason",
        "decision_state",
        "selected_candidate",
    }
    assert expected <= set(table.columns.keys())
    assert {column.name for column in table.primary_key.columns} == {"id"}

    index_names = {index.name for index in table.indexes}
    assert {
        "ix_parse_route_log_doc_type_attempted",
        "ix_parse_route_log_failure_attempted",
        "ix_parse_route_log_timeline",
    } <= index_names

    check_names = {constraint.name for constraint in table.constraints}
    assert {
        "ck_parse_route_log_failed_requires_failure_and_error",
        "ck_parse_route_log_success_has_no_failure_type",
    } <= check_names
