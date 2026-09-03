"""Unit tests for core.job_summary (pure Python — no PyQGIS, so these run in CI)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sateais_qgis.core import job_summary


@dataclass
class StubJob:
    """Stands in for TrackedJob so this module stays importable without Qt."""

    job_id: str = "00000000-1111-2222-3333-444444444444"
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
        # 呼び名は MCP ウィジェット (kindLabel) = 公開ドキュメントの見出しと同じ。
        # 画面ごとに言い換えると、利用者が読むドキュメントと食い違う
        assert job_summary.format_analysis_label("timeseries") == "Time-series change"
        assert (
            job_summary.format_analysis_label("disappearbuilding")
            == "Disappeared building detection"
        )

    def test_unknown_type_falls_back_to_the_raw_value(self):
        # Synced jobs can carry an endpoint_id this version has never heard of.
        assert job_summary.format_analysis_label("something-new") == "something-new"

    def test_empty(self):
        assert job_summary.format_analysis_label("") == ""


class TestFormatDetectionSummary:
    def test_singular_and_plural(self):
        assert job_summary.format_detection_summary("ship", 1) == "1 ship"
        assert job_summary.format_detection_summary("ship", 23) == "23 ships"
        assert job_summary.format_detection_summary("timeseries", 7) == "7 changes"

    def test_unknown_type_uses_a_generic_noun(self):
        assert job_summary.format_detection_summary("something-new", 2) == "2 detections"


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


class TestParseIso8601:
    def test_accepts_the_z_suffix_the_jobs_list_returns(self):
        # datetime.fromisoformat only learned "Z" in 3.11, and QGIS LTR ships
        # Python 3.9 — without this, every synced job's date fails to parse.
        parsed = job_summary.parse_iso8601("2026-07-03T03:39:21.506327Z")
        assert parsed is not None
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == timedelta(0)

    def test_accepts_an_explicit_offset(self):
        assert job_summary.parse_iso8601("2026-07-30T05:12:00+00:00") is not None

    def test_naive_timestamps_are_treated_as_utc(self):
        parsed = job_summary.parse_iso8601("2026-07-30T05:12:00")
        assert parsed is not None and parsed.utcoffset() == timedelta(0)

    def test_unparseable_input_returns_none(self):
        for value in ("", "not a date", None, 123):
            assert job_summary.parse_iso8601(value) is None


class TestFormatSubmittedAt:
    def test_absolute_and_relative(self):
        now = datetime(2026, 7, 30, 23, 12, tzinfo=timezone.utc)
        rendered = job_summary.format_submitted_at("2026-07-30T05:12:00+00:00", now=now)
        assert rendered.endswith("(18h ago)")

    def test_z_suffixed_timestamps_render(self):
        now = datetime(2026, 7, 30, 23, 12, tzinfo=timezone.utc)
        rendered = job_summary.format_submitted_at("2026-07-30T05:12:00Z", now=now)
        assert rendered.endswith("(18h ago)")
        assert "Z" not in rendered

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
    """要求した日付には必ずラベルを付ける。

    カードには 2 種類の日付が載る — 投入した日時と、要求した画像の期間。
    裸で置くと同じ見た目になり、一覧が投入日時順に並んでいるのに先に読まれるのは
    要求日のほうになるので、並び順が意味不明に見える。
    """

    def test_a_period_says_it_is_a_period(self):
        job = StubJob(date_start="2026-01-03", date_end="2026-07-03")
        assert job_summary.build_request_summary(job) == "Period 2026-01-03 → 2026-07-03"

    def test_scene_mode(self):
        job = StubJob(analysis_type="ship", scene_id=SCENE_ID)
        assert job_summary.build_request_summary(job) == "Scene S1A 2026-01-01"

    def test_a_single_date_is_never_left_bare(self):
        """ship / oilslick の基準日。裸の日付は投入日と見分けが付かない。"""
        job = StubJob(analysis_type="ship", date="2026-01-01")
        assert job_summary.build_request_summary(job) == "Reference date 2026-01-01"

    def test_every_rendered_form_carries_a_word(self):
        """どの経路で組まれても、日付だけの行にはならないこと。"""
        for job in (
            StubJob(date_start="2026-01-03", date_end="2026-07-03"),
            StubJob(analysis_type="ship", scene_id=SCENE_ID),
            StubJob(analysis_type="ship", date="2026-01-01"),
        ):
            summary = job_summary.build_request_summary(job)
            assert summary[0].isalpha(), summary

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
        assert "time-series change" in haystack
        assert "2026-01-03" in haystack

    def test_includes_the_scene_id(self):
        job = StubJob(analysis_type="ship", scene_id=SCENE_ID)
        assert SCENE_ID.lower() in job_summary.build_search_text(job)

    def test_is_lower_cased(self):
        haystack = job_summary.build_search_text(StubJob())
        assert haystack == haystack.lower()


class TestDetectionOutcome:
    """数だけでは何を数えたか分からない。名詞まで言い切る。"""

    def test_names_what_was_counted(self):
        assert job_summary.format_detection_outcome("newbuilding", 138) == (
            "138 new buildings found"
        )
        assert job_summary.format_detection_outcome("ship", 1) == "1 ship found"

    def test_states_the_empty_case_explicitly(self):
        """「0」ではなく「見つからなかった」。未取得と区別が付く。"""
        assert job_summary.format_detection_outcome("ship", 0) == "No ships found"

    def test_groups_thousands(self):
        assert job_summary.format_detection_outcome("ship", 12345) == "12,345 ships found"

    def test_unknown_type_falls_back_to_a_neutral_noun(self):
        assert job_summary.format_detection_outcome("something-new", 2) == "2 detections found"


class TestDetectionCount:
    """種別名の右に置く短い形。名詞は繰り返さない。"""

    def test_states_the_count_with_the_verb_only(self):
        assert job_summary.format_detection_count(138) == "138 found"
        assert job_summary.format_detection_count(1) == "1 found"

    def test_zero_is_a_word_not_a_digit(self):
        """「0」は未入力の値にも見える。見つからなかったと言い切る。"""
        assert job_summary.format_detection_count(0) == "None found"

    def test_groups_thousands(self):
        assert job_summary.format_detection_count(12345) == "12,345 found"


class TestSearchText:
    """検索は ID の完全一致ではなく、打った端から絞り込める部分一致。

    36 桁を打ち切る人はいない。実際の使い方は「コンソールで見た ID を貼る」か
    「先週の ship のやつを探す」のどちらかなので、ID・種別・シーン・日付を
    1 本の文字列にまとめて部分一致で引く。
    """

    def _job(self, **kw):
        base = dict(
            job_id="7cf9025b-a262-491d-9d5e-2ba638448273",
            analysis_type="newbuilding",
            submitted_at="2026-09-03T00:12:12Z",
            date_start="2026-07-26",
            date_end="2026-09-02",
        )
        base.update(kw)
        return StubJob(**base)

    def test_a_fragment_of_the_id_matches(self):
        haystack = job_summary.build_search_text(self._job())
        # 貼り付ける前に数文字打っただけでも絞り込めること
        for fragment in ("7cf9", "7cf9025b", "a262-491d", "2ba638448273"):
            assert fragment in haystack, fragment

    def test_the_whole_id_matches(self):
        job = self._job()
        assert job.job_id in job_summary.build_search_text(job)

    def test_matches_either_spelling_of_the_type(self):
        haystack = job_summary.build_search_text(self._job())
        assert "newbuilding" in haystack
        assert "new building detection" in haystack

    def test_matches_the_dates_and_the_scene(self):
        haystack = job_summary.build_search_text(
            self._job(scene_id="S1A_IW_GRDH_1SDV_20260101T123456_X")
        )
        assert "2026-07-26" in haystack
        assert "s1a_iw_grdh" in haystack

    def test_is_lower_cased_so_matching_can_ignore_case(self):
        haystack = job_summary.build_search_text(
            self._job(scene_id="S1A_IW_GRDH_1SDV_20260101T123456_X")
        )
        assert haystack == haystack.lower()

    def test_missing_context_does_not_break_the_haystack(self):
        job = self._job(date_start=None, date_end=None)
        assert job.job_id in job_summary.build_search_text(job)
