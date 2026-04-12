from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from typer.testing import CliRunner

import src.cli as cli_module
from src.db.base import Base
from src.db.models import ExtractedFact, FilingDocument, GoldenCase, GoldenSubject, GoldenTruth
from src.pipeline.truth_selection import select_preferred_truth


runner = CliRunner()


def _session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, expire_on_commit=False)


def _seed_filing(session: Session, *, accession_no: str) -> None:
    session.add(
        FilingDocument(
            accession_no=accession_no,
            cik="0000789019",
            ticker="MSFT",
            form_type="4",
            filed_at=None,
            accepted_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
            period_end=None,
            is_amendment=False,
            amendment_no=None,
            created_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
        )
    )


def test_select_preferred_truth_returns_parsed_fact_when_manual_truth_missing() -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_filing(session, accession_no="0000000000-24-000030")
        session.add(
            ExtractedFact(
                accession_no="0000000000-24-000030",
                route="owner",
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                value_numeric=100.0,
                value_text=None,
                value_json=None,
                value_unit="shares",
                confidence=0.99,
                extracted_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
            )
        )
        session.commit()

    with factory() as session:
        preferred = select_preferred_truth(
            session=session,
            accession_no="0000000000-24-000030",
            route="owner",
            field_name="shares_acquired_or_disposed",
            subject_key="txn:1",
        )

    assert preferred is not None
    assert preferred.source == "parsed"
    assert preferred.value_numeric == 100.0
    assert preferred.value_unit == "shares"


def test_select_preferred_truth_prefers_manual_review_ground_truth() -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_filing(session, accession_no="0000000000-24-000031")
        session.add(
            ExtractedFact(
                accession_no="0000000000-24-000031",
                route="owner",
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                value_numeric=100.0,
                value_text=None,
                value_json=None,
                value_unit="shares",
                confidence=0.49,
                extracted_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
            )
        )
        session.add(
            GoldenCase(
                case_id="manual-review::0000000000-24-000031",
                accession_no="0000000000-24-000031",
                cik="0000789019",
                form_type="4",
                accepted_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
                truth_cutoff_at=None,
                is_amendment=False,
                amendment_no=None,
                source_accession_no="0000000000-24-000031",
                source_snapshot_hash=None,
                created_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
            )
        )
        session.flush()
        subject = GoldenSubject(
            case_id="manual-review::0000000000-24-000031",
            subject_type="transaction_row",
            subject_key="txn:1",
            parent_subject_key=None,
            ordinal=1,
            created_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
        )
        session.add(subject)
        session.flush()
        session.add(
            GoldenTruth(
                case_id="manual-review::0000000000-24-000031",
                subject_id=subject.id,
                field_name="shares_acquired_or_disposed",
                truth_tier="gold",
                truth_source="manual_review",
                is_applicable=True,
                value_numeric=Decimal("125.5"),
                value_text=None,
                value_json=None,
                value_unit="shares",
                created_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
            )
        )
        session.commit()

    with factory() as session:
        preferred = select_preferred_truth(
            session=session,
            accession_no="0000000000-24-000031",
            route="owner",
            field_name="shares_acquired_or_disposed",
            subject_key="txn:1",
        )

    assert preferred is not None
    assert preferred.source == "ground_truth"
    assert preferred.truth_source == "manual_review"
    assert preferred.value_numeric == 125.5
    assert preferred.value_unit == "shares"


def test_truth_select_cli_emits_preferred_ground_truth(monkeypatch) -> None:
    factory = _session_factory()
    with factory() as session:
        _seed_filing(session, accession_no="0000000000-24-000032")
        session.add(
            ExtractedFact(
                accession_no="0000000000-24-000032",
                route="owner",
                field_name="shares_acquired_or_disposed",
                subject_key="txn:1",
                value_numeric=100.0,
                value_text=None,
                value_json=None,
                value_unit="shares",
                confidence=0.49,
                extracted_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
            )
        )
        session.add(
            GoldenCase(
                case_id="manual-review::0000000000-24-000032",
                accession_no="0000000000-24-000032",
                cik="0000789019",
                form_type="4",
                accepted_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
                truth_cutoff_at=None,
                is_amendment=False,
                amendment_no=None,
                source_accession_no="0000000000-24-000032",
                source_snapshot_hash=None,
                created_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
            )
        )
        session.flush()
        subject = GoldenSubject(
            case_id="manual-review::0000000000-24-000032",
            subject_type="transaction_row",
            subject_key="txn:1",
            parent_subject_key=None,
            ordinal=1,
            created_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
        )
        session.add(subject)
        session.flush()
        session.add(
            GoldenTruth(
                case_id="manual-review::0000000000-24-000032",
                subject_id=subject.id,
                field_name="shares_acquired_or_disposed",
                truth_tier="gold",
                truth_source="manual_review",
                is_applicable=True,
                value_numeric=Decimal("130.0"),
                value_text=None,
                value_json=None,
                value_unit="shares",
                created_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
            )
        )
        session.commit()

    monkeypatch.setattr(cli_module, "Settings", lambda: object())
    monkeypatch.setattr(cli_module, "get_session_factory", lambda settings: factory)

    result = runner.invoke(
        cli_module.app,
        [
            "truth-select",
            "--accession-no",
            "0000000000-24-000032",
            "--route",
            "owner",
            "--field",
            "shares_acquired_or_disposed",
            "--subject-key",
            "txn:1",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["source"] == "ground_truth"
    assert payload["value_numeric"] == 130.0
