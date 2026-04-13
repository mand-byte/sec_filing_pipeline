from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import inspect
import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, TypedDict, cast

from src.pipeline.edgar_provider import classify_form_family
from src.pipeline.extraction.contracts import LocatorKind, NumericFieldSpec, ValueType
from src.pipeline.extraction.locators import run_locator_chain


class ExtractionOk(TypedDict, total=False):
    status: Literal["ok"]
    value_raw: str | float | int
    value_normalized: float | int
    locator_kind: LocatorKind
    locator_path: str
    xbrl_concept: str
    source_span: str
    source_xpath: str
    selection_trace_json: str


class ExtractionFailure(TypedDict):
    status: Literal["error"]
    error_code: str


ExtractionOutcome = ExtractionOk | ExtractionFailure

MAX_XBRL_RECORDS = 500


class NumericExtractionEngine:
    def __init__(self) -> None:
        """Create a numeric extraction engine with per-filing XBRL caching."""
        self._xbrl_cache: dict[int, tuple[bool, object | None]] = {}

    def _get_zero_arg_method(self, target: object, name: str) -> Any:
        """Return a bound zero-argument method when the target exposes one safely."""
        candidate = getattr(target, name, None)
        if not callable(candidate):
            return None

        try:
            inspect.signature(candidate).bind()
        except (TypeError, ValueError):
            return None

        return cast(Any, candidate)

    def _call_quietly(self, method: Any) -> object:
        """Call a provider method without leaking stdout or stderr noise."""
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return method()

    def _load_xbrl_once(self, filing: object) -> tuple[object | None, bool]:
        """Load the filing's XBRL payload once and cache both payload and failures."""
        filing_key = id(filing)
        cached = self._xbrl_cache.get(filing_key)
        if cached is not None:
            had_error, payload = cached
            return payload, had_error

        xbrl_method = self._get_zero_arg_method(filing, "xbrl")
        if xbrl_method is None:
            return None, False

        try:
            xbrl = self._call_quietly(xbrl_method)
        except Exception:
            self._xbrl_cache[filing_key] = (True, None)
            return None, True

        self._xbrl_cache[filing_key] = (False, xbrl)
        return xbrl, False

    def _normalize_number(self, value: object, value_type: ValueType) -> float | int:
        """Normalize one raw numeric candidate into the field's target value type."""
        if isinstance(value, bool):
            raise TypeError("boolean is not a numeric extraction value")

        if isinstance(value, (int, float, Decimal)):
            numeric = float(value)
        elif isinstance(value, str):
            cleaned = value.strip().replace(",", "")
            if cleaned == "":
                raise ValueError("empty numeric string")
            numeric = float(cleaned)
        else:
            raise TypeError("unsupported numeric value type")

        if not math.isfinite(numeric):
            raise ValueError("non-finite numeric value")

        if value_type == "int":
            if not numeric.is_integer():
                raise ValueError("non-integer value for int field")
            return int(numeric)

        return numeric

    def _qa_check(self, value: float | int, qa_rules: Mapping[str, float | int | bool]) -> str | None:
        """Apply numeric QA constraints to a normalized candidate value."""
        min_rule = qa_rules.get("min")
        if isinstance(min_rule, (int, float)) and not isinstance(min_rule, bool) and value < float(min_rule):
            return "VALUE_OUT_OF_RANGE"

        max_rule = qa_rules.get("max")
        if isinstance(max_rule, (int, float)) and not isinstance(max_rule, bool) and value > float(max_rule):
            return "VALUE_OUT_OF_RANGE"

        if qa_rules.get("nonnegative") is True and value < 0:
            return "VALUE_OUT_OF_RANGE"

        return None

    def _normalized_form_family(self, form_type: object) -> str | None:
        """Normalize the filing form into the downstream form-family key."""
        if not isinstance(form_type, str):
            return None

        normalized = classify_form_family(form_type)
        return normalized or None

    def _record_get(self, record: Mapping[str, Any], *keys: str) -> Any:
        """Return the first present field among a record's schema aliases."""
        for key in keys:
            if key in record:
                return record[key]
        return None

    def _normalize_concept(self, concept: object) -> str | None:
        """Normalize concept names for case-insensitive comparisons."""
        if not isinstance(concept, str):
            return None

        cleaned = concept.strip()
        if not cleaned:
            return None

        if ":" in cleaned:
            cleaned = cleaned.split(":", 1)[1]
        return cleaned.casefold()

    def _record_concept(self, record: Mapping[str, Any]) -> str | None:
        """Read the concept/qname field from one XBRL record."""
        concept = self._record_get(record, "concept", "Concept", "qname", "name")
        if not isinstance(concept, str):
            return None
        cleaned = concept.strip()
        return cleaned or None

    def _record_statement_type(self, record: Mapping[str, Any]) -> str | None:
        """Read the statement type across record schema aliases."""
        value = self._record_get(record, "statement_type", "statementType", "statement")
        if not isinstance(value, str):
            return None
        cleaned = value.strip()
        return cleaned or None

    def _record_dimensioned(self, record: Mapping[str, Any]) -> bool:
        """Detect whether a record carries dimensional qualifiers."""
        explicit = self._record_get(record, "dimensioned", "is_dimensioned")
        if isinstance(explicit, bool):
            return explicit

        dimensions = self._record_get(record, "dimensions", "Dimensions", "dimension")
        if isinstance(dimensions, Mapping):
            return bool(dimensions)
        if isinstance(dimensions, Sequence) and not isinstance(dimensions, (str, bytes)):
            return len(dimensions) > 0
        return False

    def _coerce_date(self, value: Any) -> date | None:
        """Coerce mixed date-like values into plain `date` objects."""
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return None
            try:
                return date.fromisoformat(cleaned[:10])
            except ValueError:
                return None
        isoformat = getattr(value, "isoformat", None)
        if callable(isoformat):
            try:
                return self._coerce_date(isoformat())
            except Exception:
                return None
        return None

    def _record_period_end_date(self, record: Mapping[str, Any]) -> date | None:
        """Read the record's period end date across schema aliases."""
        return self._coerce_date(
            self._record_get(record, "period_end", "periodEnd", "end_date", "endDate")
        )

    def _record_duration_days(self, record: Mapping[str, Any]) -> int | None:
        """Compute the inclusive duration length for a duration-period record."""
        period_start = self._coerce_date(
            self._record_get(record, "period_start", "periodStart", "start_date", "startDate")
        )
        period_end = self._record_period_end_date(record)
        if period_start is None or period_end is None:
            return None
        return (period_end - period_start).days + 1

    def _record_instant_date(self, record: Mapping[str, Any]) -> date | None:
        """Read the instant/as-of date for instant-period records."""
        instant = self._coerce_date(
            self._record_get(record, "instant", "periodInstant", "as_of_date", "asOfDate")
        )
        if instant is not None:
            return instant

        period_start = self._coerce_date(
            self._record_get(record, "period_start", "periodStart", "start_date", "startDate")
        )
        period_end = self._coerce_date(
            self._record_get(record, "period_end", "periodEnd", "end_date", "endDate")
        )
        if period_start is None and period_end is not None:
            return period_end
        return None

    def _record_has_instant_period(self, record: Mapping[str, Any]) -> bool:
        """Check whether the record represents an instant period."""
        return self._record_instant_date(record) is not None

    def _record_value(self, record: Mapping[str, Any]) -> object | None:
        """Read the raw numeric value across record schema aliases."""
        value = self._record_get(record, "value", "numeric_value", "amount")
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value

    def _candidate_key(self, record: Mapping[str, Any]) -> str:
        """Build the stable identity used to dedupe and rank XBRL records."""
        for key in ("fact_key", "id", "key"):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        concept = self._record_concept(record) or "unknown"
        period_start = self._record_get(record, "period_start", "periodStart", "start_date", "startDate")
        period_end = self._record_get(record, "period_end", "periodEnd", "end_date", "endDate")
        instant = self._record_instant_date(record)
        dimensions = self._record_get(record, "dimensions", "Dimensions", "dimension")
        return f"{concept}|{period_start}|{period_end}|{instant}|{dimensions}"

    def _records_from_query_result(self, payload: object) -> list[dict[str, Any]]:
        """Normalize heterogeneous XBRL query payloads into record dictionaries."""
        if payload is None:
            return []

        if hasattr(payload, "to_dataframe") and callable(payload.to_dataframe):
            payload = payload.to_dataframe()

        if hasattr(payload, "to_dict") and callable(payload.to_dict):
            try:
                records = payload.to_dict("records")
            except TypeError:
                records = payload.to_dict(orient="records")
            if isinstance(records, list):
                return [dict(record) for record in records if isinstance(record, Mapping)]

        if isinstance(payload, Mapping):
            return [dict(payload)]

        if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
            return [dict(record) for record in payload if isinstance(record, Mapping)]

        return []

    def _query_xbrl_source(self, source: object, concepts: tuple[str, ...]) -> tuple[list[dict[str, Any]], bool]:
        """Query one XBRL source surface for concept-matched records."""
        collected: list[dict[str, Any]] = []
        had_error = False

        query_method = getattr(source, "query", None)
        if callable(query_method):
            for concept in concepts:
                try:
                    query = query_method()
                    by_concept = getattr(query, "by_concept", None)
                    if not callable(by_concept):
                        continue
                    result = by_concept(concept)
                    collected.extend(self._records_from_query_result(result))
                except Exception:
                    had_error = True

        get_facts_by_concept = getattr(source, "get_facts_by_concept", None)
        if callable(get_facts_by_concept):
            for concept in concepts:
                try:
                    result = get_facts_by_concept(concept)
                    collected.extend(self._records_from_query_result(result))
                except Exception:
                    had_error = True

        if collected:
            return collected, had_error

        try:
            return self._records_from_query_result(source), had_error
        except Exception:
            return [], True

    def _build_xbrl_search_concepts(self, field_spec: NumericFieldSpec) -> tuple[str, ...]:
        """Build the concept search list used against XBRL query surfaces."""
        search_concepts: list[str] = []
        for concept in field_spec.xbrl_concepts:
            candidates = [concept]
            if ":" in concept:
                candidates.append(concept.split(":", 1)[1])
            for candidate in candidates:
                if candidate and candidate not in search_concepts:
                    search_concepts.append(candidate)
        return tuple(search_concepts)

    def _score_xbrl_candidate(
        self,
        *,
        field_spec: NumericFieldSpec,
        record: Mapping[str, Any],
        form_family: str | None,
        preferred_instant: date | None = None,
        preferred_duration_days: int | None = None,
        preferred_period_end: date | None = None,
    ) -> int:
        """Score one XBRL record so the most plausible runtime pick sorts first."""
        score = 0

        desired_concepts = {
            self._normalize_concept(concept): index
            for index, concept in enumerate(field_spec.xbrl_concepts)
            if self._normalize_concept(concept) is not None
        }
        concept_key = self._normalize_concept(self._record_concept(record))
        if concept_key in desired_concepts:
            score += 100 - desired_concepts[concept_key] * 10

        statement_type = self._record_statement_type(record)
        if field_spec.xbrl_statement_type and statement_type == field_spec.xbrl_statement_type:
            score += 30

        if not self._record_dimensioned(record):
            score += 20

        duration_days = self._record_duration_days(record)
        if field_spec.xbrl_period_type == "instant":
            instant_date = self._record_instant_date(record)
            if instant_date is not None:
                score += 20
                if preferred_instant is not None and instant_date == preferred_instant:
                    score += 25
        elif (
            form_family == "10-Q"
            and field_spec.xbrl_duration_days_range is not None
            and duration_days is not None
        ):
            period_end_date = self._record_period_end_date(record)
            if preferred_period_end is not None and period_end_date == preferred_period_end:
                score += 15
            if preferred_duration_days is not None:
                target_days = preferred_duration_days
            else:
                preferred_days = field_spec.xbrl_preferred_duration_days
                if preferred_days:
                    target_days = min(preferred_days, key=lambda day: abs(duration_days - day))
                else:
                    min_days, max_days = field_spec.xbrl_duration_days_range
                    target_days = int((min_days + max_days) / 2)
            score += max(0, 20 - int(abs(duration_days - target_days)))

        if duration_days is not None and duration_days > 150:
            score -= 10

        return score

    def _build_xbrl_source_span(self, record: Mapping[str, Any]) -> str:
        """Summarize XBRL period and dimension metadata for persisted evidence."""
        parts: list[str] = []
        period_start = self._record_get(record, "period_start", "periodStart", "start_date", "startDate")
        period_end = self._record_get(record, "period_end", "periodEnd", "end_date", "endDate")
        instant = self._record_get(record, "instant", "periodInstant", "as_of_date", "asOfDate")
        if instant:
            parts.append(f"instant={instant}")
        if period_start or period_end:
            parts.append(f"period={period_start}->{period_end}")
        duration_days = self._record_duration_days(record)
        if duration_days is not None:
            parts.append(f"duration_days={duration_days}")
        parts.append(f"dimensioned={self._record_dimensioned(record)}")
        statement_type = self._record_statement_type(record)
        if statement_type:
            parts.append(f"statement_type={statement_type}")
        return "; ".join(parts) if parts else "xbrl-fact"

    def _extract_from_xbrl(self, *, filing: object, field_spec: NumericFieldSpec) -> dict[str, Any] | None:
        """Extract a numeric candidate from the filing's XBRL surfaces when enabled."""
        form_family = self._normalized_form_family(getattr(filing, "form", None))
        if field_spec.xbrl_enabled_form_families and form_family not in field_spec.xbrl_enabled_form_families:
            return None

        xbrl, xbrl_had_error = self._load_xbrl_once(filing)
        if xbrl_had_error:
            return {"error_code": "XBRL_QUERY_FAILED"}
        if xbrl is None:
            return None

        search_concepts = self._build_xbrl_search_concepts(field_spec)
        if not search_concepts:
            return None

        desired_concepts = {
            self._normalize_concept(concept)
            for concept in field_spec.xbrl_concepts
            if self._normalize_concept(concept) is not None
        }

        raw_records: list[dict[str, Any]] = []
        had_query_error = False
        for source in (getattr(xbrl, "facts", None), getattr(xbrl, "facts_view", None), xbrl):
            if source is None:
                continue
            if len(raw_records) >= MAX_XBRL_RECORDS:
                break
            source_records, source_had_error = self._query_xbrl_source(source, search_concepts)
            had_query_error = had_query_error or source_had_error
            remaining = MAX_XBRL_RECORDS - len(raw_records)
            raw_records.extend(source_records[:remaining])

        candidate_records: list[tuple[str, dict[str, Any]]] = []
        seen_candidate_keys: set[str] = set()
        for record in raw_records:
            concept = self._record_concept(record)
            concept_key = self._normalize_concept(concept)
            if concept_key is None or concept_key not in desired_concepts:
                continue

            statement_type = self._record_statement_type(record)
            if field_spec.xbrl_statement_type and statement_type not in {None, field_spec.xbrl_statement_type}:
                continue

            if field_spec.xbrl_prefer_dimensionless and self._record_dimensioned(record):
                continue

            if field_spec.xbrl_period_type == "instant":
                if not self._record_has_instant_period(record):
                    continue
            elif form_family == "10-Q" and field_spec.xbrl_duration_days_range is not None:
                duration_days = self._record_duration_days(record)
                if duration_days is not None:
                    min_days, max_days = field_spec.xbrl_duration_days_range
                    if duration_days < min_days or duration_days > max_days:
                        continue

            value = self._record_value(record)
            if value is None:
                continue

            candidate_key = self._candidate_key(record)
            if candidate_key in seen_candidate_keys:
                continue
            seen_candidate_keys.add(candidate_key)

            candidate_records.append((candidate_key, record))

        if not candidate_records:
            if had_query_error:
                return {"error_code": "XBRL_QUERY_FAILED"}
            return None

        preferred_instant: date | None = None
        preferred_duration_days: int | None = None
        preferred_period_end: date | None = None
        if field_spec.xbrl_period_type == "instant":
            instant_dates = [
                instant_date
                for _, record in candidate_records
                if (instant_date := self._record_instant_date(record)) is not None
            ]
            if instant_dates:
                preferred_instant = max(instant_dates)
        elif field_spec.xbrl_preferred_duration_days:
            period_end_dates = [
                period_end_date
                for _, record in candidate_records
                if (period_end_date := self._record_period_end_date(record)) is not None
            ]
            if period_end_dates:
                preferred_period_end = max(period_end_dates)
                duration_candidates = [
                    duration
                    for _, record in candidate_records
                    if self._record_period_end_date(record) == preferred_period_end
                    and (duration := self._record_duration_days(record)) is not None
                ]
                if duration_candidates:
                    preferred_duration_days = max(duration_candidates)

        candidates = [
            (
                self._score_xbrl_candidate(
                    field_spec=field_spec,
                    record=record,
                    form_family=form_family,
                    preferred_instant=preferred_instant,
                    preferred_duration_days=preferred_duration_days,
                    preferred_period_end=preferred_period_end,
                ),
                candidate_key,
                record,
            )
            for candidate_key, record in candidate_records
        ]
        candidates.sort(key=lambda item: (-item[0], item[1]))
        best_score, best_candidate_key, best_record = candidates[0]
        concept = self._record_concept(best_record)
        source_xpath = best_candidate_key
        value = self._record_value(best_record)
        return {
            "value": value,
            "raw_value": value,
            "locator_kind": "xbrl_xml",
            "locator_path": "xbrl",
            "xbrl_concept": concept,
            "source_xpath": source_xpath,
            "source_span": self._build_xbrl_source_span(best_record),
            "selection_trace_json": json.dumps(
                {
                    "candidate_count": len(candidates),
                    "selected_candidate_key": best_candidate_key,
                    "selected_score": best_score,
                    "selected_concept": concept,
                    "top_candidates": [
                        {
                            "score": score,
                            "candidate_key": candidate_key,
                            "concept": self._record_concept(record),
                        }
                        for score, candidate_key, record in candidates[:3]
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        }

    def _extract_locator_candidate(
        self,
        *,
        filing: object,
        field_spec: NumericFieldSpec,
        locator: str,
    ) -> dict[str, Any] | None:
        """Resolve one configured locator into a raw numeric candidate payload."""
        if locator == "xbrl_xml" and field_spec.xbrl_concepts:
            return self._extract_from_xbrl(filing=filing, field_spec=field_spec)
        return run_locator_chain(filing=filing, locators=(locator,))

    def extract_field(self, *, filing: object, field_spec: NumericFieldSpec) -> ExtractionOutcome:
        """Extract, normalize, and QA-check one numeric field from a filing."""
        form_family = self._normalized_form_family(getattr(filing, "form", None))
        if field_spec.xbrl_enabled_form_families and form_family not in field_spec.xbrl_enabled_form_families:
            return {"status": "error", "error_code": "FIELD_NOT_FOUND"}

        best_error = "FIELD_NOT_FOUND"

        for locator in field_spec.locators:
            locator_hit = self._extract_locator_candidate(
                filing=filing,
                field_spec=field_spec,
                locator=locator,
            )
            if locator_hit is None:
                continue
            if isinstance(locator_hit.get("error_code"), str):
                best_error = locator_hit["error_code"]
                continue

            raw_candidate: object = locator_hit.get("raw_value", locator_hit["value"])
            if isinstance(raw_candidate, dict) and "value" in raw_candidate:
                raw_candidate = raw_candidate["value"]

            if not isinstance(raw_candidate, (str, int, float, Decimal)) or isinstance(raw_candidate, bool):
                continue

            try:
                normalized = self._normalize_number(raw_candidate, field_spec.value_type)
            except (TypeError, ValueError, OverflowError):
                best_error = "TYPE_MISMATCH"
                continue

            qa_error = self._qa_check(normalized, field_spec.qa_rules)
            if qa_error is not None:
                best_error = qa_error
                continue

            result: ExtractionOk = {
                "status": "ok",
                "value_raw": raw_candidate,
                "value_normalized": normalized,
                "locator_kind": locator_hit["locator_kind"],
                "locator_path": locator_hit["locator_path"],
            }
            if isinstance(locator_hit.get("xbrl_concept"), str):
                result["xbrl_concept"] = locator_hit["xbrl_concept"]
            if isinstance(locator_hit.get("source_span"), str):
                result["source_span"] = locator_hit["source_span"]
            if isinstance(locator_hit.get("source_xpath"), str):
                result["source_xpath"] = locator_hit["source_xpath"]
            if isinstance(locator_hit.get("selection_trace_json"), str):
                result["selection_trace_json"] = locator_hit["selection_trace_json"]
            return result

        return {"status": "error", "error_code": best_error}
