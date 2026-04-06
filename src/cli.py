from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, cast

import typer
from sqlalchemy import func, select

from src.config import Settings
from src.db.models import PipelineLog, SecurityMaster
from src.db.repositories import PipelineRepository
from src.db.session import get_session_factory
from src.pipeline.edgar_provider import classify_form_family, fetch_filings_for_security
from src.pipeline.extraction.engine import NumericExtractionEngine
from src.pipeline.extraction.registry import all_numeric_field_specs
from src.pipeline.extraction.text_engine import TextExtractionEngine
from src.pipeline.extraction.text_registry import all_text_field_specs
from src.pipeline.review.review_gate import ReviewGateInput, evaluate_review_gate
from src.pipeline.review.stats import SqlAlchemyReviewStats
from src.pipeline.offline_artifacts import write_run_artifacts
from src.pipeline.offline_evaluator import OfflineEvalSelectors, run_offline_tier2_evaluation
from src.pipeline.routers.holding import HoldingRouter
from src.pipeline.routers.issuer import IssuerRouter
from src.pipeline.routers.owner import OwnerRouter
from src.pipeline.rules import is_filing_eligible, should_skip_delisted_route
from src.pipeline.scheduler import (
    ROUTE_ORDER,
    RouterContext,
    build_blocking_scheduler,
    make_run_id,
    ordered_routers,
    run_single_tick,
)
from src.pipeline.services import EvidenceInput, FactInput, PersistenceService
from src.pipeline.types import FilingRecord, RouteName


app = typer.Typer(help="SEC filing pipeline CLI for running phase 1 tasks.")


@dataclass(frozen=True)
class FilingBundle:
    filing: FilingRecord
    facts: list[FactInput] = field(default_factory=list)
    evidences: list[EvidenceInput] = field(default_factory=list)


def _normalize_to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _as_utc_start_of_day(start_date: date) -> datetime:
    return datetime.combine(start_date, time.min, tzinfo=timezone.utc)


def _bundle_sort_key(bundle: FilingBundle) -> tuple[datetime, str]:
    return (_normalize_to_utc(bundle.filing.accepted_at), bundle.filing.accession_no)


def _load_run_once_securities(session: Any) -> list[SecurityMaster]:
    return list(
        session.scalars(
            select(SecurityMaster).order_by(
                SecurityMaster.cik.asc(),
                SecurityMaster.composite_figi.asc(),
            )
        ).all()
    )


def _load_route_filing_bundles(
    *,
    security: Any,
    route: RouteName,
    start_accepted_at: datetime,
) -> list[FilingBundle]:
    del start_accepted_at
    bundles_by_route = getattr(security, "filing_bundles_by_route", None)
    if not isinstance(bundles_by_route, dict):
        return []

    bundles = bundles_by_route.get(route, [])
    if not isinstance(bundles, list):
        return []

    return sorted(
        [bundle for bundle in bundles if isinstance(bundle, FilingBundle)],
        key=_bundle_sort_key,
    )


