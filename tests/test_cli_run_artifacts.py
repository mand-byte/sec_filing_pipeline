from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import src.cli as cli_module
from src.db.base import Base
from src.db.models import FilingAttempt, PipelineLog


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False)()


def test_build_run_artifact_payloads_includes_structured_filing_attempt_coverage() -> None:
    session = _session()
    now = datetime(2024, 5, 1, tzinfo=timezone.utc)

    session.add_all(
        [
            PipelineLog(
                run_id="run-001",
                route="issuer",
                cik="0000789019",
                accession_no="0000000000-24-000001",
                stage="persist",
                level="INFO",
                message="filing persisted",
                error_type=None,
                error_detail=None,
                created_at=now,
            ),
            PipelineLog(
                run_id="run-001",
                route="owner",
                cik="0000789019",
                accession_no="0000000000-24-000002",
                stage="persist",
                level="ERROR",
                message="filing persistence failed",
                error_type="RuntimeError",
                error_detail="boom",
                created_at=now,
            ),
            FilingAttempt(
                run_id="run-001",
                route="issuer",
                accession_no="0000000000-24-000001",
                cik="0000789019",
                accepted_at=now,
                status="completed",
                error_type=None,
                error_detail=None,
                started_at=now,
                updated_at=now,
            ),
            FilingAttempt(
                run_id="run-001",
                route="owner",
                accession_no="0000000000-24-000002",
                cik="0000789019",
                accepted_at=now,
                status="failed",
                error_type="RuntimeError",
                error_detail="boom",
                started_at=now,
                updated_at=now,
            ),
        ]
    )
    session.commit()

    summary, samples, diff_markdown = cli_module._build_run_artifact_payloads(session=session, run_id="run-001")

    assert summary["coverage"]["routes"] == {"issuer": 1}
    assert summary["coverage"]["filing_attempts"]["total"] == 2
    assert summary["coverage"]["filing_attempts"]["by_status"] == {"completed": 1, "failed": 1}
    assert summary["coverage"]["filing_attempts"]["by_route"] == {
        "issuer": {"completed": 1},
        "owner": {"failed": 1},
    }
    assert summary["errors"]["distribution"] == {"RuntimeError": 1}
    assert summary["metrics"]["total_logs"] == 2
    assert summary["metrics"]["total_filing_attempts"] == 2
    assert len(samples) == 2
    assert diff_markdown.startswith("# Diff")
