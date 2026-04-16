from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
import json
import traceback
from typing import Any, Callable

from src.db.repositories import PipelineRepository
from src.pipeline.edgar_provider import classify_form_family
from src.pipeline.extraction.text_registry import all_text_field_specs
from src.pipeline.review.review_gate import ReviewGateInput, evaluate_review_gate
from src.pipeline.review.stats import SqlAlchemyReviewStats
from src.pipeline.rules import is_filing_eligible, should_skip_delisted_route
from src.pipeline.services import EvidenceInput, FactInput, PersistenceService
from src.pipeline.types import FilingRecord, RouteName


@dataclass(frozen=True)
class FilingBundle:
    filing: FilingRecord
    facts: list[FactInput] = field(default_factory=list)
    evidences: list[EvidenceInput] = field(default_factory=list)


@dataclass(frozen=True)
class BundleBuildOutcome:
    bundle: FilingBundle | None
    error_detail: str | None = None
    item_present: bool = False


class _AtomicRouteStop(RuntimeError):
    """Sentinel exception used to stop a route after a hard filing failure."""


def _normalize_to_utc(value: datetime) -> datetime:
    """Normalize datetimes to UTC before routing comparisons."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _as_utc_start_of_day(start_date: date) -> datetime:
    """Convert a configured start date into the first UTC instant of that day."""
    return datetime.combine(start_date, time.min, tzinfo=timezone.utc)


def _as_utc_end_of_day(end_date: date) -> datetime:
    """Convert a configured end date into the last UTC instant of that day."""
    return datetime.combine(end_date, time.max, tzinfo=timezone.utc)


def _bundle_sort_key(bundle: FilingBundle) -> tuple[datetime, str]:
    """Sort bundles by accepted time and accession number."""
    return (_normalize_to_utc(bundle.filing.accepted_at), bundle.filing.accession_no)


def _format_exception_detail(exc: BaseException) -> str:
    """Render an exception traceback into one persisted log string."""
    return "".join(traceback.TracebackException.from_exception(exc).format()).strip()


def _route_summary_message(
    *,
    eligible_count: int,
    persisted_count: int,
    failed_count: int,
    skipped_before_watermark: int,
    skipped_ineligible: int,
) -> str:
    """Build the standard per-route summary log message."""
    return (
        "route processed: "
        f"eligible={eligible_count} "
        f"persisted={persisted_count} "
        f"failed={failed_count} "
        f"skipped_before_watermark={skipped_before_watermark} "
        f"skipped_ineligible={skipped_ineligible}"
    )


def _load_route_filing_bundles(
    *,
    security: Any,
    route: RouteName,
    start_accepted_at: datetime,
    end_accepted_at: datetime | None = None,
) -> list[FilingBundle]:
    """Load prebuilt filing bundles from a test/security fixture when available."""
    del start_accepted_at
    bundles_by_route = getattr(security, "filing_bundles_by_route", None)
    if not isinstance(bundles_by_route, dict):
        return []

    bundles = bundles_by_route.get(route, [])
    if not isinstance(bundles, list):
        return []

    normalized_end = _normalize_to_utc(end_accepted_at) if end_accepted_at is not None else None
    filtered_bundles = [bundle for bundle in bundles if isinstance(bundle, FilingBundle)]
    if normalized_end is not None:
        filtered_bundles = [
            bundle
            for bundle in filtered_bundles
            if _normalize_to_utc(bundle.filing.accepted_at) <= normalized_end
        ]

    return sorted(filtered_bundles, key=_bundle_sort_key)


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
    error_detail: str | None = None,
) -> None:
    """Write a log record while swallowing secondary logging failures."""
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
            error_detail=error_detail,
        )
    except Exception:
        pass


def _review_metric_for_gate(fact: FactInput) -> float | None:
    """Derive the scalar metric used by the review gate from one fact."""
    if isinstance(fact.value_numeric, (int, float)) and not isinstance(fact.value_numeric, bool):
        return float(fact.value_numeric)

    if isinstance(fact.value_text, str):
        text_length = len(fact.value_text.strip())
        if text_length > 0:
            return float(text_length)

    return None


def _provider_uncertainty_signal(evidence: EvidenceInput | None) -> tuple[str | None, str | None]:
    """Map provider adequacy signals to review reasons and priorities."""
    if evidence is None or not evidence.adequacy_signals_json:
        return None, None
    try:
        payload = json.loads(evidence.adequacy_signals_json)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(payload, dict):
        return None, None

    if payload.get("multiple_candidate_targets") is True:
        return "provider_multiple_candidate_targets", "high"
    if payload.get("sufficient_context") is False:
        return "provider_insufficient_context", "high"

    confidence = payload.get("confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and confidence < 0.5:
        return "provider_low_confidence", "high"
    return None, None


def _apply_review_gate_to_bundle(*, bundle: FilingBundle, route: RouteName, stats: SqlAlchemyReviewStats) -> None:
    """Apply review-gate heuristics to text facts inside one filing bundle."""
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
            provider_reason, provider_priority = _provider_uncertainty_signal(evidence)
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
            needs_review = review_decision["decision"] == "needs_review" or provider_reason is not None or (
                isinstance(fact.confidence, (int, float)) and not isinstance(fact.confidence, bool) and fact.confidence < 0.5
            )

            bundle.facts[index] = FactInput(
                field_name=fact.field_name,
                subject_key=fact.subject_key,
                value_numeric=fact.value_numeric,
                value_text=fact.value_text,
                value_json=fact.value_json,
                value_unit=fact.value_unit,
                confidence=0.49 if needs_review else (fact.confidence if fact.confidence is not None else 0.99),
                review_priority=fact.review_priority or provider_priority or review_decision["priority"],
                review_reason=fact.review_reason or provider_reason or review_decision["reason"],
            )


@dataclass(frozen=True)
class RouteProcessor:
    repo: PipelineRepository
    persistence_service: PersistenceService
    start_date: date
    provider_bundle_builder: Callable[..., list[FilingBundle]]
    end_date: date | None = None
    ignore_existing_watermarks: bool = False

    def run(self, *, security: Any, route: RouteName, run_id: str) -> None:
        """Process one security for one route, including persistence and watermarks."""
        cik = getattr(security, "cik", None)
        if cik is None:
            _safe_write_log(
                self.repo,
                run_id=run_id,
                route=route,
                stage="route",
                level="INFO",
                message="route skipped: missing cik",
            )
            return

        active_attr = getattr(security, "active", None)
        if not isinstance(active_attr, bool):
            _safe_write_log(
                self.repo,
                run_id=run_id,
                route=route,
                cik=cik,
                stage="route",
                level="INFO",
                message="route skipped: invalid active flag",
            )
            return
        active = active_attr
        composite_figi = getattr(security, "composite_figi", None)
        delisted_utc = getattr(security, "delisted_utc", None)

        completion = None
        if composite_figi is not None:
            completion = self.repo.get_delisted_route_completion(
                composite_figi=composite_figi,
                cik=cik,
                route=route,
            )

        if active and completion is not None and bool(getattr(completion, "is_completed", False)):
            try:
                self.repo.invalidate_delisted_route_completion(
                    composite_figi=composite_figi,
                    cik=cik,
                    route=route,
                )
            except Exception as exc:
                _safe_write_log(
                    self.repo,
                    run_id=run_id,
                    route=route,
                    cik=cik,
                    stage="persist",
                    level="ERROR",
                    message="delisted completion invalidation failed",
                    error_type=exc.__class__.__name__,
                    error_detail=_format_exception_detail(exc),
                )
            completion = None

        if should_skip_delisted_route(
            active=active,
            is_completed=bool(getattr(completion, "is_completed", False)),
            snapshot=getattr(completion, "delisted_utc_snapshot", None),
            current_delisted_utc=delisted_utc,
        ):
            _safe_write_log(
                self.repo,
                run_id=run_id,
                route=route,
                cik=cik,
                stage="route",
                level="INFO",
                message="route skipped: delisted route already completed",
            )
            return

        watermark = self.repo.get_route_watermark(cik, route)
        configured_start_accepted_at = _as_utc_start_of_day(self.start_date)
        configured_end_accepted_at = _as_utc_end_of_day(self.end_date) if self.end_date is not None else None
        start_accepted_at = configured_start_accepted_at if self.ignore_existing_watermarks else (watermark or configured_start_accepted_at)

        prebuilt_bundles = _load_route_filing_bundles(
            security=security,
            route=route,
            start_accepted_at=start_accepted_at,
            end_accepted_at=configured_end_accepted_at,
        )
        normalized_start = _normalize_to_utc(start_accepted_at)
        skipped_before_watermark = 0
        skipped_ineligible = 0
        eligible_bundles = 0
        persisted_bundles = 0
        failed_bundles = 0
        last_seen_accepted_at = watermark
        review_stats = SqlAlchemyReviewStats(self.repo.session)

        def _process_bundle(bundle: FilingBundle) -> bool:
            nonlocal skipped_before_watermark
            nonlocal skipped_ineligible
            nonlocal eligible_bundles
            nonlocal persisted_bundles
            nonlocal failed_bundles
            nonlocal last_seen_accepted_at

            accepted_at = _normalize_to_utc(bundle.filing.accepted_at)
            if accepted_at <= normalized_start:
                skipped_before_watermark += 1
                return True
            if configured_end_accepted_at is not None and accepted_at > configured_end_accepted_at:
                return True
            if not is_filing_eligible(active=active, delisted_utc=delisted_utc, accepted_at=accepted_at):
                skipped_ineligible += 1
                return True

            eligible_bundles += 1
            try:
                self.repo.upsert_filing_attempt(
                    run_id=run_id,
                    route=route,
                    accession_no=bundle.filing.accession_no,
                    cik=cik,
                    accepted_at=bundle.filing.accepted_at,
                    status="in_progress",
                )
                _apply_review_gate_to_bundle(bundle=bundle, route=route, stats=review_stats)
                self.persistence_service.persist_filing_bundle(
                    filing=bundle.filing,
                    route=route,
                    facts=bundle.facts,
                    evidences=bundle.evidences,
                )
                self.repo.upsert_filing_attempt(
                    run_id=run_id,
                    route=route,
                    accession_no=bundle.filing.accession_no,
                    cik=cik,
                    accepted_at=bundle.filing.accepted_at,
                    status="completed",
                )
                persisted_bundles += 1
                _safe_write_log(
                    self.repo,
                    run_id=run_id,
                    route=route,
                    cik=cik,
                    accession_no=bundle.filing.accession_no,
                    stage="persist",
                    level="INFO",
                    message="filing persisted",
                )
                try:
                    self.repo.upsert_route_watermark(cik=cik, route=route, accepted_at=accepted_at)
                    last_seen_accepted_at = accepted_at
                except Exception as exc:
                    _safe_write_log(
                        self.repo,
                        run_id=run_id,
                        route=route,
                        cik=cik,
                        stage="persist",
                        level="ERROR",
                        message="watermark update failed",
                        error_type=exc.__class__.__name__,
                        error_detail=_format_exception_detail(exc),
                    )
                return True
            except Exception as exc:
                failed_bundles += 1
                try:
                    self.repo.session.rollback()
                except Exception:
                    pass
                try:
                    self.repo.upsert_filing_attempt(
                        run_id=run_id,
                        route=route,
                        accession_no=bundle.filing.accession_no,
                        cik=cik,
                        accepted_at=bundle.filing.accepted_at,
                        status="failed",
                        error_type=exc.__class__.__name__,
                        error_detail=_format_exception_detail(exc),
                    )
                except Exception:
                    pass
                _safe_write_log(
                    self.repo,
                    run_id=run_id,
                    route=route,
                    cik=cik,
                    accession_no=bundle.filing.accession_no,
                    stage="persist",
                    level="ERROR",
                    message="filing persistence failed",
                    error_type=exc.__class__.__name__,
                    error_detail=_format_exception_detail(exc),
                )
                return False

        if prebuilt_bundles:
            for bundle in sorted(prebuilt_bundles, key=_bundle_sort_key):
                if not _process_bundle(bundle):
                    break
        else:
            streamed_bundle_count = 0

            def _stream_bundle(bundle: FilingBundle) -> None:
                nonlocal streamed_bundle_count
                streamed_bundle_count += 1
                if not _process_bundle(bundle):
                    raise _AtomicRouteStop()

            try:
                streamed_result = self.provider_bundle_builder(
                    security=security,
                    route=route,
                    start_accepted_at=start_accepted_at,
                    end_accepted_at=configured_end_accepted_at,
                    repo=self.repo,
                    run_id=run_id,
                    on_bundle=_stream_bundle,
                )
                if streamed_bundle_count == 0 and isinstance(streamed_result, list):
                    for bundle in sorted(streamed_result, key=_bundle_sort_key):
                        if not _process_bundle(bundle):
                            break
            except TypeError as exc:
                if "on_bundle" not in str(exc):
                    _safe_write_log(
                        self.repo,
                        run_id=run_id,
                        route=route,
                        cik=cik,
                        stage="extract",
                        level="ERROR",
                        message="provider bundle build failed",
                        error_type=exc.__class__.__name__,
                        error_detail=_format_exception_detail(exc),
                    )
                else:
                    try:
                        fallback_bundles = self.provider_bundle_builder(
                            security=security,
                            route=route,
                            start_accepted_at=start_accepted_at,
                            end_accepted_at=configured_end_accepted_at,
                            repo=self.repo,
                            run_id=run_id,
                        )
                    except Exception as inner_exc:
                        _safe_write_log(
                            self.repo,
                            run_id=run_id,
                            route=route,
                            cik=cik,
                            stage="extract",
                            level="ERROR",
                            message="provider bundle build failed",
                            error_type=inner_exc.__class__.__name__,
                            error_detail=_format_exception_detail(inner_exc),
                        )
                        fallback_bundles = []
                    for bundle in sorted(fallback_bundles, key=_bundle_sort_key):
                        if not _process_bundle(bundle):
                            break
            except _AtomicRouteStop:
                pass
            except Exception as exc:
                _safe_write_log(
                    self.repo,
                    run_id=run_id,
                    route=route,
                    cik=cik,
                    stage="extract",
                    level="ERROR",
                    message="provider bundle build failed",
                    error_type=exc.__class__.__name__,
                    error_detail=_format_exception_detail(exc),
                )

        _safe_write_log(
            self.repo,
            run_id=run_id,
            route=route,
            cik=cik,
            stage="route",
            level="INFO",
            message=_route_summary_message(
                eligible_count=eligible_bundles,
                persisted_count=persisted_bundles,
                failed_count=failed_bundles,
                skipped_before_watermark=skipped_before_watermark,
                skipped_ineligible=skipped_ineligible,
            ),
        )

        if (not active) and composite_figi is not None:
            try:
                self.repo.mark_delisted_route_completed(
                    composite_figi=composite_figi,
                    cik=cik,
                    route=route,
                    delisted_utc_snapshot=delisted_utc,
                    last_seen_accepted_at=last_seen_accepted_at,
                )
            except Exception as exc:
                _safe_write_log(
                    self.repo,
                    run_id=run_id,
                    route=route,
                    cik=cik,
                    stage="persist",
                    level="ERROR",
                    message="delisted completion update failed",
                    error_type=exc.__class__.__name__,
                    error_detail=_format_exception_detail(exc),
                )
