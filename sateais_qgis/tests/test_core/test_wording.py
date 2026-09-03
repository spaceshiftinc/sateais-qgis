"""Unit tests for core.wording.

These cases are ported from the MCP widget's tests
(sateais-mcp-aws: tests/unit/lambdas/mcp_sateais/widget-geo.test.ts) so the
two implementations stay in lockstep. If a sentence or rounding rule changes
on one side, change it on both.
"""

from __future__ import annotations

import pytest

from sateais_qgis.core import wording


class TestCreditsLabel:
    def test_always_an_upper_bound(self):
        # 実消費は実処理範囲で決まる。等号で書くと多く取られるように読める
        assert wording.credits_label(257.38) == "up to 257.38 credits"

    def test_none_is_not_zero(self):
        assert wording.credits_label(None) == "Cost is known only after it runs."
        assert wording.credits_unknown(None) is True

    def test_zero_is_free(self):
        assert wording.credits_label(0) == "No credits for this analysis."
        assert wording.credits_unknown(0) is False

    def test_thousands_separator(self):
        assert wording.credits_label(1234.5) == "up to 1,234.50 credits"


class TestCoverageLabel:
    def test_silence_when_fully_covered_before_run(self):
        assert wording.coverage_label(1.0) == ""
        assert wording.coverage_is_partial(1.0) is False

    def test_full_coverage_is_explicit_after_run(self):
        assert wording.coverage_label(1.0, past=True) == "All of your area was analysed"

    def test_rounds_down(self):
        # 0.897 を 90% と書くと、90% 未満で発火する警告と矛盾する
        assert wording.coverage_label(0.897) == "89% covered"
        assert wording.coverage_label(0.66, past=True) == "Only 66% of your area was analysed"

    def test_unknown_coverage_stays_silent(self):
        # 分からないときに 100% と書かない
        assert wording.coverage_label(None) == ""
        assert wording.coverage_label(None, past=True) == ""
        assert wording.coverage_is_partial(None) is False


class TestBalanceNote:
    def test_only_when_short(self):
        assert wording.balance_note(False, 120.4) == "balance 120.40"
        assert wording.balance_note(True, 10963330.9) == ""
        assert wording.balance_note(None, 10.0) == ""


class TestAreaLabel:
    def test_digits_switch_at_100(self):
        assert wording.area_km2_label(38.29) == "38.29 km²"
        assert wording.area_km2_label(30000) == "30,000 km²"


class TestWarningMessages:
    def test_extracts_messages_in_order(self):
        warnings = [
            {"code": "LOW_AOI_COVERAGE", "message": "Scenes cover only 78% of the requested area."},
            {"code": "X"},  # message 無しは黙って落とす
            {"code": "Y", "message": ""},
        ]
        assert wording.warning_messages(warnings) == [
            "Scenes cover only 78% of the requested area."
        ]


class TestNonFiniteNumbers:
    """NaN / Infinity は「不明」に倒す。

    ``json.loads`` は既定で ``NaN`` / ``Infinity`` リテラルを受け入れるので、
    サーバが返せばそのまま届く。format.ts が ``Number.isFinite`` で守っている
    のと同じ扱いにする（守らないと "up to nan credits" と表示され、
    パーセント変換は例外で落ちた）。
    """

    def test_credits_treats_nan_as_unknown(self):
        assert wording.credits_label(float("nan")) == "Cost is known only after it runs."
        assert wording.credits_unknown(float("nan")) is True
        assert wording.credits_label(float("inf")) == "Cost is known only after it runs."

    def test_coverage_stays_silent_and_does_not_raise(self):
        assert wording.coverage_label(float("nan")) == ""
        assert wording.coverage_label(float("nan"), past=True) == ""
        assert wording.coverage_is_partial(float("nan")) is False

    def test_balance_note_ignores_nan(self):
        assert wording.balance_note(False, float("nan")) == ""


