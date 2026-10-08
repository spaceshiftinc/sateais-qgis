"""The legend's "Not covered" entry follows what the band actually draws."""

from __future__ import annotations

import pytest

pyqgis_available = True
try:
    from qgis.core import QgsApplication  # noqa: F401
except ImportError:
    pyqgis_available = False

pytestmark = pytest.mark.skipif(
    not pyqgis_available, reason="PyQGIS not available in this environment"
)

if pyqgis_available:
    from sateais_qgis.core.api.types import Preview, PreviewCoverage, PreviewCredits
    from sateais_qgis.gui.widgets.estimate_card import EstimateCard

POLYGON = "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))"


def _preview(ratio: float) -> Preview:
    return Preview(
        area_sqkm=100.0,
        credits=PreviewCredits(estimated=1.0, balance=10.0, sufficient=True),
        coverage=PreviewCoverage(
            method="estimated", ratio=ratio, requested_area_sqkm=100.0, polygon=POLYGON
        ),
        warnings=[],
    )


@pytest.fixture
def card(qgis_app):
    return EstimateCard(None)


def test_a_real_shortfall_is_in_the_legend(card):
    card.show_preview(_preview(0.9))
    assert card._uncovered_box.isVisibleTo(card)


def test_a_gap_too_small_to_draw_is_not_in_the_legend(card):
    # 99.8% covered: the band drops a 0.2% sliver as noise, so the legend must too.
    card.show_preview(_preview(0.998))
    assert not card._uncovered_box.isVisibleTo(card)


def test_full_coverage_has_no_shortfall_entry(card):
    card.show_preview(_preview(1.0))
    assert not card._uncovered_box.isVisibleTo(card)
