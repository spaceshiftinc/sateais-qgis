"""Requested vs analysed area, drawn together on the map canvas.

This is the part of the MCP map widget worth keeping: the requested rectangle
and the area the satellites actually cover are shown *at the same time*, so the
gap between them is visible before any credits are spent. With only one of the
two on screen, an uncovered strip reads as "nothing detected there".

Requested is a dashed grey outline (no fill) and analysed is the SateAIs blue
fill — the same reading as the widget's ``aoiStyle`` / coverage layer.
"""

from __future__ import annotations

import contextlib

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsProject,
    QgsWkbTypes,
)
from qgis.gui import QgsMapCanvas, QgsRubberBand
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor

# 要求範囲: 塗らない破線。widget の aoiStyle と同じ読ませ方
REQUESTED_COLOR = QColor(143, 160, 173, 230)  # #8fa0ad
REQUESTED_WIDTH = 2
# 実際に解析される範囲: SateAIs ブルーの塗り
ANALYSED_COLOR = QColor(0, 159, 232, 220)  # #009FE8
ANALYSED_FILL = QColor(0, 159, 232, 46)
ANALYSED_WIDTH = 2


class CoverageBand:
    """Transient overlay for the requested polygon and the analysed coverage.

    Never zooms the canvas: the user has just drawn here and is already looking
    at the right place. Both bands are torn down and rebuilt on each update —
    ``reset()`` alone leaves stale visuals on some QGIS builds.
    """

    def __init__(self, canvas: QgsMapCanvas) -> None:
        self.canvas = canvas
        self._requested: QgsRubberBand | None = None
        self._analysed: QgsRubberBand | None = None

    def show_requested(self, wkt_4326: str) -> bool:
        """Draw the requested polygon. Returns False for empty/invalid WKT."""
        self._requested = self._draw(
            self._requested,
            wkt_4326,
            stroke=REQUESTED_COLOR,
            fill=QColor(0, 0, 0, 0),
            width=REQUESTED_WIDTH,
            dashed=True,
        )
        return self._requested is not None

    def show_analysed(self, wkt_4326: str | None) -> bool:
        """Draw the analysed coverage. Passing None clears just this band."""
        self._analysed = self._draw(
            self._analysed,
            wkt_4326 or "",
            stroke=ANALYSED_COLOR,
            fill=ANALYSED_FILL,
            width=ANALYSED_WIDTH,
            dashed=False,
        )
        return self._analysed is not None

    def clear_analysed(self) -> None:
        """Drop the coverage band only — used when inputs change and the old
        estimate no longer describes what is on screen."""
        self._analysed = self._remove(self._analysed)

    def clear(self) -> None:
        self._requested = self._remove(self._requested)
        self._analysed = self._remove(self._analysed)

    # --- internals -----------------------------------------------------------

    def _draw(
        self,
        band: QgsRubberBand | None,
        wkt_4326: str,
        stroke: QColor,
        fill: QColor,
        width: int,
        dashed: bool,
    ) -> QgsRubberBand | None:
        band = self._remove(band)
        if not wkt_4326:
            return None
        geometry = QgsGeometry.fromWkt(wkt_4326)
        if geometry.isNull() or geometry.isEmpty():
            return None

        source_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        if source_crs != canvas_crs:
            transform = QgsCoordinateTransform(source_crs, canvas_crs, QgsProject.instance())
            geometry = QgsGeometry(geometry)
            try:
                geometry.transform(transform)
            except Exception:  # noqa: BLE001
                # 投影できない座標系では描かない。ずれた図形を出すより出さない
                return None

        band = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        band.setColor(stroke)
        band.setFillColor(fill)
        band.setWidth(width)
        if dashed:
            band.setLineStyle(Qt.PenStyle.DashLine)
        band.setToGeometry(geometry, None)
        band.show()
        return band

    @staticmethod
    def _remove(band: QgsRubberBand | None) -> None:
        if band is not None:
            with contextlib.suppress(Exception):
                band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
                band.hide()
                scene = band.scene()
                if scene is not None:
                    scene.removeItem(band)
        return None


__all__ = ["CoverageBand"]
