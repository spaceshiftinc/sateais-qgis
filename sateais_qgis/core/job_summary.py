"""Human-readable summaries of a tracked job: labels, dates, search text.

Qt-free (and QGIS-free) on purpose. This is the text behind the Jobs cards, and
keeping it out of the widgets is what lets it be tested in CI, where PyQGIS is
unavailable. The GUI reads its analysis labels from here rather than the reverse,
so those strings have a single home.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Runtime-importing job_tracker would drag QSettings (and therefore Qt) into
    # this module; the annotations are strings under PEP 563, so this is enough.
    from .job_tracker import TrackedJob

# Display names for the detection types this plugin can submit. Kept here rather
# than in the Analysis panel so cards, tooltips and search all agree.
# 呼び名は MCP ウィジェットの kindLabel と同じ = 公開ドキュメントの見出し
# (api-docs の content/docs/api-reference/analyze/*.mdx の title)。
# 画面ごとに言い換えると、利用者が読むドキュメントと名前が食い違う。
ANALYSIS_LABELS: dict[str, str] = {
    "ship": "Ship detection",
    "oilslick": "Oil slick detection",
    "newbuilding": "New building detection",
    "disappearbuilding": "Disappeared building detection",
    "timeseries": "Time-series change",
}

# (singular, plural) nouns so a completed job reads "23 ships" / "1 change"
# rather than a bare count.
DETECTION_NOUNS: dict[str, tuple] = {
    "ship": ("ship", "ships"),
    "oilslick": ("oil slick", "oil slicks"),
    "newbuilding": ("new building", "new buildings"),
    "disappearbuilding": ("removed building", "removed buildings"),
    "timeseries": ("change", "changes"),
}

_SCENE_ID_MAX = 30

# 押す先は Jobs タブ見出しの Refresh。かつて Sync という別ボタンがあった頃の
# 文言が残っており、存在しない操作を案内していた
MISSING_REQUEST_HINT = "Request details unavailable — press Refresh to fetch them."


def format_analysis_label(analysis_type: str) -> str:
    """Display name for a detection type, falling back to the raw value.

    Jobs synced from the server can carry an ``endpoint_id`` this plugin does not
    know about, and showing that verbatim beats showing nothing.
    """
    if not analysis_type:
        return ""
    return ANALYSIS_LABELS.get(analysis_type, analysis_type)


def format_detection_summary(analysis_type: str, count: int) -> str:
    """Return e.g. ``"23 ships"`` / ``"1 change"`` / ``"12 detections"``."""
    singular, plural = DETECTION_NOUNS.get(analysis_type, ("detection", "detections"))
    return f"{count} {singular if count == 1 else plural}"


def format_detection_outcome(analysis_type: str, count: int) -> str:
    """Return e.g. ``"138 new buildings found"`` / ``"No ships found"``.

    A bare ``138`` beside a name does not say what was counted. Naming the thing
    makes the number self-describing, and stating the empty case explicitly
    ("No ships found") distinguishes a finished run that found nothing from a
    run whose result has not been read yet.
    """
    singular, plural = DETECTION_NOUNS.get(analysis_type, ("detection", "detections"))
    if not count:
        return f"No {plural} found"
    return f"{count:,} {singular if count == 1 else plural} found"


def format_detection_count(count: int) -> str:
    """The count as it sits beside the type name: ``"138 found"`` / ``"None found"``.

    The type name is immediately to its left, so the noun would repeat; the long
    form (``format_detection_outcome``) goes in the tooltip instead. Zero is
    stated as a word — "0" beside a name reads as a value not yet filled in.
    """
    return f"{count:,} found" if count else "None found"


def format_scene_id(scene_id: str) -> str:
    """Shorten a scene ID to what identifies it to a human.

    Sentinel-1 IDs are structured (``S1A_IW_GRDH_1SDV_20260101T123456_…``), so the
    platform plus the acquisition date carries the meaning; anything unrecognised
    is truncated instead. Shortening semantically rather than eliding by pixel
    width keeps this a pure function — the full ID stays in the tooltip.
    """
    if not scene_id:
        return ""

    parts = scene_id.split("_")
    if len(parts) >= 5 and parts[0][:2].upper() == "S1":
        stamp = parts[4]
        if len(stamp) >= 8 and stamp[:8].isdigit():
            return f"{parts[0]} {stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}"
    return _shorten(scene_id, _SCENE_ID_MAX)


# 小数秒の桁数をそろえるための切り出し。3 桁でも 6 桁でもない値が来る
_FRACTIONAL_SECONDS_RE = re.compile(r"(?<=:\d\d)\.(\d+)")


def parse_iso8601(value: str) -> datetime | None:
    """Parse an ISO 8601 timestamp, or return None when it cannot be read.

    Two things Python 3.9 (QGIS LTR 3.34 / 3.40) cannot do with the timestamps
    this API returns, both of which made real jobs unreadable:

    ``Z`` suffix — ``fromisoformat`` only learned it in 3.11, while every
    timestamp from the jobs endpoints ends in one.

    **Variable-precision fractional seconds** — ``fromisoformat`` accepts
    *exactly* 3 or 6 digits before 3.11, but the server drops trailing zeros, so
    ``…52.74747Z`` (5 digits) arrives routinely. In one real store 9 of 47 jobs
    were affected: their cards printed the raw ISO string instead of a date,
    their runtimes were blank, and they sorted as though they had no date at
    all. Padding to 6 digits (truncating anything longer, which is below
    microsecond resolution) makes every precision readable.

    Naive timestamps are treated as UTC, which is what the API emits.
    """
    if not value or not isinstance(value, str):
        return None
    normalised = value.replace("Z", "+00:00")
    match = _FRACTIONAL_SECONDS_RE.search(normalised)
    if match:
        digits = match.group(1)[:6].ljust(6, "0")
        normalised = normalised[: match.start()] + "." + digits + normalised[match.end() :]
    try:
        parsed = datetime.fromisoformat(normalised)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def format_submitted_short(iso_ts: str) -> str:
    """Just ``2026-07-30 14:12`` in local time.

    The relative part ("18h ago") is the first thing to go when the row is
    narrow: it costs a third of the line and never changes what the reader
    decides. The full form stays available in the tooltip.
    """
    if not iso_ts:
        return ""
    ts = parse_iso8601(iso_ts)
    if ts is None:
        return iso_ts
    return ts.astimezone().strftime("%Y-%m-%d %H:%M")


def format_submitted_at(iso_ts: str, now: datetime | None = None) -> str:
    """Render a timestamp as ``2026-07-30 14:12 (18h ago)`` in local time.

    ``now`` is injectable so the relative part is testable.
    """
    if not iso_ts:
        return ""
    ts = parse_iso8601(iso_ts)
    if ts is None:
        return iso_ts
    reference = now or datetime.now(timezone.utc)
    absolute = ts.astimezone().strftime("%Y-%m-%d %H:%M")
    return f"{absolute} ({format_relative(reference - ts)})"


def format_relative(delta: timedelta) -> str:
    """Coarse "N ago" wording; anything in the future reads as ``just now``."""
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def build_request_summary(job: TrackedJob) -> str:
    """One line saying what was asked for, or ``""`` when nothing is known.

    **The dates are labelled.** A card carries two kinds of date — when the job
    was submitted, and the span of imagery it asked for — and unlabelled they
    render identically. The submitted date is what the list is ordered by, so
    when the request date is the one that reads first, the ordering looks
    arbitrary. Naming this one keeps the two apart.

    Callers hide the line entirely on an empty string, so a job whose request
    context was never captured does not leave a gap in the card.
    """
    if job.date_start and job.date_end:
        return f"Period {job.date_start} → {job.date_end}"
    if job.scene_id:
        return f"Scene {format_scene_id(job.scene_id)}"
    if job.date:
        # ship / oilslick の基準日。裸で置くと投入日と見分けが付かない
        return f"Reference date {job.date}"
    return ""


def build_request_tooltip(job: TrackedJob) -> str:
    """Full detail for the card tooltip: everything the card itself elides.

    Plain text with newlines — never HTML. ``scene_id`` and the analysis type can
    come from the server or another client, and QLabel auto-detects rich text.
    """
    lines = [format_analysis_label(job.analysis_type), f"Job ID: {job.job_id}"]

    submitted = format_submitted_at(job.submitted_at)
    if submitted:
        lines.append(f"Submitted: {submitted}")

    if job.date_start and job.date_end:
        lines.append(f"Period: {job.date_start} → {job.date_end}")
    elif job.date:
        lines.append(f"Reference date: {job.date}")

    if job.scene_id:
        lines.append(f"Scene: {job.scene_id}")

    if not job.request_source:
        lines.extend(["", MISSING_REQUEST_HINT])

    return "\n".join(lines)


def build_search_text(job: TrackedJob) -> str:
    """Lower-cased haystack for the Jobs-tab search box.

    Includes the *full* job id (the card only shows a short form) plus both the
    raw analysis type and its display name, so either spelling matches.
    """
    parts = (
        job.job_id,
        job.analysis_type,
        format_analysis_label(job.analysis_type),
        job.scene_id or "",
        job.date or "",
        job.date_start or "",
        job.date_end or "",
    )
    return " ".join(part for part in parts if part).lower()


def _shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)] + "…"


__all__ = [
    "ANALYSIS_LABELS",
    "DETECTION_NOUNS",
    "MISSING_REQUEST_HINT",
    "parse_iso8601",
    "format_analysis_label",
    "format_detection_summary",
    "format_scene_id",
    "format_submitted_at",
    "format_submitted_short",
    "format_relative",
    "build_request_summary",
    "build_request_tooltip",
    "build_search_text",
]
