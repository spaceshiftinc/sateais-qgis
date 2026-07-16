"""Persist submitted job metadata in QSettings so the Jobs tab survives restarts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .settings import _settings

_KEY_JOBS = "jobs_v1"
DEFAULT_RETENTION_DAYS = 30

VALID_STATUSES = {"pending", "processing", "completed", "failed", "unknown"}


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
        return cls(
            job_id=job_id,
            analysis_type=_coerce_str(data.get("analysis_type")),
            submitted_at=_coerce_str(data.get("submitted_at")),
            status=_coerce_str(data.get("status"), default="pending"),
            error_code=_optional_str(data.get("error_code")),
            error_message=_optional_str(data.get("error_message")),
            polygon=polygon,
            detection_count=_optional_int(data.get("detection_count")),
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
) -> TrackedJob:
    """Insert a job at the head of the list.

    ``submitted_at`` / ``status`` default to "just submitted"; the server-sync
    path passes the values reported by the jobs API instead.
    """
    jobs = _read()
    # Skip if already tracked (idempotent).
    if any(j.job_id == job_id for j in jobs):
        return next(j for j in jobs if j.job_id == job_id)
    if status not in VALID_STATUSES:
        status = "unknown"
    job = TrackedJob(
        job_id=job_id,
        analysis_type=analysis_type,
        submitted_at=submitted_at or _now_iso(),
        status=status,
        polygon=polygon,
    )
    jobs.insert(0, job)
    _write(jobs)
    return job


def update_status(
    job_id: str,
    status: str,
    error_code: str | None = None,
    error_message: str | None = None,
) -> TrackedJob | None:
    """Update a tracked job; returns the updated entry or None if not found."""
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
        try:
            submitted = datetime.fromisoformat(job.submitted_at)
        except (TypeError, ValueError):
            kept.append(job)
            continue
        if submitted.tzinfo is None:
            submitted = submitted.replace(tzinfo=timezone.utc)
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
    "set_detection_count",
    "remove",
    "list_all",
    "cleanup_expired",
    "DEFAULT_RETENTION_DAYS",
]
