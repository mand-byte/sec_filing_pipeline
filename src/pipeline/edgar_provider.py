from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from src.pipeline.extraction.registry import all_numeric_field_specs
from src.pipeline.extraction.text_registry import all_text_field_specs


@dataclass(frozen=True)
class FilingEnvelope:
    accession_no: str
    cik: str
    form_type: str
    accepted_at: datetime
    filing: Any
    filed_at: datetime | None = None
    period_end: datetime | None = None
    amendment_no: int | None = None


def classify_form_family(form_type: str) -> str:
    normalized = form_type.strip().upper()
    if normalized.startswith("SC 13D") or normalized.startswith("SCHEDULE 13D"):
        return "13D"
    if normalized.startswith("SC 13G") or normalized.startswith("SCHEDULE 13G"):
        return "13G"
    if normalized.endswith("/A") and normalized not in {"13F-HR/A"}:
        return normalized[:-2]
    return normalized


def _route_forms(route: str) -> tuple[str, ...]:
    if route == "owner":
        base_forms = {
            "3",
            "4",
            "5",
            "13D",
            "13G",
            "SC 13D",
            "SC 13G",
            "SCHEDULE 13D",
            "SCHEDULE 13G",
            "144",
        }
    else:
        base_forms = {
            form
            for spec in all_numeric_field_specs()
            if spec.route == route
            for form in spec.form_families
        }
        base_forms.update(
            {
                form
                for spec in all_text_field_specs()
                if spec.route == route
                for form in spec.form_families
            }
        )

    forms = set(base_forms)
    forms.update(
        form if form.endswith("/A") else f"{form}/A"
        for form in base_forms
    )
    return tuple(sorted(forms))


def _normalize_to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _coerce_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return _normalize_to_utc(value)

    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)

    if isinstance(value, str):
        cleaned = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(cleaned)
        except ValueError:
            return None
        return _normalize_to_utc(parsed)

    return None


def _first_datetime_attribute(target: object, *names: str) -> datetime | None:
    for name in names:
        value = getattr(target, name, None)
        coerced = _coerce_datetime(value)
        if coerced is not None:
            return coerced
    return None


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.isdigit():
            return int(cleaned)
    return None


def _first_int_attribute(target: object, *names: str) -> int | None:
    for name in names:
        value = getattr(target, name, None)
        coerced = _coerce_int(value)
        if coerced is not None:
            return coerced
    return None


def _filing_storage_day(*, filed_at: datetime | None, accepted_at: datetime) -> str:
    effective_filing_date = filed_at or accepted_at
    return _normalize_to_utc(effective_filing_date).strftime("%Y%m%d")


def _local_filing_exists(*, local_data_dir: Path, filing_day: str, accession_no: str) -> bool:
    final_dir = local_data_dir / "filings" / filing_day
    if (final_dir / f"{accession_no}.nc").exists():
        return True
    if (final_dir / f"{accession_no}.nc.gz").exists():
        return True
    return False


def _store_filtered_filings_locally(
    *,
    filings: Any,
    envelopes: list[FilingEnvelope],
    local_data_dir: Path,
) -> None:
    target_accession_to_day = {
        envelope.accession_no: _filing_storage_day(
            filed_at=envelope.filed_at,
            accepted_at=envelope.accepted_at,
        )
        for envelope in envelopes
        if not _local_filing_exists(
            local_data_dir=local_data_dir,
            filing_day=_filing_storage_day(
                filed_at=envelope.filed_at,
                accepted_at=envelope.accepted_at,
            ),
            accession_no=envelope.accession_no,
        )
    }
    if not target_accession_to_day:
        return

    filtered_filings = filings
    filter_method = getattr(filings, "filter", None)
    if callable(filter_method):
        try:
            filtered_filings = filter_method(accession_number=list(target_accession_to_day))
        except Exception:
            filtered_filings = filings

    from edgar.storage import download_filings as download_filings_to_storage

    with tempfile.TemporaryDirectory(dir=str(local_data_dir), prefix="filing_stage_") as tmp_dir:
        staging_root = Path(tmp_dir)
        download_filings_to_storage(
            filings=filtered_filings,
            data_directory=staging_root,
            overwrite_existing=False,
            disable_progress=True,
        )
        for accession_no, filing_day in target_accession_to_day.items():
            staged_dir = staging_root / filing_day
            if not staged_dir.exists():
                continue
            final_dir = local_data_dir / "filings" / filing_day
            final_dir.mkdir(parents=True, exist_ok=True)
            for suffix in (".nc.gz", ".nc"):
                staged_path = staged_dir / f"{accession_no}{suffix}"
                if not staged_path.exists():
                    continue
                final_path = final_dir / staged_path.name
                if final_path.exists():
                    break
                shutil.move(str(staged_path), str(final_path))
                break


