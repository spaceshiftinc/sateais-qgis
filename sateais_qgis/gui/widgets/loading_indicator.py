"""Small ``QWidget`` that draws a satellite orbiting Earth.

Used in the Jobs tab message bar while ``ResultLoaderWorker`` fetches a
completed job's result GeoJSON. The animation is intentionally slow (one
full orbit every ~3 seconds) so it registers as "working" without being
distracting on the periphery of the user's attention.

The whole widget is painted with ``QPainter`` — no SVG asset is required,
which keeps the plugin ZIP smaller and avoids ``QSvgRenderer`` availability
concerns on stripped-down QGIS builds.

IMPORTANT (macOS): this widget must live inside a widget tree we own (e.g. a
JobCard in our dock), NOT be reparented into the QGIS message bar, and must NOT
set ``WA_TranslucentBackground``. An animated, translucent, repainting widget
reparented into the Cocoa-backed message bar segfaults QGIS on macOS (the
QTimer paint event is delivered to a stale native surface). Keeping it as a
plain, opaque-friendly child widget avoids that entire failure class.
"""

from __future__ import annotations

import math

from qgis.PyQt.QtCore import QSize, Qt, QTimer
from qgis.PyQt.QtGui import QBrush, QColor, QPainter, QPen, QRadialGradient
from qgis.PyQt.QtWidgets import QWidget

# Colours picked from the SateAIs COSMIC palette (styles.py). Keeping them
# hard-coded here (rather than QSS) because QPainter draws pixels directly.
_EARTH_CORE = QColor("#0D1326")
_EARTH_RIM = QColor(0, 160, 233, 180)
_EARTH_GLOW_INNER = QColor(0, 160, 233, 90)
_EARTH_GLOW_OUTER = QColor(0, 160, 233, 0)
_ORBIT_COLOR = QColor(91, 194, 242, 90)
_SATELLITE_BODY = QColor("#E6EAF5")
_SATELLITE_PANEL = QColor("#00A0E9")

_TICK_MS = 33  # ~30 fps for the Cosmos animation
_ORBIT_MS_PER_TURN = 3000  # one orbit every 3 seconds


class OrbitingSatellite(QWidget):
    """Compact animated icon: a small satellite tracing an ellipse around Earth."""

    def __init__(self, size: int = 24, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._angle = 0.0
        self.setFixedSize(QSize(size, size))
        # NOTE: deliberately NOT WA_TranslucentBackground — see module docstring.
        # The paintEvent simply doesn't fill the background, so the parent
        # (the JobCard) shows through the corners without any native-surface
        # compositing.

        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._advance)

    # --- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def showEvent(self, event) -> None:  # type: ignore[override]
        self.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # type: ignore[override]
        self.stop()
        super().hideEvent(event)

    # --- animation -----------------------------------------------------------

    def _advance(self) -> None:
        # Skip repaint work while hidden (the timer may still be ticking during
        # a hide/show transition); update() on a hidden widget is a no-op anyway.
        if not self.isVisible():
            return
        self._angle = (self._angle + (360.0 * _TICK_MS / _ORBIT_MS_PER_TURN)) % 360.0
        self.update()

    # --- painting ------------------------------------------------------------

    def paintEvent(self, event) -> None:  # type: ignore[override]
        rect = self.rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        cx = rect.width() / 2.0
        cy = rect.height() / 2.0
        earth_radius = min(rect.width(), rect.height()) * 0.28

        # Soft radial glow so the icon reads as a planet rather than a flat dot.
        glow = QRadialGradient(cx, cy, earth_radius * 2.2)
        glow.setColorAt(0.0, _EARTH_GLOW_INNER)
        glow.setColorAt(1.0, _EARTH_GLOW_OUTER)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(
            int(cx - earth_radius * 2.2),
            int(cy - earth_radius * 2.2),
            int(earth_radius * 4.4),
            int(earth_radius * 4.4),
        )

        # Orbit ellipse (slightly wider than tall for a subtle 3D feel).
        orbit_rx = earth_radius * 1.85
        orbit_ry = earth_radius * 1.35
        pen = QPen(_ORBIT_COLOR)
        pen.setWidthF(1.0)
        pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(
            int(cx - orbit_rx),
            int(cy - orbit_ry),
            int(orbit_rx * 2),
            int(orbit_ry * 2),
        )

        # Earth body.
        painter.setPen(QPen(_EARTH_RIM, 1.0))
        painter.setBrush(QBrush(_EARTH_CORE))
        painter.drawEllipse(
            int(cx - earth_radius),
            int(cy - earth_radius),
            int(earth_radius * 2),
            int(earth_radius * 2),
        )

        # Satellite: small square body + two solar panels, positioned on the
        # orbit ellipse and rotated so panels stay aligned with the tangent.
        radians = math.radians(self._angle)
        sat_x = cx + orbit_rx * math.cos(radians)
        sat_y = cy + orbit_ry * math.sin(radians)

        painter.save()
        painter.translate(sat_x, sat_y)
        # Panels align roughly with the orbit tangent for a satellite-y look.
        painter.rotate(self._angle + 90.0)

        body = max(1.5, earth_radius * 0.28)
        panel_w = body * 2.0
        panel_h = body * 0.5

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(_SATELLITE_PANEL))
        painter.drawRect(int(-panel_w - body * 0.4), int(-panel_h / 2), int(panel_w), int(panel_h))
        painter.drawRect(int(body * 0.4), int(-panel_h / 2), int(panel_w), int(panel_h))

        painter.setBrush(QBrush(_SATELLITE_BODY))
        painter.drawRect(int(-body / 2), int(-body / 2), int(body), int(body))
        painter.restore()

        painter.end()
