"""The part of the requested area that will not be analysed.

Only the analysed area used to be drawn, which left "nothing was detected here"
and "this was never looked at" as the same picture. The shortfall is now drawn
in its own colour, so the two states are told apart on the map.
"""

from __future__ import annotations

import pytest

pyqgis_available = True
try:
    from qgis.core import QgsGeometry
except ImportError:
    pyqgis_available = False

pytestmark = pytest.mark.skipif(
    not pyqgis_available, reason="PyQGIS not available in this environment"
)

if pyqgis_available:
    from sateais_qgis.gui.widgets.coverage_band import CoverageBand

REQUESTED = "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))"
HALF = "POLYGON((0 0, 5 0, 5 10, 0 10, 0 0))"
# 要求範囲より広い被覆。落ちる分は無い
WIDER = "POLYGON((-1 -1, 11 -1, 11 11, -1 11, -1 -1))"
# 端が 0.1% ずれただけ。数値誤差の範囲で、警告色を出す理由にはならない
SLIVER = "POLYGON((0 0, 9.999 0, 9.999 10, 0 10, 0 0))"


@pytest.fixture
def band(qgis_app):
    # キャンバスは要らない。差分の算出だけを見る
    return CoverageBand.__new__(CoverageBand)


def _shortfall(band, requested: str, analysed: str | None) -> str:
    band._requested_wkt = requested
    return band._uncovered_wkt(analysed)


def test_half_covered_leaves_the_other_half(band):
    wkt = _shortfall(band, REQUESTED, HALF)
    assert wkt
    remainder = QgsGeometry.fromWkt(wkt)
    assert remainder.area() == pytest.approx(50.0, rel=1e-6)


def test_full_coverage_draws_nothing(band):
    assert _shortfall(band, REQUESTED, WIDER) == ""


def test_a_numerical_sliver_is_not_a_shortfall(band):
    """0.1% の差で「衛星データなし」を塗ると、全面カバーでも警告が出る。"""
    assert _shortfall(band, REQUESTED, SLIVER) == ""


@pytest.mark.parametrize(
    ("requested", "analysed"),
    [
        (REQUESTED, None),
        (REQUESTED, ""),
        ("", HALF),
        ("not wkt at all", HALF),
        (REQUESTED, "not wkt at all"),
    ],
)
def test_unknown_inputs_draw_nothing(band, requested, analysed):
    """欠けているのか全面なのか分からないときは、地図に何も足さない。"""
    assert _shortfall(band, requested, analysed) == ""
