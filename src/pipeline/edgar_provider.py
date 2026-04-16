from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
import os
from pathlib import Path
from typing import Any, Iterator

from src.config import (
    EDGAR_DOWNLOAD_FILINGS_FLAG_CLOUD,
    EDGAR_DOWNLOAD_FILINGS_FLAG_DISABLED,
    EDGAR_DOWNLOAD_FILINGS_FLAG_LOCAL,
)
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
    """Normalize SEC form strings into the form-family keys used downstream."""
    normalized = form_type.strip().upper()
    if normalized.startswith("SC 13D") or normalized.startswith("SCHEDULE 13D"):
        return "13D"
    if normalized.startswith("SC 13G") or normalized.startswith("SCHEDULE 13G"):
        return "13G"
    if normalized.endswith("/A") and normalized not in {"13F-HR/A"}:
        return normalized[:-2]
    return normalized


def _route_forms(route: str) -> tuple[str, ...]:
    """Return the set of filing forms relevant to one pipeline route."""
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
    """Normalize datetimes to UTC before comparing filing timestamps."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _coerce_datetime(value: object) -> datetime | None:
    """Coerce mixed filing metadata date values into UTC datetimes."""
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
    """Return the first datetime-like attribute that can be coerced successfully."""
    for name in names:
        try:
            value = getattr(target, name, None)
        except Exception:
            continue
        coerced = _coerce_datetime(value)
        if coerced is not None:
            return coerced
    return None


def _coerce_int(value: object) -> int | None:
    """Coerce integer-like values while rejecting booleans and non-integral floats."""
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
    """Return the first integer-like attribute that can be coerced successfully."""
    for name in names:
        try:
            value = getattr(target, name, None)
        except Exception:
            continue
        coerced = _coerce_int(value)
        if coerced is not None:
            return coerced
    return None


def _filing_storage_day(*, filed_at: datetime | None, accepted_at: datetime) -> str:
    """Choose the YYYYMMDD storage bucket for one filing artifact."""
    effective_filing_date = filed_at or accepted_at
    return _normalize_to_utc(effective_filing_date).strftime("%Y%m%d")


def _load_full_submission_text(filing: object) -> tuple[str | None, bool]:
    """Read the full submission text, falling back to a fresh download when cached access fails."""
    full_text_method = getattr(filing, "full_text_submission", None)
    if callable(full_text_method):
        try:
            content = full_text_method()
        except Exception:
            content = None
        if isinstance(content, str) and content:
            return content, False

    text_url = getattr(filing, "text_url", None)
    if not isinstance(text_url, str) or not text_url:
        return None, False

    try:
        from edgar.httprequests import download_file

        downloaded = download_file(text_url, as_text=True)
    except Exception:
        return None, False

    if isinstance(downloaded, str) and downloaded:
        return downloaded, True
    return None, False


def _store_filtered_filings(
    *,
    envelopes: list[FilingEnvelope],
    local_data_dir: Path,
    route: str | None = None,
    repo: object | None = None,
    use_cloud_storage: bool = False,
) -> None:
    """Persist newly fetched filing text into the configured local or cloud EDGAR storage."""
    for envelope in envelopes:
        if route is not None and repo is not None:
            is_completed = getattr(repo, "is_filing_completed", None)
            if callable(is_completed):
                try:
                    if is_completed(route=route, accession_no=envelope.accession_no):
                        continue
                except Exception:
                    pass

        filing_day = _filing_storage_day(
            filed_at=envelope.filed_at,
            accepted_at=envelope.accepted_at,
        )

        content, downloaded_via_fallback = _load_full_submission_text(envelope.filing)
        if not isinstance(content, str) or not content:
            continue

        if use_cloud_storage:
            try:
                from edgar.filesystem import EdgarPath
            except Exception:
                continue
            final_path = EdgarPath("filings", filing_day, f"{envelope.accession_no}.nc")
            if final_path.exists() and not downloaded_via_fallback:
                continue
            final_path.write_text(content, encoding="utf-8")
        else:
            final_dir = local_data_dir / "filings" / filing_day
            final_dir.mkdir(parents=True, exist_ok=True)
            final_path = final_dir / f"{envelope.accession_no}.nc"
            if final_path.exists() and not downloaded_via_fallback:
                continue
            final_path.write_text(content, encoding="utf-8")


def _configure_edgar_storage(
    *,
    edgar_module: object,
    filing_storage_mode: int,
    local_data_dir: str | Path | None,
    cloud_uri: str | None,
    cloud_endpoint_url: str | None,
    cloud_access_id: str | None,
    cloud_access_key: str | None,
) -> tuple[bool, bool, Path]:
    """Configure edgartools storage backends and report effective persistence settings."""
    should_persist_filings = filing_storage_mode != EDGAR_DOWNLOAD_FILINGS_FLAG_DISABLED
    persist_to_cloud = filing_storage_mode == EDGAR_DOWNLOAD_FILINGS_FLAG_CLOUD
    resolved_local_data_dir = Path(local_data_dir or Path.home() / ".edgar").expanduser().resolve()

    if not should_persist_filings:
        return False, False, resolved_local_data_dir

    if persist_to_cloud:
        if not isinstance(cloud_uri, str) or not cloud_uri.strip():
            raise RuntimeError("cloud filing persistence requires cloud_uri")
        use_cloud_storage_fn = getattr(edgar_module, "use_cloud_storage", None)
        if callable(use_cloud_storage_fn):
            client_kwargs: dict[str, str] = {}
            if isinstance(cloud_endpoint_url, str) and cloud_endpoint_url.strip():
                client_kwargs["endpoint_url"] = cloud_endpoint_url.strip()
            if isinstance(cloud_access_id, str) and cloud_access_id.strip():
                client_kwargs["aws_access_key_id"] = cloud_access_id.strip()
            if isinstance(cloud_access_key, str) and cloud_access_key.strip():
                client_kwargs["aws_secret_access_key"] = cloud_access_key.strip()
            use_cloud_storage_fn(
                cloud_uri.strip(),
                client_kwargs=client_kwargs or None,
                verify=False,
            )
        return True, True, resolved_local_data_dir

    if filing_storage_mode == EDGAR_DOWNLOAD_FILINGS_FLAG_LOCAL:
        resolved_local_data_dir.mkdir(parents=True, exist_ok=True)
        os.environ["EDGAR_USE_LOCAL_DATA"] = "1"
        os.environ["EDGAR_LOCAL_DATA_DIR"] = str(resolved_local_data_dir)
        use_local_storage = getattr(edgar_module, "use_local_storage", None)
        if callable(use_local_storage):
            use_local_storage(str(resolved_local_data_dir))
        return True, False, resolved_local_data_dir

    raise RuntimeError(f"unsupported filing_storage_mode={filing_storage_mode}")


def _collect_filing_envelopes(
    *,
    company: object,
    cik: object,
    forms: tuple[str, ...],
    start_accepted_at: datetime,
    end_accepted_at: datetime | None = None,
) -> list[FilingEnvelope]:
    """Fetch and normalize filing envelopes for one company/route window."""
    filings = company.get_filings(form=list(forms))
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
    return envelopes


def iter_filings_for_security(
    *,
    security: Any,
    route: str,
    start_accepted_at: datetime,
    end_accepted_at: datetime | None = None,
    identity: str | None = None,
    filing_storage_mode: int = EDGAR_DOWNLOAD_FILINGS_FLAG_DISABLED,
    local_data_dir: str | Path | None = None,
    repo: object | None = None,
    cloud_uri: str | None = None,
    cloud_endpoint_url: str | None = None,
    cloud_access_id: str | None = None,
    cloud_access_key: str | None = None,
) -> Iterator[FilingEnvelope]:
    """Yield filing envelopes in accepted-time order, preparing durable storage per filing."""
    forms = _route_forms(route)
    if not forms:
        return

    cik = getattr(security, "cik", None)
    if cik is None:
        return

    try:
        import edgar
    except Exception:
        return
    Company = getattr(edgar, "Company", None)
    if Company is None:
        return
    set_identity = getattr(edgar, "set_identity", None)

    effective_identity = (identity or os.environ.get("EDGAR_IDENTITY") or "").strip()
    if effective_identity and callable(set_identity):
        set_identity(effective_identity)

    should_persist_filings, persist_to_cloud, resolved_local_data_dir = _configure_edgar_storage(
        edgar_module=edgar,
        filing_storage_mode=filing_storage_mode,
        local_data_dir=local_data_dir,
        cloud_uri=cloud_uri,
        cloud_endpoint_url=cloud_endpoint_url,
        cloud_access_id=cloud_access_id,
        cloud_access_key=cloud_access_key,
    )

    try:
        company = Company(str(cik))
        envelopes = _collect_filing_envelopes(
            company=company,
            cik=cik,
            forms=forms,
            start_accepted_at=start_accepted_at,
            end_accepted_at=end_accepted_at,
        )
    except Exception as exc:
        raise RuntimeError(f"edgar fetch failed for cik={cik} route={route}: {exc}") from exc

    for envelope in envelopes:
        if should_persist_filings:
            try:
                _store_filtered_filings(
                    envelopes=[envelope],
                    local_data_dir=resolved_local_data_dir,
                    route=route,
                    repo=repo,
                    use_cloud_storage=persist_to_cloud,
                )
            except Exception:
                pass
        yield envelope


def fetch_filings_for_security(
    *,
    security: Any,
    route: str,
    start_accepted_at: datetime,
    end_accepted_at: datetime | None = None,
    identity: str | None = None,
    filing_storage_mode: int = EDGAR_DOWNLOAD_FILINGS_FLAG_DISABLED,
    local_data_dir: str | Path | None = None,
    repo: object | None = None,
    cloud_uri: str | None = None,
    cloud_endpoint_url: str | None = None,
    cloud_access_id: str | None = None,
    cloud_access_key: str | None = None,
) -> list[FilingEnvelope]:
    """Fetch and normalize filings for one security and route from edgartools."""
    return list(
        iter_filings_for_security(
            security=security,
            route=route,
            start_accepted_at=start_accepted_at,
            end_accepted_at=end_accepted_at,
            identity=identity,
            filing_storage_mode=filing_storage_mode,
            local_data_dir=local_data_dir,
            repo=repo,
            cloud_uri=cloud_uri,
            cloud_endpoint_url=cloud_endpoint_url,
            cloud_access_id=cloud_access_id,
            cloud_access_key=cloud_access_key,
        )
    )
