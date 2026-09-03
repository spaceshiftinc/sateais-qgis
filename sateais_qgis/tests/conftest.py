"""Shared fixtures for the tests that need PyQGIS.

**There is exactly one QgsApplication per process.** Qt allows a single
application object, and QGIS does not recover from one being torn down and
another built in its place: the second ``QgsApplication([], False)`` segfaults.
Two modules each owning a module-scoped application is therefore not merely
wasteful, it crashes the run as soon as both are collected.

It is also specifically a ``QgsApplication`` and never a bare ``QApplication``:
``QgsMessageLog.logMessage`` reaches through ``QgsApplication::messageLog()``,
so a plain QApplication left as the process-wide instance segfaults the worker
tests that log — whichever order they happen to run in.

``GUIenabled=False`` plus ``QT_QPA_PLATFORM=offscreen`` keeps this headless; no
window or Dock icon appears.
"""

from __future__ import annotations

import pytest

pyqgis_available = True
try:
    from qgis.core import QgsApplication
except ImportError:
    pyqgis_available = False


@pytest.fixture(scope="session")
def qgis_app():
    """The process-wide QGIS application, created once and reused."""
    if not pyqgis_available:
        pytest.skip("PyQGIS not available in this environment")
    existing = QgsApplication.instance()
    if existing is not None:
        yield existing
        return
    app = QgsApplication([], False)
    app.initQgis()
    yield app
    app.exitQgis()