def fetch_filings_for_security(
    *,
    security: Any,
    route: str,
    start_accepted_at: datetime,
    end_accepted_at: datetime | None = None,
    identity: str | None = None,
    download_filings_to_local: bool = False,
    local_data_dir: str | Path | None = None,
) -> list[FilingEnvelope]:
    forms = _route_forms(route)
    if not forms:
        return []

    cik = getattr(security, "cik", None)
    if cik is None:
        return []

    try:
        import edgar
    except Exception:
        return []
    Company = getattr(edgar, "Company", None)
    if Company is None:
        return []
    set_identity = getattr(edgar, "set_identity", None)

    effective_identity = (identity or os.environ.get("EDGAR_IDENTITY") or "").strip()
    if effective_identity and callable(set_identity):
        set_identity(effective_identity)

    if download_filings_to_local:
        resolved_local_data_dir = Path(local_data_dir or Path.home() / ".edgar").expanduser().resolve()
        resolved_local_data_dir.mkdir(parents=True, exist_ok=True)
        os.environ["EDGAR_USE_LOCAL_DATA"] = "1"
        os.environ["EDGAR_LOCAL_DATA_DIR"] = str(resolved_local_data_dir)
        use_local_storage = getattr(edgar, "use_local_storage", None)
        if callable(use_local_storage):
            use_local_storage(str(resolved_local_data_dir))

    try:
        company = Company(str(cik))
        filings = company.get_filings(form=list(forms))
    except Exception as exc:
        raise RuntimeError(f"edgar fetch failed for cik={cik} route={route}: {exc}") from exc

    start_utc = _normalize_to_utc(start_accepted_at)
    end_utc = _normalize_to_utc(end_accepted_at) if end_accepted_at is not None else None
    envelopes: list[FilingEnvelope] = []

    for filing in filings:
        accession_no = getattr(filing, "accession_no", None)
        if not isinstance(accession_no, str) or accession_no == "":
            continue

        form_type = getattr(filing, "form", None)
        if not isinstance(form_type, str) or form_type == "":
            continue

        accepted_raw = getattr(filing, "acceptance_datetime", None)
        if accepted_raw is None:
            accepted_raw = getattr(filing, "filing_date", None)

        accepted_at = _coerce_datetime(accepted_raw)
        if accepted_at is None:
            continue

        if accepted_at <= start_utc:
            continue
        if end_utc is not None and accepted_at > end_utc:
            continue

        filed_at = _first_datetime_attribute(
            filing,
            "filing_date",
            "filed_at",
            "filed_date",
        )
        period_end = _first_datetime_attribute(
            filing,
            "period_of_report",
            "period_end",
            "period",
            "report_period",
            "report_date",
        )
        amendment_no = _first_int_attribute(
            filing,
            "amendment_no",
            "amendment_number",
        )

        envelopes.append(
            FilingEnvelope(
                accession_no=accession_no,
                cik=str(cik),
                form_type=form_type,
                accepted_at=accepted_at,
                filing=filing,
                filed_at=filed_at,
                period_end=period_end,
                amendment_no=amendment_no,
            )
        )

    envelopes.sort(key=lambda envelope: envelope.accepted_at)

    if download_filings_to_local and envelopes:
        try:
            _store_filtered_filings_locally(
                filings=filings,
                envelopes=envelopes,
                local_data_dir=resolved_local_data_dir,
            )
        except Exception:
            pass

    return envelopes
