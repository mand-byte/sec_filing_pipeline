from __future__ import annotations

from pathlib import Path
import subprocess
import tarfile
import zipfile


def test_build_artifacts_include_db_migration_assets(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--out-dir", str(dist_dir)],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
    )

    migration_name = "20260411_add_evidence_locator_and_filing_attempt.sql"
    wheel_path = next(dist_dir.glob("*.whl"))
    sdist_path = next(dist_dir.glob("*.tar.gz"))

    with zipfile.ZipFile(wheel_path) as wheel:
        matches = [name for name in wheel.namelist() if name.endswith(migration_name)]
        assert matches == [f"src/db/migrations/{migration_name}"]

    with tarfile.open(sdist_path, "r:gz") as sdist:
        matches = [name for name in sdist.getnames() if name.endswith(migration_name)]
        assert len(matches) == 1
