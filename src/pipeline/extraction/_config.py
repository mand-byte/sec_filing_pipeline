from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


_REPO_CONFIG_ROOT = Path(__file__).resolve().parents[3] / "configs"
_BUNDLED_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "_bundled_configs"


def extraction_config_dir() -> Path:
    for candidate in (
        _REPO_CONFIG_ROOT / "extraction",
        _BUNDLED_CONFIG_ROOT / "extraction",
    ):
        if candidate.exists():
            return candidate
    return _REPO_CONFIG_ROOT / "extraction"


def tier2_path(*parts: str) -> Path:
    relative_path = Path(*parts)
    for root in (
        _REPO_CONFIG_ROOT / "tier2",
        _BUNDLED_CONFIG_ROOT / "tier2",
    ):
        candidate = root / relative_path
        if candidate.exists():
            return candidate
    return (_REPO_CONFIG_ROOT / "tier2") / relative_path


@lru_cache(maxsize=None)
def load_extraction_config(filename: str) -> dict[str, Any]:
    path = extraction_config_dir() / filename
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"Extraction config root must be a mapping: {path}")
    return dict(payload)
