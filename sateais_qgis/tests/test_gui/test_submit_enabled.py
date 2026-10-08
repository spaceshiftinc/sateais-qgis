"""Submit is enabled exactly when the form is complete."""

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
    from sateais_qgis.core import client_factory
    from sateais_qgis.gui.widgets.analysis_panel import AnalysisPanel

WKT = "POLYGON((139.6 35.6, 139.8 35.6, 139.8 35.8, 139.6 35.8, 139.6 35.6))"


@pytest.fixture
def panel(qgis_app, monkeypatch):
    monkeypatch.setattr(client_factory, "has_api_key", lambda: True)
    return AnalysisPanel(iface=None)


def test_starts_disabled(panel):
    assert not panel.submit_button.isEnabled()


def test_finishing_a_pick_does_not_enable_an_incomplete_form(panel):
    panel.set_pick_in_progress(True)
    panel.set_pick_in_progress(False)
    assert not panel.submit_button.isEnabled()


def test_a_complete_form_enables_submit_and_a_pick_pauses_it(panel):
    panel.form.set_analysis_type("newbuilding")
    panel.set_polygon(WKT, 1.0)
    assert panel.submit_button.isEnabled()

    panel.set_pick_in_progress(True)
    assert not panel.submit_button.isEnabled()
    panel.set_pick_in_progress(False)
    assert panel.submit_button.isEnabled()
