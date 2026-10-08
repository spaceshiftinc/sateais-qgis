"""Closing the dock hides it; job tracking must carry on in the background."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pyqgis_available = True
try:
    from qgis.gui import QgsMapCanvas
except ImportError:
    pyqgis_available = False

pytestmark = pytest.mark.skipif(
    not pyqgis_available, reason="PyQGIS not available in this environment"
)

if pyqgis_available:
    from sateais_qgis.core import client_factory, job_tracker, settings
    from sateais_qgis.gui.dock_widget import SateAIsDockWidget


class FakeSettings:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def value(self, key, default=None, type=None):
        return self._store.get(key, default)

    def setValue(self, key, value) -> None:
        self._store[key] = value

    def remove(self, key) -> None:
        self._store.pop(key, None)


@pytest.fixture
def dock(qgis_app, monkeypatch):
    store = FakeSettings()
    monkeypatch.setattr(settings, "_settings", lambda: store)
    monkeypatch.setattr(job_tracker, "_settings", lambda: store)
    monkeypatch.setattr(client_factory, "has_api_key", lambda: False)
    canvas = QgsMapCanvas()
    iface = SimpleNamespace(mapCanvas=lambda: canvas, messageBar=lambda: MagicMock())
    widget = SateAIsDockWidget(iface)
    widget._test_canvas = canvas  # keep the canvas alive for the dock's lifetime
    return widget


def test_closing_keeps_polling_and_drops_the_pending_estimate(dock):
    task = MagicMock()
    dock.jobs_panel._poll_task = task
    dock.analysis_panel._preview_timer.start()

    dock.close()

    assert dock.jobs_panel._poll_task is task
    task.cancel.assert_not_called()
    assert not dock.analysis_panel._preview_timer.isActive()
