from __future__ import annotations

from pathlib import Path
from typing import Any


def migration_dir() -> Path:
    return Path(__file__).resolve().parent / "migrations"


def migration_readme_path() -> Path:
    return migration_dir() / "README.md"


def migration_asset_paths() -> list[Path]:
    return sorted(
        path
        for path in migration_dir().glob("*.sql")
        if path.is_file()
    )


def describe_rollout_assets() -> dict[str, Any]:
    readme_path = migration_readme_path()
    instructions = None
    if readme_path.exists():
        instructions = readme_path.read_text(encoding="utf-8").strip()

    return {
        "migration_dir": str(migration_dir()),
        "readme_path": str(readme_path),
        "instructions": instructions,
        "migrations": [
            {
                "name": path.name,
                "path": str(path),
            }
            for path in migration_asset_paths()
        ],
    }
