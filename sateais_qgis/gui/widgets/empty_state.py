"""Cosmic empty state for the Jobs tab — the first thing a new user sees.

Replaces a bare "No jobs yet" line with a subtle starfield, a friendly line,
and a call-to-action that jumps to the Analysis tab. The starfield is painted
with ``QPainter`` and driven by a ``QTimer`` — the same safe pattern used by
``OrbitingSatellite``: a plain child widget in our own dock, never reparented
into the QGIS message bar (which segfaults on macOS), timer stopped while hidden.
"""

from __future__ import annotations

import math
import random

from qgis.PyQt.QtCore import QCoreApplication, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QBrush, QColor, QPainter, QRadialGradient
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

_STAR_COUNT = 44
_TICK_MS = 66  # ~15 fps — a slow, calm twinkle, easy on the battery
_STAR_SEED = 7  # fixed seed → stable layout across repaints and sessions

_BG_GLOW = QColor(19, 26, 51)  # #131A33 — soft nebula glow near the top
_BG_DEEP = QColor(5, 8, 15)  # #05080F — deep space (matches COSMIC bg)
_STAR_COLOR = QColor(200, 220, 255)


class EmptyState(QWidget):
    """Animated starfield + CTA shown when the Jobs list is empty."""

    start_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._t = 0.0
        self._stars = self._make_stars(_STAR_COUNT)
        self._build_ui()

        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)

    # --- construction --------------------------------------------------------

    @staticmethod
    def _make_stars(n: int) -> list[dict]:
        rng = random.Random(_STAR_SEED)
        stars: list[dict] = []
        for _ in range(n):
            stars.append(
                {
                    "x": rng.random(),
                    "y": rng.random(),
                    "r": rng.uniform(0.6, 1.7),
                    "base": rng.uniform(0.12, 0.55),
                    "amp": rng.uniform(0.10, 0.40),
                    "phase": rng.uniform(0.0, math.tau),
                    "speed": rng.uniform(0.4, 1.2),
                }
            )
        return stars

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 36, 24, 36)
        layout.setSpacing(10)
        layout.addStretch()

        title = QLabel(self.tr("Ready when you are"))
        title.setObjectName("EmptyTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(
            self.tr(
                "Pick an area on the map and run a detection.\nYour jobs and results appear here."
            )
        )
        subtitle.setObjectName("EmptySubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addSpacing(6)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.start_button = QPushButton(self.tr("Start an analysis"))
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.setCursor(Qt.PointingHandCursor)
        self.start_button.clicked.connect(self.start_requested.emit)
        btn_row.addWidget(self.start_button)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()

    # --- animation lifecycle -------------------------------------------------

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

    def _tick(self) -> None:
        if not self.isVisible():
            return
        self._t += _TICK_MS / 1000.0
        self.update()

    # --- painting ------------------------------------------------------------

    def paintEvent(self, event) -> None:  # type: ignore[override]
        rect = self.rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        glow = QRadialGradient(
            rect.width() * 0.5,
            rect.height() * 0.30,
            max(rect.width(), rect.height()) * 0.85,
        )
        glow.setColorAt(0.0, _BG_GLOW)
        glow.setColorAt(1.0, _BG_DEEP)
        painter.fillRect(rect, QBrush(glow))

        painter.setPen(Qt.NoPen)
        for star in self._stars:
            twinkle = star["base"] + star["amp"] * math.sin(self._t * star["speed"] + star["phase"])
            alpha = max(0.0, min(1.0, twinkle))
            color = QColor(_STAR_COLOR)
            color.setAlphaF(alpha)
            painter.setBrush(QBrush(color))
            x = star["x"] * rect.width()
            y = star["y"] * rect.height()
            r = star["r"]
            painter.drawEllipse(int(x - r), int(y - r), int(r * 2), int(r * 2))

        painter.end()

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("EmptyState", message)
