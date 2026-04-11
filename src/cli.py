from dataclasses import asdict
from datetime import date, datetime, timezone
from functools import partial
import json
from pathlib import Path
from typing import Any, cast

import typer
from sqlalchemy import func, select

from src.config import Settings
from src.db.models import FilingAttempt, PipelineLog
from src.db.repositories import PipelineRepository
from src.db.session import get_session_factory
from src.pipeline.edgar_provider import classify_form_family, fetch_filings_for_security
from src.pipeline.extraction._config import tier2_path
from src.pipeline.extraction.bundles import (
    coerce_numeric_value,
)
from src.pipeline.extraction.provider import build_bundles_from_provider
from src.pipeline.offline_artifacts import write_run_artifacts
from src.pipeline.offline_evaluator import OfflineEvalSelectors, run_offline_tier2_evaluation
from src.pipeline.golden_10q_numeric_batch import evaluate_10q_numeric_batch
from src.pipeline.route_runtime import (
    BundleBuildOutcome,
    FilingBundle,
    RouteProcessor,
    _normalize_to_utc,
    _safe_write_log,
)
from src.pipeline.release_gates import evaluate_fix_once_release_gate
from src.pipeline.routers.holding import HoldingRouter
from src.pipeline.routers.issuer import IssuerRouter
from src.pipeline.routers.owner import OwnerRouter
from src.pipeline.review.dashboard import build_review_dashboard_packets, write_review_dashboard
from src.pipeline.review.server import ReviewServerConfig, run_review_server
from src.pipeline.review.workflow import ReviewWorkflowError, ReviewWorkflowService, review_task_detail_asdict
from src.pipeline.scheduler import (
    ROUTE_ORDER,
    build_blocking_scheduler,
    make_run_id,
    ordered_routers,
    run_single_tick,
)
from src.pipeline.services import PersistenceService
from src.pipeline.types import FilingRecord, RouteName
from src.pipeline.universe import SecurityUniverseRow, load_security_universe


app = typer.Typer(help="SEC filing pipeline CLI for running phase 1 tasks.")


def _coerce_numeric_value(value: object) -> float | None:
    return coerce_numeric_value(value)


def _load_run_once_securities(session: Any, settings: Settings) -> list[SecurityUniverseRow]:
    return load_security_universe(session=session, settings=settings)


def _build_bundles_from_provider(
    *,
    security: Any,
    route: RouteName,
    start_accepted_at: datetime,
    repo: PipelineRepository,
    run_id: str,
) -> list[FilingBundle]:
    return build_bundles_from_provider(
        security=security,
        route=route,
        start_accepted_at=start_accepted_at,
        repo=repo,
        run_id=run_id,
        fetch_filings=fetch_filings_for_security,
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

    filing_attempt_rows = session.scalars(
        select(FilingAttempt)
        .where(FilingAttempt.run_id == run_id)
        .order_by(FilingAttempt.route.asc(), FilingAttempt.accession_no.asc(), FilingAttempt.id.asc())
    ).all()
    filing_attempt_status_counts: dict[str, int] = {}
    filing_attempt_route_counts: dict[str, dict[str, int]] = {}
    for row in filing_attempt_rows:
        filing_attempt_status_counts[row.status] = filing_attempt_status_counts.get(row.status, 0) + 1
        route_status_counts = filing_attempt_route_counts.setdefault(row.route, {})
        route_status_counts[row.status] = route_status_counts.get(row.status, 0) + 1

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
            "error_detail": row.error_detail,
        }
        for row in sample_logs
    ]

    summary = {
        "run_id": run_id,
        "coverage": {
            "routes": route_coverage,
            "filing_attempts": {
                "total": len(filing_attempt_rows),
                "by_status": filing_attempt_status_counts,
                "by_route": filing_attempt_route_counts,
            },
        },
        "errors": {
            "distribution": error_distribution,
        },
        "metrics": {
            "total_logs": len(sample_logs),
            "total_filing_attempts": len(filing_attempt_rows),
        },
    }

    diff_markdown = "# Diff\n- baseline comparison unavailable for this run"
    return summary, samples, diff_markdown