class TestScenesUnavailable:
    """シーン不足は「被覆率を確認できなかった」とは別物。

    orchestrator #300 以降、シーンが無い / 前後比較に足りない場合は
    ``coverage`` を返さず ``SCENE_NOT_FOUND`` / ``INSUFFICIENT_SCENES`` を
    warnings に載せる。検索の時間切れと同じ扱いにすると「全範囲ぶん課金される
    前提で」と案内してしまい、二重に誤る（何も解析されず、直すべきは期間）。
    """

    def test_detects_both_codes(self):
        assert wording.scenes_unavailable([{"code": "SCENE_NOT_FOUND", "message": "x"}]) is True
        assert wording.scenes_unavailable([{"code": "INSUFFICIENT_SCENES", "message": "x"}]) is True

    def test_other_warnings_are_not_scene_shortage(self):
        assert wording.scenes_unavailable([{"code": "LOW_AOI_COVERAGE", "message": "x"}]) is False
        assert wording.scenes_unavailable([]) is False


class TestJobMetaFields:
    """値には見出しを付ける。単位だけでは何の数字か決まらないため。"""

    def test_names_every_value(self):
        assert wording.job_meta_fields("2026-09-03 12:00", 196.4, 1.96, "3m 31s") == [
            ("Submitted", "2026-09-03 12:00"),
            ("Area", "196 km²"),
            ("Cost", "1.96 credits"),
            ("Took", "3m 31s"),
        ]

    def test_drops_unknown_values_rather_than_captioning_a_blank(self):
        assert wording.job_meta_fields("2026-09-03 12:00", None, None, "") == [
            ("Submitted", "2026-09-03 12:00"),
        ]

    def test_zero_credits_reads_as_free_not_as_missing(self):
        assert ("Cost", "free") in wording.job_meta_fields("x", None, 0, "")

    @pytest.mark.parametrize("bad", [float("nan"), float("inf")])
    def test_nan_and_infinity_are_not_figures(self, bad):
        labels = [label for label, _ in wording.job_meta_fields("x", bad, bad, "")]
        assert labels == ["Submitted"]


class TestFormatCredits:
    def test_matches_the_rounding_used_elsewhere(self):
        assert wording.format_credits(126.9612) == "126.96"
        assert wording.format_credits(1234.5) == "1,234.50"


class TestLegendLabels:
    """地図の3色の呼び名。全体が2つに分かれる構造が語だけで読めること。"""

    def test_the_two_parts_share_the_word_of_the_whole(self):
        assert wording.LEGEND_COVERED.lower() in wording.LEGEND_NOT_COVERED.lower()

    def test_the_coverage_sentence_uses_the_same_word_as_the_legend(self):
        # 凡例の "Covered" と本文の "97% covered" が互いを補強する
        assert wording.LEGEND_COVERED.lower() in wording.coverage_label(0.97)

    def test_every_label_is_short_enough_for_a_narrow_dock(self):
        for label in (
            wording.LEGEND_REQUESTED,
            wording.LEGEND_COVERED,
            wording.LEGEND_NOT_COVERED,
        ):
            assert len(label) <= 12, label


class TestAreaLimitReason:
    """面積上限だけはサーバが数値付きで理由を返す。

    上限は endpoint ごとに違い、値を返す API も無い。プラグインに書き写すと
    サーバの変更で黙って嘘になるので、超過したときの文面から数値を取り出して
    こちらの言葉に組み直す。「拒否されました」だけでは、どれだけ小さくすれば
    よいかが分からない。
    """

    SERVER = "Polygon area (52.6 km²) exceeds 50 km² limit for endpoint 'timeseries'"

    def test_states_both_numbers_and_the_next_move(self):
        said = wording.area_limit_reason(self.SERVER)
        assert "52.6 km²" in said
        assert "50 km²" in said
        assert "smaller" in said

    def test_never_repeats_the_internal_endpoint_id(self):
        assert "timeseries" not in wording.area_limit_reason(self.SERVER)

    def test_failure_label_uses_the_same_sentence(self):
        # 事前（preview）と事後（ジョブ失敗）で同じ読み方になること
        assert wording.failure_label("VALIDATION_ERROR", self.SERVER) == wording.area_limit_reason(
            self.SERVER
        )

    @pytest.mark.parametrize(
        "message",
        [
            "",
            None,
            "Invalid WKT",
            # 面積の話ではない検証エラーを取り違えない
            "date_start must be before date_end",
        ],
    )
    def test_other_validation_errors_are_not_area_limits(self, message):
        assert wording.area_limit_reason(message) == ""

    def test_thousands_separated_limits_are_read(self):
        said = wording.area_limit_reason(
            "Polygon area (31,204.9 km²) exceeds 30,000 km² limit for endpoint 'newbuilding'"
        )
        assert "31,204.9 km²" in said and "30,000 km²" in said
