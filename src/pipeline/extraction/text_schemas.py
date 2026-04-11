from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from src.pipeline.extraction._config import extraction_config_dir


_SCALAR_TYPES = {"string", "number", "integer", "boolean"}
_CONTAINER_TYPES = {"object", "array"}
_SCHEMA_TYPES = _SCALAR_TYPES | _CONTAINER_TYPES


@dataclass(frozen=True)
class TextSchemaNode:
    type: str
    nullable: bool = False
    enum: tuple[Any, ...] = ()
    required: tuple[str, ...] = ()
    properties: Mapping[str, "TextSchemaNode"] = field(default_factory=dict)
    items: "TextSchemaNode | None" = None
    minimum: float | None = None
    maximum: float | None = None
    min_items: int | None = None
    max_items: int | None = None

    def __post_init__(self) -> None:
        normalized_type = self.type.strip()
        if normalized_type not in _SCHEMA_TYPES:
            raise ValueError(f"Unsupported text schema type: {self.type}")

        object.__setattr__(self, "type", normalized_type)
        object.__setattr__(self, "enum", tuple(self.enum))
        object.__setattr__(self, "required", tuple(str(name) for name in self.required))
        object.__setattr__(self, "properties", MappingProxyType(dict(self.properties)))

        if normalized_type == "object" and self.items is not None:
            raise ValueError("Object schema nodes cannot define array items")
        if normalized_type != "object" and self.properties:
            raise ValueError("Only object schema nodes can define properties")
        if normalized_type != "object" and self.required:
            raise ValueError("Only object schema nodes can define required keys")
        if normalized_type == "array" and self.items is None:
            raise ValueError("Array schema nodes must define items")
        if normalized_type != "array" and self.items is not None:
            raise ValueError("Only array schema nodes can define items")


@dataclass(frozen=True)
class TextSchemaDefinition:
    schema_ref: str
    schema_id: str
    version: str
    root: TextSchemaNode
    comparison_rule: str | None = None
    review_correction_shape: str | None = None


@dataclass(frozen=True)
class SchemaValidationResult:
    ok: bool
    errors: tuple[str, ...] = ()


def _schema_path(schema_ref: str) -> Path:
    normalized_ref = schema_ref.strip()
    if not normalized_ref:
        raise ValueError("schema_ref must be non-empty")

    parts = normalized_ref.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"schema_ref must be versioned like v1/schema_id: {schema_ref}")

    version, schema_id = (part.strip() for part in parts)
    if not version or not schema_id:
        raise ValueError(f"schema_ref must be versioned like v1/schema_id: {schema_ref}")
    if "/" in schema_id or "\\" in schema_id or schema_id.startswith("."):
        raise ValueError(f"schema_ref contains invalid schema_id: {schema_ref}")

    return extraction_config_dir() / "text_schemas" / version / f"{schema_id}.yaml"


def _load_schema_mapping(schema_ref: str) -> dict[str, Any]:
    path = _schema_path(schema_ref)
    if not path.exists():
        raise ValueError(f"text schema file not found for {schema_ref}: {path}")

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise ValueError(f"text schema root must be a mapping: {path}")
    return dict(payload)


