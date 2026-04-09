from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from src.db.base import Base
from src.db.models import (
    GoldenCandidate,
    GoldenCase,
    GoldenEvalResult,
    GoldenEvalRun,
    GoldenSubject,
    GoldenTruth,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


def _golden_case() -> GoldenCase:
    return GoldenCase(
        case_id="case-001",
        accession_no="0000000000-24-000001",
        cik="0000789019",
        form_type="10-Q",
        accepted_at=datetime(2024, 4, 25, tzinfo=timezone.utc),
        truth_cutoff_at=datetime(2024, 4, 26, tzinfo=timezone.utc),
        is_amendment=False,
        amendment_no=None,
        source_accession_no="0000000000-24-000001",
        source_snapshot_hash="snapshot-1",
        created_at=datetime(2024, 4, 26, tzinfo=timezone.utc),
    )


def _golden_subject(case_id: str) -> GoldenSubject:
    return GoldenSubject(
        case_id=case_id,
        subject_type="filing",
        subject_key="filing",
        parent_subject_key=None,
        ordinal=None,
        created_at=datetime(2024, 4, 26, tzinfo=timezone.utc),
    )


def test_sqlalchemy_metadata_includes_all_strict_v2_tables() -> None:
    expected_tables = {
        "golden_case",
        "golden_subject",
        "golden_truth",
        "golden_invariant_result",
        "golden_candidate",
        "golden_eval_run",
        "golden_eval_result",
        "golden_review_packet",
    }

    assert expected_tables.issubset(set(Base.metadata.tables.keys()))


def test_golden_subject_enforces_case_subject_key_uniqueness(session: Session) -> None:
    session.add(_golden_case())
    session.commit()

    session.add(_golden_subject("case-001"))
    session.commit()

    session.add(_golden_subject("case-001"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_golden_truth_enforces_case_subject_field_tier_source_uniqueness(session: Session) -> None:
    case = _golden_case()
    session.add(case)
    session.commit()

    subject = _golden_subject(case.case_id)
    session.add(subject)
    session.commit()

    session.add(
        GoldenTruth(
            case_id=case.case_id,
            subject_id=subject.id,
            field_name="total_revenue",
            truth_tier="gold",
            truth_source="manual_adjudication",
            is_applicable=True,
            value_numeric=Decimal("123.4500000000"),
            value_text=None,
            value_json=None,
            value_unit="usd",
            created_at=datetime(2024, 4, 26, tzinfo=timezone.utc),
        )
    )
    session.commit()

    session.add(
        GoldenTruth(
            case_id=case.case_id,
            subject_id=subject.id,
            field_name="total_revenue",
            truth_tier="gold",
            truth_source="manual_adjudication",
            is_applicable=False,
            value_numeric=Decimal("123.4500000000"),
            value_text=None,
            value_json=None,
            value_unit="usd",
            created_at=datetime(2024, 4, 26, tzinfo=timezone.utc),
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_golden_eval_result_enforces_run_case_subject_field_uniqueness(session: Session) -> None:
    case = _golden_case()
    session.add(case)
    session.add(
        GoldenEvalRun(
            run_id="run-001",
            config_path="configs/strict_v2.yaml",
            git_sha="abc123",
            summary_json=None,
            created_at=datetime(2024, 4, 26, tzinfo=timezone.utc),
        )
    )
    session.commit()

    subject = _golden_subject(case.case_id)
    session.add(subject)
    session.commit()

    session.add(
        GoldenEvalResult(
            run_id="run-001",
            case_id=case.case_id,
            subject_id=subject.id,
            field_name="total_revenue",
            status="ok",
            matched=True,
            truth_tier="gold",
            truth_source="manual_adjudication",
            expected_value="123.45",
            actual_value="123.45",
            details_json=None,
            created_at=datetime(2024, 4, 26, tzinfo=timezone.utc),
        )
    )
    session.commit()

    session.add(
        GoldenEvalResult(
            run_id="run-001",
            case_id=case.case_id,
            subject_id=subject.id,
            field_name="total_revenue",
            status="ok",
            matched=True,
            truth_tier="gold",
            truth_source="manual_adjudication",
            expected_value="123.45",
            actual_value="123.45",
            details_json=None,
            created_at=datetime(2024, 4, 26, tzinfo=timezone.utc),
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_golden_candidate_requires_eval_run_foreign_key(session: Session) -> None:
    case = _golden_case()
    session.add(case)
    session.commit()

    subject = _golden_subject(case.case_id)
    session.add(subject)
    session.commit()

    session.add(
        GoldenCandidate(
            eval_run_id="missing-run",
            case_id=case.case_id,
            subject_id=subject.id,
            field_name="total_revenue",
            candidate_key="candidate-1",
            status="ok",
            selected=False,
            value_numeric=Decimal("123.4500000000"),
            value_text=None,
            value_json=None,
            provenance_json=None,
            created_at=datetime(2024, 4, 26, tzinfo=timezone.utc),
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
