from dataclasses import asdict
from datetime import date, datetime, timezone
from functools import partial
import json
from pathlib import Path
from typing import Any, cast

import typer

from src.config import Settings
from src.db.rollout import apply_rollout_assets, describe_rollout_assets, dry_run_rollout_result, init_database_schema
from src.db.repositories import PipelineRepository
from src.db.session import build_engine, get_session_factory
from src.pipeline.edgar_provider import classify_form_family, fetch_filings_for_security
from src.pipeline.extraction._config import tier2_path
from src.pipeline.extraction.bundles import (
    coerce_numeric_value,
)
from src.pipeline.extraction.provider import build_bundles_from_provider
from src.pipeline.extraction.text_normalization import normalizer_from_settings
from src.pipeline.offline_artifacts import write_run_artifacts
from src.pipeline.offline_evaluator import OfflineEvalSelectors, run_offline_tier2_evaluation
from src.pipeline.golden_10q_numeric_batch import evaluate_10q_numeric_batch
from src.pipeline.runtime_verification import (
    build_run_artifact_payloads,
    verify_runtime_run as verify_runtime_run_with_session,
)
from src.pipeline.strict_v2_summary import build_strict_v2_summary
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
from src.pipeline.runtime_cohorts import load_backfill_cohorts
from src.pipeline.runtime_preflight import run_runtime_preflight
from src.pipeline.scheduler import (
    ROUTE_ORDER,
    build_blocking_scheduler,
    make_run_id,
    ordered_routers,
    run_single_tick,
)
from src.pipeline.services import PersistenceService
from src.pipeline.truth_selection import select_preferred_truth
from src.pipeline.types import FilingRecord, RouteName
from src.pipeline.universe import SecurityUniverseRow, load_security_universe


app = typer.Typer(help="SEC filing pipeline CLI for running phase 1 tasks.")


@app.command("db-rollout-assets")
def db_rollout_assets() -> None:
    """List checked-in DB rollout assets for existing-database migrations."""
    typer.echo(json.dumps(describe_rollout_assets(), ensure_ascii=False, indent=2))


@app.command("db-rollout-apply")
def db_rollout_apply(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview rollout statements without executing SQL"),
) -> None:
    """Apply checked-in rollout SQL to the configured PostgreSQL database."""
    if dry_run:
        result = dry_run_rollout_result()
    else:
        settings = Settings()
        result = apply_rollout_assets(engine=build_engine(settings), dry_run=False)
    typer.echo(json.dumps(asdict(result), ensure_ascii=False, indent=2))


@app.command("db-init")
def db_init() -> None:
    """Bootstrap the base database schema from SQLAlchemy metadata."""
    settings = Settings()
    result = init_database_schema(engine=build_engine(settings))
    typer.echo(json.dumps(asdict(result), ensure_ascii=False, indent=2))


def _coerce_numeric_value(value: object) -> float | None:
    return coerce_numeric_value(value)


def _load_run_once_securities(session: Any, settings: Settings) -> list[SecurityUniverseRow]:
    return load_security_universe(session=session, settings=settings)