def _sequence_to_tuple(value: object, *, key: str) -> tuple[Any, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{key} must be a sequence")
    return tuple(value)


def _parse_schema_node(payload: Mapping[str, Any]) -> TextSchemaNode:
    node_type_raw = payload.get("type")
    if not isinstance(node_type_raw, str) or not node_type_raw.strip():
        raise ValueError("schema node must define a non-empty type")

    node_type = node_type_raw.strip()

    properties: dict[str, TextSchemaNode] = {}
    properties_raw = payload.get("properties", {})
    if properties_raw is not None:
        if not isinstance(properties_raw, Mapping):
            raise ValueError("schema properties must be a mapping")
        for key, value in properties_raw.items():
            if not isinstance(value, Mapping):
                raise ValueError(f"schema property {key!r} must be a mapping")
            properties[str(key)] = _parse_schema_node(dict(value))

    items = None
    items_raw = payload.get("items")
    if items_raw is not None:
        if not isinstance(items_raw, Mapping):
            raise ValueError("schema items must be a mapping")
        items = _parse_schema_node(dict(items_raw))

    minimum = payload.get("minimum")
    maximum = payload.get("maximum")
    min_items = payload.get("min_items")
    max_items = payload.get("max_items")

    return TextSchemaNode(
        type=node_type,
        nullable=bool(payload.get("nullable", False)),
        enum=_sequence_to_tuple(payload.get("enum"), key="enum"),
        required=tuple(str(value) for value in _sequence_to_tuple(payload.get("required"), key="required")),
        properties=properties,
        items=items,
        minimum=float(minimum) if isinstance(minimum, (int, float)) and not isinstance(minimum, bool) else None,
        maximum=float(maximum) if isinstance(maximum, (int, float)) and not isinstance(maximum, bool) else None,
        min_items=int(min_items) if isinstance(min_items, (int, float)) and not isinstance(min_items, bool) else None,
        max_items=int(max_items) if isinstance(max_items, (int, float)) and not isinstance(max_items, bool) else None,
    )


@lru_cache(maxsize=None)
def load_text_schema(schema_ref: str) -> TextSchemaDefinition:
    payload = _load_schema_mapping(schema_ref)
    normalized_ref = schema_ref.strip()
    version, schema_id = normalized_ref.split("/", 1)
    file_schema_id = str(payload.get("schema_id", schema_id)).strip() or schema_id
    if file_schema_id != schema_id:
        raise ValueError(f"text schema id mismatch for {schema_ref}: {file_schema_id}")

    node_payload = {
        key: value
        for key, value in payload.items()
        if key not in {"schema_id", "comparison_rule", "review_correction_shape", "description"}
    }
    root = _parse_schema_node(node_payload)
    return TextSchemaDefinition(
        schema_ref=normalized_ref,
        schema_id=file_schema_id,
        version=version,
        root=root,
        comparison_rule=str(payload.get("comparison_rule")).strip() or None
        if payload.get("comparison_rule") is not None
        else None,
        review_correction_shape=str(payload.get("review_correction_shape")).strip() or None
        if payload.get("review_correction_shape") is not None
        else None,
    )


def _is_numeric(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _validate_node(*, node: TextSchemaNode, value: Any, path: str, errors: list[str]) -> None:
    if value is None:
        if node.nullable:
            return
        errors.append(f"{path}: null is not allowed")
        return

    if node.enum and value not in node.enum:
        errors.append(f"{path}: {value!r} is not in enum {node.enum!r}")
        return

    if node.type == "object":
        if not isinstance(value, Mapping):
            errors.append(f"{path}: expected object")
            return

        missing = [key for key in node.required if key not in value]
        if missing:
            errors.append(f"{path}: missing required keys {missing!r}")

        extra = sorted(str(key) for key in value.keys() if str(key) not in node.properties)
        if extra:
            errors.append(f"{path}: unexpected keys {extra!r}")

        for key, property_node in node.properties.items():
            if key not in value:
                continue
            _validate_node(node=property_node, value=value[key], path=f"{path}.{key}", errors=errors)
        return

    if node.type == "array":
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            errors.append(f"{path}: expected array")
            return
        if node.min_items is not None and len(value) < node.min_items:
            errors.append(f"{path}: expected at least {node.min_items} items")
        if node.max_items is not None and len(value) > node.max_items:
            errors.append(f"{path}: expected at most {node.max_items} items")
        if node.items is None:
            return
        for index, item in enumerate(value):
            _validate_node(node=node.items, value=item, path=f"{path}[{index}]", errors=errors)
        return

    if node.type == "string":
        if not isinstance(value, str):
            errors.append(f"{path}: expected string")
        return

    if node.type == "boolean":
        if not isinstance(value, bool):
            errors.append(f"{path}: expected boolean")
        return

    if node.type == "number":
        if not _is_numeric(value):
            errors.append(f"{path}: expected finite number")
            return
        numeric_value = float(value)
        if node.minimum is not None and numeric_value < node.minimum:
            errors.append(f"{path}: expected >= {node.minimum}")
        if node.maximum is not None and numeric_value > node.maximum:
            errors.append(f"{path}: expected <= {node.maximum}")
        return

    if node.type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(f"{path}: expected integer")
            return
        numeric_value = int(value)
        if node.minimum is not None and numeric_value < node.minimum:
            errors.append(f"{path}: expected >= {node.minimum}")
        if node.maximum is not None and numeric_value > node.maximum:
            errors.append(f"{path}: expected <= {node.maximum}")
        return


def validate_text_schema_value(*, schema_ref: str, value: Any) -> SchemaValidationResult:
    schema = load_text_schema(schema_ref)
    errors: list[str] = []
    _validate_node(node=schema.root, value=value, path="$", errors=errors)
    return SchemaValidationResult(ok=not errors, errors=tuple(errors))