def _build_bundles_from_provider(
    *,
    security: Any,
    route: RouteName,
    start_accepted_at: datetime,
    repo: PipelineRepository,
    run_id: str,
) -> list[FilingBundle]:
    envelopes = fetch_filings_for_security(
        security=security,
        route=route,
        start_accepted_at=start_accepted_at,
    )
    if not envelopes:
        return []

    numeric_engine = NumericExtractionEngine()
    text_engine = TextExtractionEngine()
    route_numeric_specs = tuple(
        sorted(
            (spec for spec in all_numeric_field_specs() if spec.route == route),
            key=lambda spec: spec.field_name,
        )
    )
    route_text_specs = tuple(
        sorted(
            (spec for spec in all_text_field_specs() if spec.route == route),
            key=lambda spec: spec.field_name,
        )
    )

    bundles: list[FilingBundle] = []
    for envelope in sorted(
        envelopes,
        key=lambda env: (_normalize_to_utc(env.accepted_at), env.accession_no),
    ):
        filing = FilingRecord(
            accession_no=envelope.accession_no,
            cik=envelope.cik,
            ticker=getattr(security, "ticker", None),
            form_type=envelope.form_type,
            filed_at=None,
            accepted_at=envelope.accepted_at,
            period_end=None,
            is_amendment=envelope.form_type.endswith("/A"),
            amendment_no=None,
        )

        facts: list[FactInput] = []
        evidences: list[EvidenceInput] = []
        form_family = classify_form_family(envelope.form_type)

        for spec in route_numeric_specs:
            if form_family not in spec.form_families:
                continue

            outcome = numeric_engine.extract_field(filing=envelope.filing, field_spec=spec)
            if outcome["status"] != "ok":
                _safe_write_log(
                    repo,
                    run_id=run_id,
                    route=route,
                    stage="extract",
                    level="ERROR",
                    message="numeric field extraction failed",
                    cik=envelope.cik,
                    accession_no=envelope.accession_no,
                    error_type=outcome["error_code"],
                )
                continue

            facts.append(
                FactInput(
                    field_name=spec.field_name,
                    value_numeric=float(outcome["value_normalized"]),
                    confidence=0.99,
                )
            )
            evidences.append(
                EvidenceInput(
                    field_name=spec.field_name,
                    locator_kind=outcome["locator_kind"],
                    source_span=outcome["locator_path"],
                    raw_value=str(outcome["value_raw"]),
                    normalized_value=str(outcome["value_normalized"]),
                )
            )

        for spec in route_text_specs:
            if form_family not in spec.form_families:
                continue

            outcome = text_engine.extract_field(filing=envelope.filing, field_spec=spec)
            if outcome["status"] != "ok":
                _safe_write_log(
                    repo,
                    run_id=run_id,
                    route=route,
                    stage="extract",
                    level="ERROR",
                    message="text field extraction failed",
                    cik=envelope.cik,
                    accession_no=envelope.accession_no,
                    error_type=outcome["error_code"],
                )
                continue

            facts.append(
                FactInput(
                    field_name=spec.field_name,
                    value_text=outcome["value_text"],
                    value_json=outcome["value_json"],
                    confidence=0.99,
                )
            )
            evidences.append(
                EvidenceInput(
                    field_name=spec.field_name,
                    locator_kind=outcome["locator_kind"],
                    source_span=outcome["source_span"],
                    source_xpath=outcome["locator_path"],
                    raw_value=outcome["value_text"],
                    normalized_value=outcome["value_text"],
                )
            )

        if not facts:
            bundles.append(
                FilingBundle(
                    filing=filing,
                    facts=[],
                    evidences=[],
                )
            )
            continue

        bundles.append(
            FilingBundle(
                filing=filing,
                facts=facts,
                evidences=evidences,
            )
        )

    return bundles


def _safe_write_log(
    repo: PipelineRepository,
    *,
    run_id: str,
    route: RouteName,
    stage: str,
    level: str,
    message: str,
    cik: str | None = None,
    accession_no: str | None = None,
    error_type: str | None = None,
) -> None:
    try:
        repo.write_log(
            run_id=run_id,
            route=route,
            stage=stage,
            level=level,
            message=message,
            cik=cik,
            accession_no=accession_no,
            error_type=error_type,
        )
    except Exception:
        pass


def _review_metric_for_gate(fact: FactInput) -> float | None:
    if isinstance(fact.value_numeric, (int, float)) and not isinstance(fact.value_numeric, bool):
        return float(fact.value_numeric)

    if isinstance(fact.value_text, str):
        text_length = len(fact.value_text.strip())
        if text_length > 0:
            return float(text_length)

    return None


def _apply_review_gate_to_bundle(*, bundle: FilingBundle, route: RouteName, stats: SqlAlchemyReviewStats) -> None:
    form_family = classify_form_family(bundle.filing.form_type)
    text_field_names = {
        spec.field_name
        for spec in all_text_field_specs()
        if spec.route == route and form_family in spec.form_families
    }
    if not text_field_names:
        return

    evidence_by_field: dict[str, EvidenceInput] = {}
    for evidence in bundle.evidences:
        if evidence.field_name not in evidence_by_field:
            evidence_by_field[evidence.field_name] = evidence

    for index, fact in enumerate(bundle.facts):
        if fact.field_name not in text_field_names:
            continue

        evidence = evidence_by_field.get(fact.field_name)
        metric = _review_metric_for_gate(fact)
        review_decision = evaluate_review_gate(
            candidate=ReviewGateInput(
                cik=bundle.filing.cik,
                route=route,
                field_name=fact.field_name,
                template_hash=evidence.source_xpath if evidence else None,
                value_numeric=metric,
            ),
            stats=stats,
        )

        bundle.facts[index] = FactInput(
            field_name=fact.field_name,
            value_numeric=fact.value_numeric,
            value_text=fact.value_text,
            value_json=fact.value_json,
            value_unit=fact.value_unit,
            confidence=0.49 if review_decision["decision"] == "needs_review" else 0.99,
            review_priority=review_decision["priority"],
            review_reason=review_decision["reason"],
        )


