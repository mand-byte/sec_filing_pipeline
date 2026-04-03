from src.models import Base  # noqa: F401
from src.models import filing, registry, review, state  # noqa: F401


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
