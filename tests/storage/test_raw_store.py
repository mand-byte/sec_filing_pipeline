import hashlib
from pathlib import Path

import pytest

from src.storage.raw_store import RawArtifact, RawStore


def test_persist_document_writes_to_deterministic_documents_path(
    tmp_path: Path,
) -> None:
    store = RawStore(tmp_path)
    content = b"<xml>ownership-doc</xml>"
    artifact = RawArtifact(
        cik="0000320193",
        accession_no="0000320193-26-000001",
        filename="ownership.xml",
        content_type="text/xml",
        content=content,
    )

    stored = store.persist_document(artifact)

    expected_sha = hashlib.sha256(content).hexdigest()
    expected_path = (
        tmp_path
        / artifact.cik
        / artifact.accession_no
        / "documents"
        / f"{expected_sha}.xml"
    )

    assert stored.sha256_hex == expected_sha
    assert len(stored.sha256_hex) == 64
    assert stored.byte_length == len(content)
    assert stored.path == expected_path
    assert stored.path.parent == (
        tmp_path / artifact.cik / artifact.accession_no / "documents"
    )
    assert stored.path.read_bytes() == content


def test_persist_text_snapshot_writes_snapshot_with_suffix_and_content(
    tmp_path: Path,
) -> None:
    store = RawStore(tmp_path)

    path = store.persist_text_snapshot(
        cik="0000320193",
        accession_no="0000320193-26-000001",
        filename="filing-summary",
        suffix="txt",
        content="owner filing summary",
    )

    expected_path = (
        tmp_path
        / "0000320193"
        / "0000320193-26-000001"
        / "snapshots"
        / "filing-summary.txt"
    )

    assert path == expected_path
    assert path.suffix == ".txt"
    assert path.read_text(encoding="utf-8") == "owner filing summary"


@pytest.mark.parametrize(
    "invalid_cik", ["", ".", "..", "/abs", "bad/value", r"bad\\value"]
)
def test_persist_document_rejects_invalid_cik(tmp_path: Path, invalid_cik: str) -> None:
    store = RawStore(tmp_path)
    artifact = RawArtifact(
        cik=invalid_cik,
        accession_no="0000320193-26-000001",
        filename="ownership.xml",
        content_type="text/xml",
        content=b"document",
    )

    with pytest.raises(ValueError):
        store.persist_document(artifact)


@pytest.mark.parametrize(
    "invalid_accession_no", ["", ".", "..", "/abs", "bad/value", r"bad\\value"]
)
def test_persist_text_snapshot_rejects_invalid_accession_no(
    tmp_path: Path,
    invalid_accession_no: str,
) -> None:
    store = RawStore(tmp_path)

    with pytest.raises(ValueError):
        store.persist_text_snapshot(
            cik="0000320193",
            accession_no=invalid_accession_no,
            filename="filing-summary",
            suffix="txt",
            content="owner filing summary",
        )
