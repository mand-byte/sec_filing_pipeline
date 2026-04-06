from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
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
from src.pipeline.offline_artifacts import write_run_artifacts
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


def _load_run_once_securities(session: Any) -> list[SecurityMaster]:
    return list(session.scalars(select(SecurityMaster)).all())


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

    return [bundle for bundle in bundles if isinstance(bundle, FilingBundle)]


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

    engine = NumericExtractionEngine()
    route_specs = tuple(spec for spec in all_numeric_field_specs() if spec.route == route)

    bundles: list[FilingBundle] = []
    for envelope in envelopes:
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

        for spec in route_specs:
            if form_family not in spec.form_families:
                continue

            outcome = engine.extract_field(filing=envelope.filing, field_spec=spec)
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

    last_seen_accepted_at = watermark
    if eligible_bundles:
        processed_bundles: list[FilingBundle] = []
        for bundle in eligible_bundles:
            try:
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
                samples=sample_payload,
                diff_markdown=diff_markdown,
            )


@app.command("run-once")
def run_once() -> None:
    """Run the phase-1 pipeline once."""
    _run_once_pipeline()


@app.command("schedule")
def schedule() -> None:
    """Run the phase-1 scheduler loop."""
    settings = Settings()
    scheduler = build_blocking_scheduler(
        interval_minutes=settings.scheduler_interval_minutes,
        tick_callable=run_once,
    )
    scheduler.start()