def _process_security_route(
    *,
    security: Any,
    route: RouteName,
    repo: PipelineRepository,
    persistence_service: PersistenceService,
    start_date: date,
    run_id: str,
) -> None:
    cik = getattr(security, "cik", None)
    if cik is None:
        return

    active_attr = getattr(security, "active", None)
    if not isinstance(active_attr, bool):
        return
    active = active_attr
    composite_figi = getattr(security, "composite_figi", None)
    delisted_utc = getattr(security, "delisted_utc", None)

    completion = None
    if composite_figi is not None:
        completion = repo.get_delisted_route_completion(
            composite_figi=composite_figi,
            cik=cik,
            route=route,
        )

    if active and completion is not None and bool(getattr(completion, "is_completed", False)):
        try:
            repo.invalidate_delisted_route_completion(
                composite_figi=composite_figi,
                cik=cik,
                route=route,
            )
        except Exception as exc:
            _safe_write_log(
                repo,
                run_id=run_id,
                route=route,
                cik=cik,
                stage="persist",
                level="ERROR",
                message="delisted completion invalidation failed",
                error_type=exc.__class__.__name__,
            )
        completion = None

    if should_skip_delisted_route(
        active=active,
        is_completed=bool(getattr(completion, "is_completed", False)),
        snapshot=getattr(completion, "delisted_utc_snapshot", None),
        current_delisted_utc=delisted_utc,
    ):
        return

    watermark = repo.get_route_watermark(cik, route)
    start_accepted_at = watermark or _as_utc_start_of_day(start_date)

    bundles = _load_route_filing_bundles(
        security=security,
        route=route,
        start_accepted_at=start_accepted_at,
    )
    if not bundles:
        bundles = _build_bundles_from_provider(
            security=security,
            route=route,
            start_accepted_at=start_accepted_at,
            repo=repo,
            run_id=run_id,
        )

    eligible_bundles: list[FilingBundle] = []
    normalized_start = _normalize_to_utc(start_accepted_at)
    for bundle in bundles:
        accepted_at = _normalize_to_utc(bundle.filing.accepted_at)
        if accepted_at <= normalized_start:
            continue
        if not is_filing_eligible(active=active, delisted_utc=delisted_utc, accepted_at=accepted_at):
            continue
        eligible_bundles.append(bundle)

    eligible_bundles.sort(key=_bundle_sort_key)

    last_seen_accepted_at = watermark
    if eligible_bundles:
        review_stats = SqlAlchemyReviewStats(repo.session)
        processed_bundles: list[FilingBundle] = []
        for bundle in eligible_bundles:
            try:
                _apply_review_gate_to_bundle(bundle=bundle, route=route, stats=review_stats)
                persistence_service.persist_filing_bundle(
                    filing=bundle.filing,
                    route=route,
                    facts=bundle.facts,
                    evidences=bundle.evidences,
                )
                processed_bundles.append(bundle)
                _safe_write_log(
                    repo,
                    run_id=run_id,
                    route=route,
                    cik=cik,
                    accession_no=bundle.filing.accession_no,
                    stage="persist",
                    level="INFO",
                    message="filing persisted",
                )
            except Exception as exc:
                try:
                    repo.session.rollback()
                except Exception:
                    pass
                _safe_write_log(
                    repo,
                    run_id=run_id,
                    route=route,
                    cik=cik,
                    accession_no=bundle.filing.accession_no,
                    stage="persist",
                    level="ERROR",
                    message="filing persistence failed",
                    error_type=exc.__class__.__name__,
                )

        if processed_bundles:
            max_accepted_at = max(
                (_normalize_to_utc(bundle.filing.accepted_at) for bundle in processed_bundles),
                key=lambda value: value,
            )
            try:
                repo.upsert_route_watermark(cik=cik, route=route, accepted_at=max_accepted_at)
                last_seen_accepted_at = max_accepted_at
            except Exception as exc:
                _safe_write_log(
                    repo,
                    run_id=run_id,
                    route=route,
                    cik=cik,
                    stage="persist",
                    level="ERROR",
                    message="watermark update failed",
                    error_type=exc.__class__.__name__,
                )

    if (not active) and composite_figi is not None:
        try:
            repo.mark_delisted_route_completed(
                composite_figi=composite_figi,
                cik=cik,
                route=route,
                delisted_utc_snapshot=delisted_utc,
                last_seen_accepted_at=last_seen_accepted_at,
            )
        except Exception as exc:
            _safe_write_log(
                repo,
                run_id=run_id,
                route=route,
                cik=cik,
                stage="persist",
                level="ERROR",
                message="delisted completion update failed",
                error_type=exc.__class__.__name__,
            )


