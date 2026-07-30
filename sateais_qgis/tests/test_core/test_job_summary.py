"""Unit tests for core.job_summary (pure Python — no PyQGIS, so these run in CI)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sateais_qgis.core import job_summary


@dataclass
class StubJob:
    """Stands in for TrackedJob so this module stays importable without Qt."""

    job_id: str = "3816209d-1a2b-4c3d-8e9f-0a1b2c3d4e5f"
    analysis_type: str = "timeseries"
    submitted_at: str = "2026-07-30T05:12:00+00:00"
    scene_id: str | None = None
    date: str | None = None
    date_start: str | None = None
    date_end: str | None = None
    request_source: str = "local"


SCENE_ID = "S1A_IW_GRDH_1SDV_20260101T123456_20260101T123521_051234_062ABC_1234"


class TestFormatAnalysisLabel:
    def test_known_types(self):
        assert job_summary.format_analysis_label("timeseries") == "Time Series"
        assert job_summary.format_analysis_label("disappearbuilding") == "Disappeared Building"

    def test_unknown_type_falls_back_to_the_raw_value(self):
        # Synced jobs can carry an endpoint_id this version has never heard of.
        assert job_summary.format_analysis_label("idlefarm") == "idlefarm"

    def test_empty(self):
        assert job_summary.format_analysis_label("") == ""


class TestFormatDetectionSummary:
    def test_singular_and_plural(self):
        assert job_summary.format_detection_summary("ship", 1) == "1 ship"
        assert job_summary.format_detection_summary("ship", 23) == "23 ships"
        assert job_summary.format_detection_summary("timeseries", 7) == "7 changes"

    def test_unknown_type_uses_a_generic_noun(self):
        assert job_summary.format_detection_summary("idlefarm", 2) == "2 detections"


class TestFormatSceneId:
    def test_sentinel1_id_is_shortened_to_platform_and_date(self):
        assert job_summary.format_scene_id(SCENE_ID) == "S1A 2026-01-01"

    def test_short_unrecognised_id_is_left_alone(self):
        assert job_summary.format_scene_id("SOME_SCENE") == "SOME_SCENE"

    def test_long_unrecognised_id_is_truncated(self):
        raw = "X" * 60
        shortened = job_summary.format_scene_id(raw)
        assert len(shortened) < len(raw)
        assert shortened.endswith("…")

    def test_sentinel1_id_with_a_bad_timestamp_falls_back(self):
        # Right shape, unparseable date field: must not invent a date.
        raw = "S1A_IW_GRDH_1SDV_NOTADATE"
        assert job_summary.format_scene_id(raw) == raw

    def test_empty(self):
        assert job_summary.format_scene_id("") == ""


class TestFormatSubmittedAt:
    def test_absolute_and_relative(self):
        now = datetime(2026, 7, 30, 23, 12, tzinfo=timezone.utc)
        rendered = job_summary.format_submitted_at("2026-07-30T05:12:00+00:00", now=now)
        assert rendered.endswith("(18h ago)")

    def test_naive_timestamps_are_treated_as_utc(self):
        now = datetime(2026, 7, 30, 5, 42, tzinfo=timezone.utc)
        rendered = job_summary.format_submitted_at("2026-07-30T05:12:00", now=now)
        assert rendered.endswith("(30m ago)")

    def test_unparseable_input_is_returned_as_is(self):
        assert job_summary.format_submitted_at("not a timestamp") == "not a timestamp"

    def test_empty(self):
        assert job_summary.format_submitted_at("") == ""

    def test_future_timestamps_read_as_just_now(self):
        now = datetime(2026, 7, 30, 0, 0, tzinfo=timezone.utc)
        rendered = job_summary.format_submitted_at("2026-07-30T05:12:00+00:00", now=now)
        assert rendered.endswith("(just now)")


class TestFormatRelative:
    def test_buckets(self):
        assert job_summary.format_relative(timedelta(seconds=5)) == "5s ago"
        assert job_summary.format_relative(timedelta(minutes=30)) == "30m ago"
        assert job_summary.format_relative(timedelta(hours=18)) == "18h ago"
        assert job_summary.format_relative(timedelta(days=3)) == "3d ago"


class TestBuildRequestSummary:
    def test_date_range(self):
        job = StubJob(date_start="2026-01-03", date_end="2026-07-03")
        assert job_summary.build_request_summary(job) == "2026-01-03 → 2026-07-03"

    def test_scene_mode(self):
        job = StubJob(analysis_type="ship", scene_id=SCENE_ID)
        assert job_summary.build_request_summary(job) == "Scene S1A 2026-01-01"

    def test_polygon_plus_date_mode(self):
        job = StubJob(analysis_type="ship", date="2026-01-01")
        assert job_summary.build_request_summary(job) == "2026-01-01"

    def test_nothing_known_is_empty_so_the_line_can_be_hidden(self):
        assert job_summary.build_request_summary(StubJob()) == ""

    def test_a_half_filled_range_does_not_render_a_dangling_arrow(self):
        assert job_summary.build_request_summary(StubJob(date_start="2026-01-03")) == ""


class TestBuildRequestTooltip:
    def test_carries_the_full_ids_the_card_shortens(self):
        job = StubJob(analysis_type="ship", scene_id=SCENE_ID)
        tooltip = job_summary.build_request_tooltip(job)
        assert job.job_id in tooltip
        assert SCENE_ID in tooltip

    def test_includes_the_period_for_date_range_jobs(self):
        job = StubJob(date_start="2026-01-03", date_end="2026-07-03")
        assert "Period: 2026-01-03 → 2026-07-03" in job_summary.build_request_tooltip(job)

    def test_prompts_for_sync_only_when_unresolved(self):
        assert job_summary.MISSING_REQUEST_HINT in job_summary.build_request_tooltip(
            StubJob(request_source="")
        )
        assert job_summary.MISSING_REQUEST_HINT not in job_summary.build_request_tooltip(
            StubJob(request_source="server", date_start="2026-01-03", date_end="2026-07-03")
        )

    def test_is_plain_text_even_when_values_contain_markup(self):
        job = StubJob(analysis_type="<b>oops</b>", scene_id="<i>x</i>")
        tooltip = job_summary.build_request_tooltip(job)
        # Passed through verbatim; the widget sets PlainText so it renders as-is.
        assert "<b>oops</b>" in tooltip
        assert "<html>" not in tooltip.lower()


class TestBuildSearchText:
    def test_matches_full_id_raw_type_and_label(self):
        job = StubJob(date_start="2026-01-03", date_end="2026-07-03")
        haystack = job_summary.build_search_text(job)
        assert job.job_id in haystack  # the card only shows the first 8 chars
        assert "timeseries" in haystack
        assert "time series" in haystack
        assert "2026-01-03" in haystack

    def test_includes_the_scene_id(self):
        job = StubJob(analysis_type="ship", scene_id=SCENE_ID)
        assert SCENE_ID.lower() in job_summary.build_search_text(job)

    def test_is_lower_cased(self):
        haystack = job_summary.build_search_text(StubJob())
        assert haystack == haystack.lower()