def _build_run_artifact_payloads(*, session: Any, run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    return build_run_artifact_payloads(session=session, run_id=run_id)


def _build_bundles_from_provider(
    *,
    security: Any,
    route: RouteName,
    start_accepted_at: datetime,
    repo: PipelineRepository,
    run_id: str,
    settings: Settings | None = None,
) -> list[FilingBundle]:
    fetch_callable = fetch_filings_for_security
    if settings is not None:
        edgar_identity = getattr(settings, "edgar_identity", None)
        if isinstance(edgar_identity, str) and edgar_identity.strip():
            fetch_callable = partial(fetch_filings_for_security, identity=edgar_identity)
    return build_bundles_from_provider(
        security=security,
        route=route,
        start_accepted_at=start_accepted_at,
        repo=repo,
        run_id=run_id,
        fetch_filings=fetch_callable,
        text_normalizer=normalizer_from_settings(settings) if settings is not None else None,
    )


def _parse_route_name(route: str | None) -> RouteName | None:
    if route is None:
        return None

    normalized = route.strip().lower()
    if normalized not in ROUTE_ORDER:
        allowed_routes = ", ".join(ROUTE_ORDER)
        raise typer.BadParameter(f"route must be one of: {allowed_routes}")

    return cast(RouteName, normalized)


def _parse_start_date_value(start_date: str | None) -> date | None:
    if start_date is None:
        return None
    cleaned = start_date.strip()
    if not cleaned:
        return None
    try:
        return date.fromisoformat(cleaned)
    except ValueError as exc:
        raise typer.BadParameter("start_date must be YYYY-MM-DD") from exc


def _selected_routes(route: RouteName | None) -> tuple[RouteName, ...]:
    if route is None:
        return cast(tuple[RouteName, ...], ROUTE_ORDER)
    return (route,)


def _normalize_security_filters(values: list[str] | tuple[str, ...] | None, *, upper: bool = False) -> tuple[str, ...]:
    if not values:
        return ()

    normalized: list[str] = []
    for value in values:
        cleaned = str(value).strip()
        if not cleaned:
            continue
        normalized.append(cleaned.upper() if upper else cleaned)
    return tuple(normalized)


def _filter_pipeline_securities(
    *,
    securities: list[Any],
    tickers: tuple[str, ...] = (),
    ciks: tuple[str, ...] = (),
    limit: int | None = None,
) -> list[Any]:
    selected = list(securities)
    if tickers:
        ticker_set = {ticker.upper() for ticker in tickers}
        selected = [
            security
            for security in selected
            if str(getattr(security, "ticker", "")).strip().upper() in ticker_set
        ]
    if ciks:
        cik_set = {cik.strip() for cik in ciks}
        selected = [
            security
            for security in selected
            if str(getattr(security, "cik", "")).strip() in cik_set
        ]
    if limit is not None:
        selected = selected[:limit]
    return selected


def _build_runtime_run_manifest(
    *,
    run_id: str,
    mode: str,
    selected_routes: tuple[RouteName, ...],
    start_date: date,
    ignore_existing_watermarks: bool,
    tickers: tuple[str, ...],
    ciks: tuple[str, ...],
    limit: int | None,
    securities: list[Any],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "mode": mode,
        "routes": list(selected_routes),
        "start_date": start_date.isoformat(),
        "ignore_existing_watermarks": ignore_existing_watermarks,
        "filters": {
            "tickers": list(tickers),
            "ciks": list(ciks),
            "limit": limit,
        },
        "selected_security_count": len(securities),
        "selected_security_sample": [
            {
                "ticker": str(getattr(security, "ticker", "")).strip() or None,
                "cik": str(getattr(security, "cik", "")).strip() or None,
                "active": bool(getattr(security, "active", False)),
            }
            for security in securities[:20]
        ],
    }


def _run_pipeline(
    *,
    mode: str,
    route: RouteName | None = None,
    start_date_override: date | None = None,
    tickers: tuple[str, ...] = (),
    ciks: tuple[str, ...] = (),
    limit: int | None = None,
    ignore_existing_watermarks: bool = False,
) -> str:
    settings = Settings()
    session_factory = get_session_factory(settings)
    selected_routes = _selected_routes(route)
    effective_start_date = start_date_override or settings.start_date

    run_id = make_run_id()

    with session_factory() as session:
        repo = PipelineRepository(session)
        persistence_service = PersistenceService(session)
        securities = _filter_pipeline_securities(
            securities=_load_run_once_securities(session, settings),
            tickers=tickers,
            ciks=ciks,
            limit=limit,
        )
        processor = RouteProcessor(
            repo=repo,
            persistence_service=persistence_service,
            start_date=effective_start_date,
            provider_bundle_builder=partial(_build_bundles_from_provider, settings=settings),
            ignore_existing_watermarks=ignore_existing_watermarks,
        )
        router_map = {
            "issuer": IssuerRouter(processor),
            "owner": OwnerRouter(processor),
            "holding": HoldingRouter(processor),
        }
        routers = ordered_routers({route_name: router_map[route_name] for route_name in selected_routes})
        typer.echo(f"runtime run_id: {run_id}")
        typer.echo("route order: " + " -> ".join(router.name for router in routers))
        typer.echo(f"security cohort: count={len(securities)}")
        if mode == "backfill":
            typer.echo(
                "backfill mode: "
                + f"start_date={effective_start_date.isoformat()} "
                + f"ignore_existing_watermarks={ignore_existing_watermarks}"
            )

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
                manifest=_build_runtime_run_manifest(
                    run_id=run_id,
                    mode=mode,
                    selected_routes=selected_routes,
                    start_date=effective_start_date,
                    ignore_existing_watermarks=ignore_existing_watermarks,
                    tickers=tickers,
                    ciks=ciks,
                    limit=limit,
                    securities=securities,
                ),
            )
    return run_id


