from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping

import yaml


@dataclass(frozen=True)
class BackfillCohort:
    name: str
    description: str | None
    routes: tuple[str, ...]
    tickers: tuple[str, ...]
    ciks: tuple[str, ...]


def _runtime_config_candidates(relative_path: str) -> tuple[Path, ...]:
    repo_root = Path(__file__).resolve().parents[2]
    return (
        repo_root / "configs" / "runtime" / relative_path,
        repo_root / "src" / "_bundled_configs" / "runtime" / relative_path,
    )


def _load_runtime_mapping(path: Path) -> dict[str, object]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, Mapping):
        raise ValueError(f"runtime config root must be a mapping: {path}")
    return dict(payload)


def load_backfill_cohorts(config_path: Path | None = None) -> dict[str, BackfillCohort]:
    if config_path is None:
        for candidate in _runtime_config_candidates("backfill_cohorts.yaml"):
            if candidate.exists():
                config_path = candidate
                break
    if config_path is None or not config_path.exists():
        raise ValueError("runtime backfill cohort config not found")

    payload = _load_runtime_mapping(config_path)
    cohorts_raw = payload.get("cohorts", [])
    if not isinstance(cohorts_raw, list):
        raise ValueError(f"runtime backfill cohorts must be a list: {config_path}")

    cohorts: dict[str, BackfillCohort] = {}
    for raw in cohorts_raw:
        if not isinstance(raw, Mapping):
            continue
        name = str(raw.get("name", "")).strip()
        if not name:
            continue
        description = str(raw.get("description", "")).strip() or None
        routes = tuple(str(value).strip() for value in raw.get("routes", ()) if str(value).strip())
        tickers = tuple(str(value).strip().upper() for value in raw.get("tickers", ()) if str(value).strip())
        ciks = tuple(str(value).strip() for value in raw.get("ciks", ()) if str(value).strip())
        cohorts[name] = BackfillCohort(
            name=name,
            description=description,
            routes=routes,
            tickers=tickers,
            ciks=ciks,
        )
    return cohorts
