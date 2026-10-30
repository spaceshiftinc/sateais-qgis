"""Submit is enabled exactly when the form is complete and its estimate is back and allows it."""

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
    from sateais_qgis.core import client_factory, wording
    from sateais_qgis.core.api.types import Preview
    from sateais_qgis.gui.widgets.analysis_panel import AnalysisPanel
    from sateais_qgis.workers import submit_task
    from sateais_qgis.workers.submit_task import ERROR_SERVER_ERROR, ERROR_VALIDATION_FAILED

WKT = "POLYGON((139.6 35.6, 139.8 35.6, 139.8 35.8, 139.6 35.8, 139.6 35.6))"
SMALLER_WKT = "POLYGON((139.6 35.6, 139.7 35.6, 139.7 35.7, 139.6 35.7, 139.6 35.6))"
AREA_LIMIT_SERVER = "Polygon area (52.6 km²) exceeds 50 km² limit for endpoint 'timeseries'"


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
    _complete(panel)
    _estimate_ok(panel)
    assert panel.submit_button.isEnabled()

    panel.set_pick_in_progress(True)
    assert not panel.submit_button.isEnabled()
    panel.set_pick_in_progress(False)
    assert panel.submit_button.isEnabled()


def _complete(panel):
    """Complete the form. Its estimate is now pending, so Submit waits for it."""
    panel.form.set_analysis_type("newbuilding")
    panel.set_polygon(WKT, 1.0)
    assert not panel.submit_button.isEnabled()


def _estimate_ok(panel):
    panel._on_preview_finished(True, Preview(), panel._preview_seq)


def _estimate_fails(panel, payload):
    # The first failure is retried quietly; the second one is final.
    panel._preview_retried = True
    panel._on_preview_finished(False, payload, panel._preview_seq)


def test_submit_waits_for_the_estimate_of_the_current_inputs(panel):
    _complete(panel)
    stale = panel._preview_seq
    panel.set_polygon(SMALLER_WKT, 0.5)

    # An answer computed for the previous inputs does not release it
    panel._on_preview_finished(True, Preview(), stale)
    assert not panel.submit_button.isEnabled()

    _estimate_ok(panel)
    assert panel.submit_button.isEnabled()


def test_a_quiet_retry_keeps_waiting(panel):
    _complete(panel)
    panel._on_preview_finished(False, ERROR_SERVER_ERROR, panel._preview_seq)
    assert not panel.submit_button.isEnabled()


def test_a_rejected_estimate_holds_submit_until_the_inputs_change(panel):
    _complete(panel)
    _estimate_fails(panel, ERROR_VALIDATION_FAILED)
    assert not panel.submit_button.isEnabled()

    panel.set_polygon(SMALLER_WKT, 0.5)
    assert not panel.submit_button.isEnabled()  # waiting for the new estimate
    _estimate_ok(panel)
    assert panel.submit_button.isEnabled()


def test_the_area_limit_sentence_holds_submit(panel):
    _complete(panel)
    _estimate_fails(panel, wording.area_limit_reason(AREA_LIMIT_SERVER))
    assert not panel.submit_button.isEnabled()


def test_no_usable_scene_holds_submit(panel):
    _complete(panel)
    preview = Preview(warnings=[{"code": "SCENE_NOT_FOUND", "message": "none"}])
    panel._on_preview_finished(True, preview, panel._preview_seq)
    assert not panel.submit_button.isEnabled()


def test_a_usable_estimate_keeps_submit(panel):
    _complete(panel)
    preview = Preview(warnings=[{"code": "LOW_AOI_COVERAGE", "message": "partial"}])
    panel._on_preview_finished(True, preview, panel._preview_seq)
    assert panel.submit_button.isEnabled()


# Names, not values: the constants only exist when PyQGIS does, and parameters are
# built at collection time, even for skipped tests
@pytest.mark.parametrize(
    "code_name",
    [
        "ERROR_SERVER_ERROR",
        "ERROR_NETWORK_ERROR",
        "ERROR_RATE_LIMITED",
        "ERROR_INSUFFICIENT_CREDITS",
        "ERROR_AUTH_FAILED",
        "ERROR_PERMISSION_DENIED",
    ],
)
def test_failures_that_can_clear_without_an_edit_leave_it_to_the_server(panel, code_name):
    _complete(panel)
    _estimate_fails(panel, getattr(submit_task, code_name))
    assert panel.submit_button.isEnabled()


def test_closing_the_dock_releases_the_hold_with_the_estimate(panel):
    _complete(panel)
    _estimate_fails(panel, ERROR_VALIDATION_FAILED)
    panel.discard_estimate()
    assert panel.submit_button.isEnabled()
