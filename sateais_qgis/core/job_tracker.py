"""Persist submitted job metadata in QSettings so the Jobs tab survives restarts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from . import job_summary
from .settings import _settings

_KEY_JOBS = "jobs_v1"
DEFAULT_RETENTION_DAYS = 30

VALID_STATUSES = {"pending", "processing", "completed", "failed", "unknown"}

# Request parameters this plugin stores and shows. Everything else the API
# reports is deliberately dropped: ``satellite_id`` is a constant, ``lat``/``lon``
# mean different things depending on how the job was submitted, and
# ``polygon_id`` / ``year`` / ``tif_id`` cannot be submitted from QGIS at all.
# Keeping an allowlist also stops unknown server keys accumulating in the single
# JSON blob QSettings holds.
_REQUEST_KEYS = ("scene_id", "date", "date_start", "date_end")


@dataclass
class TrackedJob:
    job_id: str
    analysis_type: str
    submitted_at: str  # ISO 8601 (UTC)
    status: str = "pending"
    error_code: str | None = None
    error_message: str | None = None
    polygon: str | None = None  # WKT in EPSG:4326 (None for scene-id only jobs)
    # Number of detected features, filled in the first time the result is
    # loaded (the API doesn't return a count, so we derive it from the GeoJSON).
    # None until then; persisted so the badge survives restarts.
    detection_count: int | None = None
    # 完了後にサーバが返す実績値。単位付きで並べるだけで、それぞれが
    # 何の数字かはラベルなしに読める
    completed_at: str | None = None
    area_sqkm: float | None = None
    credits_used: float | None = None

    # --- request context ----------------------------------------------------
    # What was actually asked for, so a card is identifiable without loading the
    # result. Filled from the submit form when the job is created here, or from
    # the jobs-list API's ``request_params`` on Sync (for jobs submitted from the
    # console / CLI / MCP, and for jobs tracked before this existed). Stays None
    # when neither source has run — the single-job status endpoint does not carry
    # request parameters, so polling can never fill these in.
    scene_id: str | None = None
    date: str | None = None  # ship / oilslick reference date (YYYY-MM-DD)
    date_start: str | None = None  # date-range types
    date_end: str | None = None
    # "" = never resolved, "local" = captured at submit, "server" = from Sync,
    # "unavailable" = the server had nothing for it.
    request_source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrackedJob:
        job_id = data.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            raise ValueError("invalid job_id")
        polygon = data.get("polygon")
        if polygon is not None and not isinstance(polygon, str):
            polygon = None
        # Missing keys fall back to defaults, so entries written by older
        # versions load unchanged and no migration is needed.
        return cls(
            job_id=job_id,
            analysis_type=_coerce_str(data.get("analysis_type")),
            submitted_at=_coerce_str(data.get("submitted_at")),
            status=_coerce_str(data.get("status"), default="pending"),
            error_code=_optional_str(data.get("error_code")),
            error_message=_optional_str(data.get("error_message")),
            polygon=polygon,
            detection_count=_optional_int(data.get("detection_count")),
            scene_id=_optional_str(data.get("scene_id")),
            date=_optional_str(data.get("date")),
            date_start=_optional_str(data.get("date_start")),
            date_end=_optional_str(data.get("date_end")),
            request_source=_coerce_str(data.get("request_source")),
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_str(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: Any) -> int | None:
    # bool is an int subclass; reject it so stray True/False don't become 1/0.
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) and value >= 0 else None


def _request_context(request: dict[str, Any] | None) -> dict[str, str]:
    """Keep only the allowlisted, non-empty string parameters from a request."""
    if not isinstance(request, dict):
        return {}
    context: dict[str, str] = {}
    for key in _REQUEST_KEYS + ("polygon",):
        value = _optional_str(request.get(key))
        if value:
            context[key] = value
    return context


def _read() -> list[TrackedJob]:
    raw = _settings().value(_KEY_JOBS, "[]", type=str) or "[]"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    jobs: list[TrackedJob] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        try:
            jobs.append(TrackedJob.from_dict(entry))
        except (KeyError, TypeError, ValueError):
            continue
    return jobs


def _write(jobs: list[TrackedJob]) -> None:
    payload = json.dumps([job.to_dict() for job in jobs])
    _settings().setValue(_KEY_JOBS, payload)


def list_all() -> list[TrackedJob]:
    """Return all tracked jobs, newest first."""
    return _read()


def add(
    analysis_type: str,
    job_id: str,
    polygon: str | None = None,
    submitted_at: str | None = None,
    status: str = "pending",
    request: dict[str, Any] | None = None,
    request_source: str = "",
) -> TrackedJob:
    """Insert a job at the head of the list.

    ``submitted_at`` / ``status`` default to "just submitted"; the server-sync
    path passes the values reported by the jobs API instead. ``request`` is the
    submitted parameter set (or the API's ``request_params``); only the keys this
    plugin displays are kept, so unknown server fields never accumulate in the
    stored blob.
    """
    jobs = _read()
    # Skip if already tracked (idempotent).
    if any(j.job_id == job_id for j in jobs):
        return next(j for j in jobs if j.job_id == job_id)
    if status not in VALID_STATUSES:
        status = "unknown"
    context = _request_context(request)
    job = TrackedJob(
        job_id=job_id,
        analysis_type=analysis_type,
        submitted_at=submitted_at or _now_iso(),
        status=status,
        polygon=polygon or context.get("polygon"),
        request_source=request_source,
        **{key: context.get(key) for key in _REQUEST_KEYS},
    )
    jobs.insert(0, job)
    _write(jobs)
    return job


def update_status(
    job_id: str,
    status: str,
    error_code: str | None = None,
    error_message: str | None = None,
    completed_at: str | None = None,
    area_sqkm: float | None = None,
    credits_used: float | None = None,
) -> TrackedJob | None:
    """Update a tracked job; returns the updated entry or None if not found.

    The completion figures are optional because only the jobs-list endpoint
    carries them; a plain status poll leaves them untouched rather than
    blanking what a previous refresh already learned.
    """
    if status not in VALID_STATUSES:
        status = "unknown"
    jobs = _read()
    for job in jobs:
        if job.job_id == job_id:
            job.status = status
            if error_code is not None:
                job.error_code = error_code
            if error_message is not None:
                job.error_message = error_message
            if completed_at is not None:
                job.completed_at = completed_at
            if area_sqkm is not None:
                job.area_sqkm = area_sqkm
            if credits_used is not None:
                job.credits_used = credits_used
            _write(jobs)
            return job
    return None


def set_request_context(
    job_id: str,
    request: dict[str, Any] | None,
    source: str,
) -> TrackedJob | None:
    """Merge allowlisted request parameters into an already-tracked job.

    Incoming non-None values win, so a later Sync can correct what was captured
    locally — except ``polygon``, which is only filled when missing so a Sync
    never replaces the exact WKT the user drew with the server's echo of it.
    Backfilling ``polygon`` here is what makes AOI preview work for jobs that
    were submitted from the console, CLI or MCP.
    """
    context = _request_context(request)
    jobs = _read()
    for job in jobs:
        if job.job_id != job_id:
            continue
        for key in _REQUEST_KEYS:
            value = context.get(key)
            if value is not None:
                setattr(job, key, value)
        if not job.polygon and context.get("polygon"):
            job.polygon = context["polygon"]
        # "unavailable" is a floor, not a correction: a job whose request was
        # captured locally at submit time must not be demoted just because the
        # server had nothing to add for it.
        if source and not (source == "unavailable" and job.request_source):
            job.request_source = source
        _write(jobs)
        return job
    return None


def set_detection_count(job_id: str, count: int) -> TrackedJob | None:
    """Store the detected-feature count for a job. Returns the updated entry."""
    if count < 0:
        return None
    jobs = _read()
    for job in jobs:
        if job.job_id == job_id:
            job.detection_count = count
            _write(jobs)
            return job
    return None


def remove(job_id: str) -> bool:
    """Delete a tracked job by id. Returns True if something was removed."""
    jobs = _read()
    remaining = [j for j in jobs if j.job_id != job_id]
    if len(remaining) == len(jobs):
        return False
    _write(remaining)
    return True


def cleanup_expired(retention_days: int = DEFAULT_RETENTION_DAYS) -> int:
    """Drop jobs whose ``submitted_at`` is older than ``retention_days``.

    Returns the number of jobs removed. Entries with an unparseable
    ``submitted_at`` are kept as-is to avoid silently losing data.
    """
    if retention_days <= 0:
        return 0
    jobs = _read()
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    kept: list[TrackedJob] = []
    removed = 0
    for job in jobs:
        # Shared with the card rendering so a "Z"-suffixed timestamp from the
        # jobs list endpoint is understood here too — Python 3.9 (QGIS LTR)
        # cannot parse it directly, and an unparseable date keeps a job forever.
        submitted = job_summary.parse_iso8601(job.submitted_at)
        if submitted is None:
            kept.append(job)
            continue
        if submitted < cutoff:
            removed += 1
        else:
            kept.append(job)
    if removed:
        _write(kept)
    return removed


__all__ = [
    "TrackedJob",
    "add",
    "update_status",
    "set_request_context",
    "set_detection_count",
    "remove",
    "list_all",
    "cleanup_expired",
    "DEFAULT_RETENTION_DAYS",
]
