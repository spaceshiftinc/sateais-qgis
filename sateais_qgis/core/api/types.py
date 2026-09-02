"""SateAIs API domain models."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
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


@dataclass
class PreviewCredits:
    """Credit estimate for a would-be job.

    ``estimated`` is None when the server cannot estimate before the run
    (that is *not* "free" — see ``wording.credits_label``). ``sufficient``
    follows the same rule.
    """

    estimated: float | None = None
    balance: float | None = None
    sufficient: bool | None = None


@dataclass
class PreviewCoverage:
    """How much of the requested polygon would actually be analysed.

    ``polygon`` is the analysed-area WKT in the same format the job detail
    returns after completion, so one drawing path can render both.
    """

    method: str | None = None
    ratio: float | None = None
    requested_area_sqkm: float | None = None
    polygon: str | None = None


@dataclass
class Preview:
    """Response of ``POST /analyze/{endpoint}/preview``.

    The server omits ``coverage`` when the catalogue search cannot finish in
    time. Callers must treat that as "unknown", never as full coverage.
    """

    endpoint_id: str | None = None
    area_sqkm: float | None = None
    credits: PreviewCredits | None = None
    coverage: PreviewCoverage | None = None
    warnings: list[dict[str, Any]] = field(default_factory=list)


def _opt_float(value: Any) -> float | None:
    """Numbers only, and only finite ones.

    ``json.loads`` accepts the ``NaN`` / ``Infinity`` literals by default, and
    ``bool`` is a subclass of ``int``. Both would otherwise become a number the
    UI presents as fact; None keeps them in the "unknown" branch.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def preview_from_dict(data: dict[str, Any]) -> Preview:
    """Parse a preview response. Unknown fields are ignored, missing ones stay None."""
    credits_raw = data.get("credits")
    credits = None
    if isinstance(credits_raw, dict):
        sufficient = credits_raw.get("sufficient")
        credits = PreviewCredits(
            estimated=_opt_float(credits_raw.get("estimated")),
            balance=_opt_float(credits_raw.get("balance")),
            sufficient=sufficient if isinstance(sufficient, bool) else None,
        )

    coverage_raw = data.get("coverage")
    coverage = None
    if isinstance(coverage_raw, dict):
        polygon = coverage_raw.get("polygon")
        method = coverage_raw.get("method")
        coverage = PreviewCoverage(
            method=method if isinstance(method, str) else None,
            ratio=_opt_float(coverage_raw.get("ratio")),
            requested_area_sqkm=_opt_float(coverage_raw.get("requested_area_sqkm")),
            polygon=polygon if isinstance(polygon, str) and polygon else None,
        )

    warnings_raw = data.get("warnings")
    warnings = (
        [w for w in warnings_raw if isinstance(w, dict)] if isinstance(warnings_raw, list) else []
    )

    endpoint_id = data.get("endpoint_id")
    return Preview(
        endpoint_id=endpoint_id if isinstance(endpoint_id, str) else None,
        area_sqkm=_opt_float(data.get("area_sqkm")),
        credits=credits,
        coverage=coverage,
        warnings=warnings,
    )


__all__ = [
    "Job",
    "JobStatus",
    "AnalysisType",
    "AnalysisRequest",
    "Preview",
    "PreviewCredits",
    "PreviewCoverage",
    "preview_from_dict",
]