def _run_once_pipeline(*, route: RouteName | None = None) -> None:
    _run_pipeline(mode="run_once", route=route)


def _run_backfill_pipeline(
    *,
    route: RouteName | None = None,
    start_date: date | None = None,
    tickers: tuple[str, ...] = (),
    ciks: tuple[str, ...] = (),
    limit: int | None = None,
    ignore_existing_watermarks: bool = True,
) -> str:
    return _run_pipeline(
        mode="backfill",
        route=route,
        start_date_override=start_date,
        tickers=tickers,
        ciks=ciks,
        limit=limit,
        ignore_existing_watermarks=ignore_existing_watermarks,
    )


def _write_backfill_cohort_manifest(
    *,
    base_dir: Path,
    cohort_name: str,
    description: str | None,
    selected_routes: tuple[RouteName, ...],
    start_date: date | None,
    tickers: tuple[str, ...],
    ciks: tuple[str, ...],
    limit: int | None,
    ignore_existing_watermarks: bool,
    route_run_ids: list[dict[str, str]],
) -> Path:
    cohort_dir = base_dir / "cohorts"
    cohort_dir.mkdir(parents=True, exist_ok=True)
    manifest_run_id = make_run_id()
    manifest_path = cohort_dir / f"{cohort_name}__{manifest_run_id}.json"
    manifest_path.write_text(
        json.dumps(
            {
                "cohort_name": cohort_name,
                "description": description,
                "routes": list(selected_routes),
                "start_date": start_date.isoformat() if start_date is not None else None,
                "tickers": list(tickers),
                "ciks": list(ciks),
                "limit": limit,
                "ignore_existing_watermarks": ignore_existing_watermarks,
                "route_runs": route_run_ids,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest_path


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


@app.command("backfill")
def backfill(
    route: str | None = typer.Option(None, "--route", help="Optional route filter: issuer, owner, holding"),
    start_date: str | None = typer.Option(None, "--start-date", help="Override historical backfill start date (YYYY-MM-DD)"),
    ticker: list[str] | None = typer.Option(None, "--ticker", help="Optional ticker filter; repeatable"),
    cik: list[str] | None = typer.Option(None, "--cik", help="Optional CIK filter; repeatable"),
    limit: int | None = typer.Option(None, "--limit", min=1, help="Optional max securities after filtering"),
    ignore_existing_watermarks: bool = typer.Option(
        True,
        "--ignore-existing-watermarks/--respect-watermarks",
        help="Ignore stored route watermarks so historical filings before the current watermark can be replayed.",
    ),
) -> None:
    """Run a historical backfill cohort with optional security filters and watermark replay."""
    _run_backfill_pipeline(
        route=_parse_route_name(route),
        start_date=_parse_start_date_value(start_date),
        tickers=_normalize_security_filters(ticker, upper=True),
        ciks=_normalize_security_filters(cik),
        limit=limit,
        ignore_existing_watermarks=ignore_existing_watermarks,
    )


@app.command("backfill-cohort")
def backfill_cohort(
    cohort: str = typer.Option(..., "--cohort", help="Named backfill cohort from configs/runtime/backfill_cohorts.yaml"),
    route: str | None = typer.Option(None, "--route", help="Optional single route override: issuer, owner, holding"),
    start_date: str | None = typer.Option(None, "--start-date", help="Override historical backfill start date (YYYY-MM-DD)"),
    limit: int | None = typer.Option(None, "--limit", min=1, help="Optional max securities after cohort filtering"),
    ignore_existing_watermarks: bool = typer.Option(
        True,
        "--ignore-existing-watermarks/--respect-watermarks",
        help="Ignore stored route watermarks so historical filings before the current watermark can be replayed.",
    ),
) -> None:
    """Run a named seed cohort backfill from versioned runtime config."""
    settings = Settings()
    cohorts = load_backfill_cohorts()
    selected = cohorts.get(cohort.strip())
    if selected is None:
        available = ", ".join(sorted(cohorts))
        raise typer.BadParameter(f"unknown cohort {cohort!r}; available cohorts: {available}")

    parsed_route = _parse_route_name(route)
    selected_routes = (parsed_route,) if parsed_route is not None else cast(tuple[RouteName, ...], selected.routes or ROUTE_ORDER)
    parsed_start_date = _parse_start_date_value(start_date)
    typer.echo(
        "backfill cohort: "
        + f"{selected.name} "
        + f"tickers={','.join(selected.tickers) if selected.tickers else '-'} "
        + f"routes={','.join(selected_routes)}"
    )
    route_run_ids: list[dict[str, str]] = []
    for route_name in selected_routes:
        route_run_id = _run_backfill_pipeline(
            route=route_name,
            start_date=parsed_start_date,
            tickers=selected.tickers,
            ciks=selected.ciks,
            limit=limit,
            ignore_existing_watermarks=ignore_existing_watermarks,
        )
        route_run_ids.append({"route": route_name, "run_id": route_run_id})
    if getattr(settings, "write_offline_artifacts", False):
        manifest_path = _write_backfill_cohort_manifest(
            base_dir=settings.offline_artifacts_dir,
            cohort_name=selected.name,
            description=selected.description,
            selected_routes=selected_routes,
            start_date=parsed_start_date,
            tickers=selected.tickers,
            ciks=selected.ciks,
            limit=limit,
            ignore_existing_watermarks=ignore_existing_watermarks,
            route_run_ids=route_run_ids,
        )
        typer.echo(f"cohort manifest: {manifest_path}")


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
    phase_gates = result.summary.get("phase_gates", {})
    if isinstance(phase_gates, dict) and phase_gates:
        typer.echo(
            "strict-v2 phase-gates: "
            + f"total={phase_gates.get('total', 0)} "
            + f"passed={phase_gates.get('passed', 0)} "
            + f"failed={phase_gates.get('failed', 0)} "
            + f"skipped={phase_gates.get('skipped', 0)}"
        )


def _run_strict_v2_numeric_batch_eval(
    *,
    golden_path: str,
    snapshot_dir: str,
    artifacts_dir: str,
    min_pass_rate: float,
) -> None:
    if not 0.0 <= min_pass_rate <= 1.0:
        raise typer.BadParameter("min_pass_rate must be between 0.0 and 1.0")

    run_id = make_run_id()
    result = evaluate_10q_numeric_batch(
        golden_path=Path(golden_path),
        snapshot_dir=Path(snapshot_dir),
    )
    metrics = result.summary["metrics"]
    pass_rate = float(metrics["top1_accuracy"])
    summary = build_strict_v2_summary(
        run_id=run_id,
        selectors={
            "route": "issuer",
            "form_family": "10-Q",
            "field_name": None,
            "case_id": None,
            "mode": "numeric_batch",
        },
        coverage={
            "total_cases": int(metrics["total_batches"]),
            "total_candidates": int(metrics["total_field_checks"]),
            "gold_applicable_rows": int(metrics["total_field_checks"]),
            "silver_applicable_rows": 0,
            "invariant_rows": 0,
        },
        metrics={
            "passed": int(metrics["passed"]),
            "failed": int(metrics["failed"]),
            "pass_rate": pass_rate,
            "min_pass_rate": min_pass_rate,
            "passes_threshold": pass_rate >= min_pass_rate,
            "gold_strict_accuracy": float(metrics["top1_accuracy"]),
            "gold_coverage": float(metrics["candidate_recall"]),
            "row_selection_accuracy": float(metrics["top1_accuracy"]),
            "not_applicable_precision": 1.0,
            "silver_alignment": 0.0,
            "invariant_pass_rate": 0.0,
            "candidate_recall": float(metrics["candidate_recall"]),
            "batch_all_match_rate": float(metrics["batch_all_match_rate"]),
            "total_batches": int(metrics["total_batches"]),
            "total_field_checks": int(metrics["total_field_checks"]),
        },
        phase_gates=result.phase_gates,
    )
    write_run_artifacts(
        base_dir=Path(artifacts_dir),
        run_id=run_id,
        summary=summary,
        by_field=result.by_field,
        failures=result.failures,
        candidates=[],
        diff_markdown="# Diff\n- numeric batch mismatches captured in mismatches.ndjson" if result.failures else "# Diff\n- no failures",
        manifest={
            "run_id": run_id,
            "mode": "numeric_batch",
            "config_paths": {
                "golden_path": str(Path(golden_path)),
                "snapshot_dir": str(Path(snapshot_dir)),
            },
        },
        coverage=summary["coverage"],
        phase_gates=result.phase_gates,
        review_packets=result.review_packets,
    )
    typer.echo(f"strict-v2 run_id: {run_id}")
    typer.echo(
        "strict-v2 metrics: "
        + f"passed={summary['metrics']['passed']} "
        + f"failed={summary['metrics']['failed']} "
        + f"gold_strict_accuracy={summary['metrics']['gold_strict_accuracy']:.4f} "
        + f"silver_alignment={summary['metrics']['silver_alignment']:.4f}"
    )
    typer.echo(
        "strict-v2 phase-gates: "
        + f"total={summary['phase_gates']['total']} "
        + f"passed={summary['phase_gates']['passed']} "
        + f"failed={summary['phase_gates']['failed']} "
        + f"skipped={summary['phase_gates']['skipped']}"
    )
    failed_phase_gates = [gate for gate in result.phase_gates if gate.get("status") == "failed"]
    if failed_phase_gates:
        raise typer.Exit(code=1)
    if pass_rate < min_pass_rate:
        raise typer.Exit(code=1)


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
    numeric_batch_golden_path: str | None = typer.Option(None, "--numeric-batch-golden-path", help="Optional adjudicated 10-Q numeric batch yaml"),
    numeric_batch_snapshot_dir: str | None = typer.Option(None, "--numeric-batch-snapshot-dir", help="Optional directory of numeric batch snapshots"),
) -> None:
    """Run strict-v2 evaluation and emit the golden artifact contract."""
    if (numeric_batch_golden_path is None) ^ (numeric_batch_snapshot_dir is None):
        raise typer.BadParameter("numeric batch strict-v2 mode requires both --numeric-batch-golden-path and --numeric-batch-snapshot-dir")
    if numeric_batch_golden_path is not None and numeric_batch_snapshot_dir is not None:
        _run_strict_v2_numeric_batch_eval(
            golden_path=numeric_batch_golden_path,
            snapshot_dir=numeric_batch_snapshot_dir,
            artifacts_dir=artifacts_dir,
            min_pass_rate=min_pass_rate,
        )
        return

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
    artifacts_dir: str = typer.Option(
        "artifacts/golden",
        "--artifacts-dir",
        help="Directory for strict-v2 numeric batch artifacts",
    ),
    min_pass_rate: float = typer.Option(0.95, "--min-pass-rate", min=0.0, max=1.0, help="Minimum pass rate threshold"),
) -> None:
    """Compatibility alias that routes numeric batch adjudication through strict-v2 artifacts."""
    _run_strict_v2_numeric_batch_eval(
        golden_path=golden_path,
        snapshot_dir=snapshot_dir,
        artifacts_dir=artifacts_dir,
        min_pass_rate=min_pass_rate,
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
    strict_summary: list[str] | None = typer.Option(
        None,
        "--strict-summary",
        help="Optional strict-v2 summary.json path; repeat to require multiple evaluator summaries to pass",
    ),
    runtime_run_id: list[str] | None = typer.Option(
        None,
        "--runtime-run-id",
        help="Optional runtime run id to verify against DB/artifacts; repeat to require multiple runtime runs to verify cleanly",
    ),
    runtime_cohort_manifest: list[str] | None = typer.Option(
        None,
        "--runtime-cohort-manifest",
        help="Optional backfill cohort manifest json; repeat to require every listed route run to verify cleanly",
    ),
    runtime_artifacts_dir: Path | None = typer.Option(
        None,
        "--runtime-artifacts-dir",
        help="Optional runtime artifacts base directory; defaults to OFFLINE_ARTIFACTS_DIR when runtime run ids are provided",
    ),
) -> None:
    settings = Settings()
    with get_session_factory(settings)() as session:
        result = evaluate_fix_once_release_gate(
            session=session,
            output_dir=output_dir,
            strict_summary_paths=[Path(path) for path in strict_summary] if strict_summary else None,
            runtime_run_ids=runtime_run_id,
            runtime_artifacts_dir=(runtime_artifacts_dir or settings.offline_artifacts_dir)
            if (runtime_run_id or runtime_cohort_manifest)
            else None,
            runtime_cohort_manifests=[Path(path) for path in runtime_cohort_manifest] if runtime_cohort_manifest else None,
        )
    typer.echo(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    if not result.passed:
        raise typer.Exit(code=1)


@app.command("truth-select")
def truth_select(
    accession_no: str = typer.Option(..., "--accession-no", help="Filing accession number"),
    route: str = typer.Option(..., "--route", help="Route name: issuer, owner, holding"),
    field_name: str = typer.Option(..., "--field", help="Field name"),
    subject_key: str = typer.Option("document", "--subject-key", help="Subject key, defaults to document"),
) -> None:
    """Resolve the preferred downstream truth with ground-truth-over-parsed precedence."""
    settings = Settings()
    with get_session_factory(settings)() as session:
        preferred_truth = select_preferred_truth(
            session=session,
            accession_no=accession_no,
            route=_parse_route_name(route) or route,
            field_name=field_name,
            subject_key=subject_key,
        )
    if preferred_truth is None:
        raise typer.Exit(code=1)
    typer.echo(json.dumps(preferred_truth.asdict(), ensure_ascii=False, indent=2))


@app.command("verify-runtime-run")
def verify_runtime_run(
    run_id: str = typer.Option(..., "--run-id", help="Runtime run id to verify against DB state"),
    artifacts_dir: Path | None = typer.Option(None, "--artifacts-dir", help="Runtime artifacts base directory; defaults to OFFLINE_ARTIFACTS_DIR"),
) -> None:
    """Verify runtime run artifacts against filing_attempt and pipeline_log DB state."""
    settings = Settings()
    base_dir = artifacts_dir or settings.offline_artifacts_dir

    with get_session_factory(settings)() as session:
        result = verify_runtime_run_with_session(session=session, run_id=run_id, base_dir=base_dir)

    payload = result.__dict__
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    if not result.passed:
        raise typer.Exit(code=1)


@app.command("runtime-preflight")
def runtime_preflight() -> None:
    """Check whether the current environment is ready for real runtime/backfill evidence collection."""
    settings = Settings()
    result = run_runtime_preflight(settings=settings)
    typer.echo(json.dumps(result.asdict(), ensure_ascii=False, indent=2))
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
