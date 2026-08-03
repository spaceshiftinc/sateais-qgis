"""SateAIs API domain models."""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from typing import Any

from .errors import InvalidAnalysisRequestError


class JobStatus(str, Enum):
    """Status of a detection job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    UNKNOWN = "unknown"

    @classmethod
    def parse(cls, raw: str | None) -> JobStatus:
        """Parse an API status string, falling back to UNKNOWN."""
        if raw is None:
            return cls.UNKNOWN
        try:
            return cls(raw)
        except ValueError:
            return cls.UNKNOWN


@dataclass
class Job:
    """Snapshot of a job's state."""

    job_id: str
    status: JobStatus
    created_at: str | None = None
    completed_at: str | None = None
    result_path: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    # Detection type ("ship", "timeseries", …). Only populated by the job-list
    # endpoint; single-job responses do not include it.
    endpoint_id: str | None = None
    # The parameters the job was submitted with, echoed back verbatim. Also
    # list-only, which is why polling can never recover them — Sync is the only
    # way to learn what a job submitted elsewhere actually asked for.
    request_params: dict[str, Any] | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in (JobStatus.COMPLETED, JobStatus.FAILED)

    @property
    def is_completed(self) -> bool:
        return self.status == JobStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        return self.status == JobStatus.FAILED


class AnalysisType(str, Enum):
    """Available detection job types."""

    SHIP = "ship"
    OILSLICK = "oilslick"
    NEWBUILDING = "newbuilding"
    DISAPPEARBUILDING = "disappearbuilding"
    TIMESERIES = "timeseries"

    @property
    def accepts_scene_or_polygon_date(self) -> bool:
        """True if the type accepts either scene_id or polygon+date."""
        return self in (AnalysisType.SHIP, AnalysisType.OILSLICK)

    @property
    def requires_date_range(self) -> bool:
        """True if the type requires polygon + date_start + date_end."""
        return self in (
            AnalysisType.NEWBUILDING,
            AnalysisType.DISAPPEARBUILDING,
            AnalysisType.TIMESERIES,
        )


@dataclass(frozen=True)
class AnalysisRequest:
    """A detection job request.

    Input patterns vary by analysis type:
        - ship / oilslick: scene_id OR (polygon + date)
        - newbuilding / disappearbuilding / timeseries: polygon + date_start + date_end
    """

    analysis_type: AnalysisType
    satellite_id: str = "sentinel-1"
    scene_id: str | None = None
    polygon: str | None = None
    date: str | None = None
    date_start: str | None = None
    date_end: str | None = None
    date_direction: str | None = None
    orbit_direction: str | None = None

    def validate(self) -> None:
        """Validate the parameter combination.

        Raises:
            InvalidAnalysisRequestError: If required parameters are missing
                or incompatible.
        """
        t = self.analysis_type
        if t.accepts_scene_or_polygon_date:
            has_scene = bool(self.scene_id)
            has_polygon_date = bool(self.polygon) and bool(self.date)
            if has_scene == has_polygon_date:
                raise InvalidAnalysisRequestError(
                    f"{t.value}: specify exactly one of scene_id OR polygon+date "
                    f"(got scene_id={has_scene}, polygon+date={has_polygon_date})"
                )
        elif t.requires_date_range:
            missing = [
                name
                for name, value in (
                    ("polygon", self.polygon),
                    ("date_start", self.date_start),
                    ("date_end", self.date_end),
                )
                if not value
            ]
            if missing:
                raise InvalidAnalysisRequestError(
                    f"{t.value}: required fields missing: {', '.join(missing)}"
                )

    def to_body(self) -> dict[str, Any]:
        """Build the request body dict, omitting None fields."""
        body: dict[str, Any] = {}
        for f in fields(self):
            if f.name == "analysis_type":
                continue
            value = getattr(self, f.name)
            if value is None:
                continue
            body[f.name] = value
        return body


__all__ = [
    "Job",
    "JobStatus",
    "AnalysisType",
    "AnalysisRequest",
]