def _build_run_artifact_payloads(*, session: Any, run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    route_rows = session.execute(
        select(PipelineLog.route, func.count())
        .where(PipelineLog.run_id == run_id, PipelineLog.stage == "persist", PipelineLog.level == "INFO")
        .group_by(PipelineLog.route)
    ).all()
    route_coverage = {route: int(count) for route, count in route_rows}

    error_rows = session.execute(
        select(PipelineLog.error_type, func.count())
        .where(PipelineLog.run_id == run_id, PipelineLog.level == "ERROR")
        .group_by(PipelineLog.error_type)
    ).all()
    error_distribution = {
        (error_type or "UNKNOWN"): int(count)
        for error_type, count in error_rows
    }

    sample_logs = session.scalars(
        select(PipelineLog)
        .where(PipelineLog.run_id == run_id)
        .order_by(PipelineLog.id.asc())
    ).all()
    samples = [
        {
            "route": row.route,
            "stage": row.stage,
            "level": row.level,
            "message": row.message,
            "cik": row.cik,
            "accession_no": row.accession_no,
            "error_type": row.error_type,
        }
        for row in sample_logs
    ]

    summary = {
        "run_id": run_id,
        "coverage": {
            "routes": route_coverage,
        },
        "errors": {
            "distribution": error_distribution,
        },
        "metrics": {
            "total_logs": len(sample_logs),
        },
    }

    diff_markdown = "# Diff\n- baseline comparison unavailable for this run"
    return summary, samples, diff_markdown


def _run_once_pipeline() -> None:
    settings = Settings()
    session_factory = get_session_factory(settings)

    router_map = {
        "issuer": IssuerRouter(),
        "owner": OwnerRouter(),
        "holding": HoldingRouter(),
    }
    routers = ordered_routers(router_map)
    typer.echo("route order: " + " -> ".join(router.name for router in routers))

    run_id = make_run_id()

    with session_factory() as session:
        repo = PipelineRepository(session)
        persistence_service = PersistenceService(session)
        securities = _load_run_once_securities(session)

        run_single_tick(
            run_id=run_id,
            securities=securities,
            routers=routers,
            repo=repo,
        )

        for security in securities:
            for route_name in ROUTE_ORDER:
                _process_security_route(
                    security=security,
                    route=cast(RouteName, route_name),
                    repo=repo,
                    persistence_service=persistence_service,
                    start_date=settings.start_date,
                    run_id=run_id,
                )

        if settings.write_offline_artifacts:
            summary_payload, sample_payload, diff_markdown = _build_run_artifact_payloads(
                session=session,
                run_id=run_id,
            )
            write_run_artifacts(
                base_dir=settings.offline_artifacts_dir,
                run_id=run_id,
                summary=summary_payload,
                by_field={},
                failures=[sample for sample in sample_payload if sample.get("level") == "ERROR"],
                candidates=sample_payload,
                diff_markdown=diff_markdown,
            )


@app.command("run-once")
def run_once() -> None:
    """Run the phase-1 pipeline once."""
    _run_once_pipeline()


@app.command("offline-eval")
def offline_eval(
    regex_config: str = typer.Option(
        "configs/tier2/regex/default.yaml",
        "--regex-config",
        help="Path to Tier2 regex config yaml",
    ),
    golden_set: str = typer.Option(
        "configs/tier2/golden_set/default.yaml",
        "--golden-set",
        help="Path to Tier2 golden set yaml",
    ),
    fixtures_dir: str = typer.Option(
        "configs/tier2/fixtures",
        "--fixtures-dir",
        help="Directory of local fixture snapshots",
    ),
    artifacts_dir: str = typer.Option(
        "artifacts/offline",
        "--artifacts-dir",
        help="Directory for offline evaluator artifacts",
    ),
    route: str | None = typer.Option(None, "--route", help="Optional route filter"),
    form_family: str | None = typer.Option(None, "--form-family", help="Optional form family filter"),
    field_name: str | None = typer.Option(None, "--field", help="Optional field filter"),
    case_id: str | None = typer.Option(None, "--case-id", help="Optional case id filter"),
    baseline: str | None = typer.Option(None, "--baseline", help="Optional baseline summary json"),
    min_pass_rate: float = typer.Option(0.95, "--min-pass-rate", help="Minimum pass rate threshold"),
) -> None:
    """Run Tier2 offline evaluator using local fixtures and golden set."""
    result = run_offline_tier2_evaluation(
        regex_config_path=Path(regex_config),
        golden_set_path=Path(golden_set),
        fixtures_dir=Path(fixtures_dir),
        artifacts_dir=Path(artifacts_dir),
        selectors=OfflineEvalSelectors(
            route=route,
            form_family=form_family,
            field_name=field_name,
            case_id=case_id,
        ),
        baseline_path=Path(baseline) if baseline else None,
        min_pass_rate=min_pass_rate,
    )
    typer.echo(f"offline run_id: {result.run_id}")
    typer.echo(
        "offline metrics: "
        + f"passed={result.summary['metrics']['passed']} "
        + f"failed={result.summary['metrics']['failed']}"
    )


@app.command("schedule")
def schedule() -> None:
    """Run the phase-1 scheduler loop."""
    settings = Settings()
    scheduler = build_blocking_scheduler(
        interval_minutes=settings.scheduler_interval_minutes,
        tick_callable=run_once,
    )
    scheduler.start()