def _parse_route_name(route: str | None) -> RouteName | None:
    if route is None:
        return None

    normalized = route.strip().lower()
    if normalized not in ROUTE_ORDER:
        allowed_routes = ", ".join(ROUTE_ORDER)
        raise typer.BadParameter(f"route must be one of: {allowed_routes}")

    return cast(RouteName, normalized)


def _selected_routes(route: RouteName | None) -> tuple[RouteName, ...]:
    if route is None:
        return cast(tuple[RouteName, ...], ROUTE_ORDER)
    return (route,)


def _run_once_pipeline(*, route: RouteName | None = None) -> None:
    settings = Settings()
    session_factory = get_session_factory(settings)
    selected_routes = _selected_routes(route)

    run_id = make_run_id()

    with session_factory() as session:
        repo = PipelineRepository(session)
        persistence_service = PersistenceService(session)
        securities = _load_run_once_securities(session, settings)
        processor = RouteProcessor(
            repo=repo,
            persistence_service=persistence_service,
            start_date=settings.start_date,
            provider_bundle_builder=_build_bundles_from_provider,
        )
        router_map = {
            "issuer": IssuerRouter(processor),
            "owner": OwnerRouter(processor),
            "holding": HoldingRouter(processor),
        }
        routers = ordered_routers({route_name: router_map[route_name] for route_name in selected_routes})
        typer.echo("route order: " + " -> ".join(router.name for router in routers))

        run_single_tick(
            run_id=run_id,
            securities=securities,
            routers=routers,
            repo=repo,
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
def run_once(
    route: str | None = typer.Option(None, "--route", help="Optional route filter: issuer, owner, holding"),
) -> None:
    """Run the phase-1 pipeline once."""
    _run_once_pipeline(route=_parse_route_name(route))


@app.command("run-route")
def run_route(
    route: str = typer.Argument(..., help="Route name: issuer, owner, holding"),
) -> None:
    """Run a single pipeline route once."""
    _run_once_pipeline(route=_parse_route_name(route))


@app.command("run-issuer")
def run_issuer() -> None:
    """Run the issuer route once."""
    _run_once_pipeline(route="issuer")


@app.command("run-owner")
def run_owner() -> None:
    """Run the owner route once."""
    _run_once_pipeline(route="owner")


@app.command("run-holding")
def run_holding() -> None:
    """Run the holding route once."""
    _run_once_pipeline(route="holding")


def _run_strict_v2_eval(
    *,
    regex_config: str,
    golden_set: str,
    fixtures_dir: str,
    artifacts_dir: str,
    route: str | None,
    form_family: str | None,
    field_name: str | None,
    case_id: str | None,
    baseline: str | None,
    min_pass_rate: float,
) -> None:
    if not 0.0 <= min_pass_rate <= 1.0:
        raise typer.BadParameter("min_pass_rate must be between 0.0 and 1.0")

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
    typer.echo(f"strict-v2 run_id: {result.run_id}")
    typer.echo(
        "strict-v2 metrics: "
        + f"passed={result.summary['metrics']['passed']} "
        + f"failed={result.summary['metrics']['failed']} "
        + f"gold_strict_accuracy={result.summary['metrics']['gold_strict_accuracy']:.4f} "
        + f"silver_alignment={result.summary['metrics']['silver_alignment']:.4f}"
    )


@app.command("offline-eval")
def offline_eval(
    regex_config: str = typer.Option(
        str(tier2_path("regex", "default.yaml")),
        "--regex-config",
        help="Path to Tier2 regex config yaml",
    ),
    golden_set: str = typer.Option(
        str(tier2_path("golden_set", "default.yaml")),
        "--golden-set",
        help="Path to Tier2 golden set yaml",
    ),
    fixtures_dir: str = typer.Option(
        str(tier2_path("fixtures")),
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
    min_pass_rate: float = typer.Option(0.95, "--min-pass-rate", min=0.0, max=1.0, help="Minimum pass rate threshold"),
) -> None:
    """Run Tier2 offline evaluator using local fixtures and golden set."""
    _run_strict_v2_eval(
        regex_config=regex_config,
        golden_set=golden_set,
        fixtures_dir=fixtures_dir,
        artifacts_dir=artifacts_dir,
        route=route,
        form_family=form_family,
        field_name=field_name,
        case_id=case_id,
        baseline=baseline,
        min_pass_rate=min_pass_rate,
    )


@app.command("strict-v2-eval")
def strict_v2_eval(
    regex_config: str = typer.Option(
        str(tier2_path("regex", "default.yaml")),
        "--regex-config",
        help="Path to strict-v2 regex config yaml",
    ),
    golden_set: str = typer.Option(
        str(tier2_path("golden_set", "default.yaml")),
        "--golden-set",
        help="Path to strict-v2 golden set yaml",
    ),
    fixtures_dir: str = typer.Option(
        str(tier2_path("fixtures")),
        "--fixtures-dir",
        help="Directory of local strict-v2 fixture snapshots",
    ),
    artifacts_dir: str = typer.Option(
        "artifacts/golden",
        "--artifacts-dir",
        help="Directory for strict-v2 artifacts",
    ),
    route: str | None = typer.Option(None, "--route", help="Optional route filter"),
    form_family: str | None = typer.Option(None, "--form-family", help="Optional form family filter"),
    field_name: str | None = typer.Option(None, "--field", help="Optional field filter"),
    case_id: str | None = typer.Option(None, "--case-id", help="Optional case id filter"),
    baseline: str | None = typer.Option(None, "--baseline", help="Optional baseline summary json"),
    min_pass_rate: float = typer.Option(0.95, "--min-pass-rate", min=0.0, max=1.0, help="Minimum pass rate threshold"),
) -> None:
    """Run strict-v2 evaluation and emit the golden artifact contract."""
    _run_strict_v2_eval(
        regex_config=regex_config,
        golden_set=golden_set,
        fixtures_dir=fixtures_dir,
        artifacts_dir=artifacts_dir,
        route=route,
        form_family=form_family,
        field_name=field_name,
        case_id=case_id,
        baseline=baseline,
        min_pass_rate=min_pass_rate,
    )


@app.command("golden-10q-numeric-batch")
def golden_10q_numeric_batch(
    golden_path: str = typer.Option(
        ...,
        "--golden-path",
        help="Path to the adjudicated 10-Q numeric batch golden set",
    ),
    snapshot_dir: str = typer.Option(
        ...,
        "--snapshot-dir",
        help="Directory containing batch_001 candidate snapshots",
    ),
) -> None:
    result = evaluate_10q_numeric_batch(
        golden_path=Path(golden_path),
        snapshot_dir=Path(snapshot_dir),
    )
    metrics = result.summary["metrics"]
    typer.echo(
        "golden metrics: "
        + f"batches={metrics['total_batches']} "
        + f"field_checks={metrics['total_field_checks']} "
        + f"candidate_recall={metrics['candidate_recall']} "
        + f"top1_accuracy={metrics['top1_accuracy']} "
        + f"batch_all_match_rate={metrics['batch_all_match_rate']}"
    )
    for field_name, field_metrics in result.by_field.items():
        typer.echo(
            "field "
            + f"{field_name}: "
            + f"candidate_recall={field_metrics['candidate_recall']} "
            + f"top1_accuracy={field_metrics['top1_accuracy']}"
        )


@app.command("review-list")
def review_list(
    status: str = typer.Option("open", "--status", help="Review task status filter"),
    route: str | None = typer.Option(None, "--route", help="Optional route filter"),
    limit: int = typer.Option(100, "--limit", min=1, max=1000, help="Maximum tasks to return"),
) -> None:
    settings = Settings()
    with get_session_factory(settings)() as session:
        service = ReviewWorkflowService(session)
        payload = [
            {
                **asdict(task),
                "created_at": task.created_at.isoformat(),
            }
            for task in service.list_tasks(status=status, route=route, limit=limit)
        ]
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@app.command("review-show")
def review_show(
    task_id: int = typer.Argument(..., help="Review task id"),
) -> None:
    settings = Settings()
    with get_session_factory(settings)() as session:
        service = ReviewWorkflowService(session)
        try:
            detail = service.get_task_detail(task_id=task_id)
        except ReviewWorkflowError as exc:
            raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(review_task_detail_asdict(detail), ensure_ascii=False, indent=2))


@app.command("review-assign")
def review_assign(
    task_id: int = typer.Argument(..., help="Review task id"),
    assignee: str = typer.Argument(..., help="Assignee name"),
) -> None:
    settings = Settings()
    with get_session_factory(settings)() as session:
        service = ReviewWorkflowService(session)
        try:
            summary = service.assign_task(task_id=task_id, assignee=assignee)
        except ReviewWorkflowError as exc:
            raise typer.BadParameter(str(exc)) from exc
    typer.echo(
        json.dumps(
            {
                "task_id": summary.task_id,
                "status": summary.status,
                "assignee": summary.assignee,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("review-resolve")
def review_resolve(
    task_id: int = typer.Argument(..., help="Review task id"),
    decision: str = typer.Option(..., "--decision", help="accept, corrected, reject, not_applicable"),
    reviewer: str = typer.Option(..., "--reviewer", help="Reviewer name"),
    error_code: str | None = typer.Option(None, "--error-code", help="Normalized extraction failure class for non-accept decisions"),
    comment: str | None = typer.Option(None, "--comment", help="Optional review comment"),
    corrected_json: str | None = typer.Option(None, "--corrected-json", help="JSON payload for corrected decisions"),
) -> None:
    settings = Settings()
    with get_session_factory(settings)() as session:
        service = ReviewWorkflowService(session)
        try:
            summary = service.resolve_task(
                task_id=task_id,
                decision=decision,
                reviewer=reviewer,
                error_code=error_code,
                comment=comment,
                corrected_json=corrected_json,
            )
        except ReviewWorkflowError as exc:
            raise typer.BadParameter(str(exc)) from exc
    typer.echo(
        json.dumps(
            {
                "task_id": summary.task_id,
                "status": summary.status,
                "assignee": summary.assignee,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("review-dashboard")
def review_dashboard(
    status: str = typer.Option("open", "--status", help="Review task status filter"),
    route: str | None = typer.Option(None, "--route", help="Optional route filter"),
    limit: int = typer.Option(100, "--limit", min=1, max=1000, help="Maximum tasks to export"),
    output_dir: Path = typer.Option(
        Path("artifacts/review_dashboard"),
        "--output-dir",
        help="Directory for the exported review dashboard",
    ),
) -> None:
    settings = Settings()
    with get_session_factory(settings)() as session:
        service = ReviewWorkflowService(session)
        packets = build_review_dashboard_packets(
            service=service,
            status=status,
            route=route,
            limit=limit,
        )
    dashboard_dir = write_review_dashboard(output_dir=output_dir, packets=packets)
    typer.echo(str(dashboard_dir))


@app.command("review-serve")
def review_serve(
    status: str = typer.Option("open", "--status", help="Review task status filter"),
    route: str | None = typer.Option(None, "--route", help="Optional route filter"),
    limit: int = typer.Option(100, "--limit", min=1, max=1000, help="Maximum tasks to expose"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host interface to bind"),
    port: int = typer.Option(8765, "--port", min=1, max=65535, help="Port to bind"),
) -> None:
    settings = Settings()
    session_factory = get_session_factory(settings)
    typer.echo(f"http://{host}:{port}")
    run_review_server(
        session_factory=session_factory,
        config=ReviewServerConfig(
            host=host,
            port=port,
            status=status,
            route=route,
            limit=limit,
        ),
    )


@app.command("release-gate")
def release_gate(
    output_dir: Path = typer.Option(
        Path("artifacts/release_gate"),
        "--output-dir",
        help="Directory for exported fix-once regression packets and summary",
    ),
) -> None:
    settings = Settings()
    with get_session_factory(settings)() as session:
        result = evaluate_fix_once_release_gate(session=session, output_dir=output_dir)
    typer.echo(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    if not result.passed:
        raise typer.Exit(code=1)


@app.command("schedule")
def schedule(
    route: str | None = typer.Option(None, "--route", help="Optional route filter: issuer, owner, holding"),
) -> None:
    """Run the phase-1 scheduler loop."""
    settings = Settings()
    parsed_route = _parse_route_name(route)
    scheduler = build_blocking_scheduler(
        interval_minutes=settings.scheduler_interval_minutes,
        tick_callable=partial(_run_once_pipeline, route=parsed_route),
    )
    scheduler.start()


if __name__ == "__main__":
    app()
