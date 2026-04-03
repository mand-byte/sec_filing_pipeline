from dataclasses import dataclass
import hashlib
from pathlib import Path


@dataclass(frozen=True)
class RawArtifact:
    cik: str
    accession_no: str
    filename: str
    content_type: str
    content: bytes


@dataclass(frozen=True)
class StoredArtifact:
    path: Path
    sha256_hex: str
    byte_length: int


class RawStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    @staticmethod
    def _validate_path_component(value: str, field_name: str) -> str:
        if value in {"", ".", ".."}:
            raise ValueError(f"Invalid {field_name}: {value!r}")
        if "/" in value or "\\" in value:
            raise ValueError(f"Invalid {field_name}: {value!r}")
        if Path(value).is_absolute():
            raise ValueError(f"Invalid {field_name}: {value!r}")
        return value

    def persist_document(self, artifact: RawArtifact) -> StoredArtifact:
        cik = self._validate_path_component(artifact.cik, "cik")
        accession_no = self._validate_path_component(
            artifact.accession_no, "accession_no"
        )
        sha256_hex = hashlib.sha256(artifact.content).hexdigest()
        suffix = Path(artifact.filename).suffix or ".bin"
        documents_dir = self.root / cik / accession_no / "documents"
        documents_dir.mkdir(parents=True, exist_ok=True)
        path = documents_dir / f"{sha256_hex}{suffix}"
        path.write_bytes(artifact.content)

        return StoredArtifact(
            path=path,
            sha256_hex=sha256_hex,
            byte_length=len(artifact.content),
        )

    def persist_text_snapshot(
        self,
        *,
        cik: str,
        accession_no: str,
        filename: str,
        suffix: str,
        content: str,
    ) -> Path:
        normalized_cik = self._validate_path_component(cik, "cik")
        normalized_accession_no = self._validate_path_component(
            accession_no, "accession_no"
        )
        snapshots_dir = (
            self.root / normalized_cik / normalized_accession_no / "snapshots"
        )
        snapshots_dir.mkdir(parents=True, exist_ok=True)

        stem = Path(filename).stem
        normalized_suffix = suffix[1:] if suffix.startswith(".") else suffix
        path = snapshots_dir / f"{stem}.{normalized_suffix}"
        path.write_text(content, encoding="utf-8")
        return path
