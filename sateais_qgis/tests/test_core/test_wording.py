"""Unit tests for core.wording.

These cases are ported from the MCP widget's tests
(sateais-mcp-aws: tests/unit/lambdas/mcp_sateais/widget-geo.test.ts) so the
two implementations stay in lockstep. If a sentence or rounding rule changes
on one side, change it on both.
"""

from __future__ import annotations

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
