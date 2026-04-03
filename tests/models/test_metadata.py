from src.domain.enums import FallbackReason, ParseAttemptStatus, ParseFailureType
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
