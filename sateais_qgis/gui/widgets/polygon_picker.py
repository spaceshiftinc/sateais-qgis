"""Drag-to-select rectangular AOI on the map canvas."""

from __future__ import annotations

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsGeometry,
    QgsPointXY,
    QgsWkbTypes,
)
from qgis.gui import QgsMapCanvas, QgsMapTool, QgsRubberBand
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QCursor, QMouseEvent

from ...core.geometry_adapter import polygon_area_km2, qgs_geometry_to_wkt_4326

RUBBER_BAND_COLOR = QColor(0, 212, 255, 180)  # Cosmic Cyan, 70% alpha
RUBBER_BAND_WIDTH = 2


class PolygonPicker(QgsMapTool):
    """Press-drag-release map tool that emits the rectangle as a polygon WKT.

    Press anchors the first corner, dragging sizes the rectangle, releasing
    finishes the pick. Esc cancels. The resulting WKT (EPSG:4326) and area
    in km² are emitted via ``polygon_finished``.
    """

    polygon_finished = pyqtSignal(str, float)
    polygon_cancelled = pyqtSignal()
    area_changed = pyqtSignal(float)  # live area in km² while dragging

    def __init__(self, canvas: QgsMapCanvas) -> None:
        super().__init__(canvas)
        self.canvas = canvas
        self.setCursor(QCursor(Qt.CrossCursor))

        self._anchor: QgsPointXY | None = None

        self._rubber_band = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
        self._rubber_band.setStrokeColor(RUBBER_BAND_COLOR)
        self._rubber_band.setWidth(RUBBER_BAND_WIDTH)
        self._rubber_band.setFillColor(QColor(0, 212, 255, 90))

    def canvasPressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            return
        self._anchor = self.toMapCoordinates(event.pos())
        self._draw_rectangle(self._anchor)

    def canvasMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._anchor is None:
            return
        self._draw_rectangle(self.toMapCoordinates(event.pos()))

    def canvasReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton or self._anchor is None:
            return
        end = self.toMapCoordinates(event.pos())
        if end.x() == self._anchor.x() or end.y() == self._anchor.y():
            # Zero-area drag (single click, no movement).
            self._cancel()
            return
        self._finish(self._anchor, end)

    def keyPressEvent(self, event):  # type: ignore[override]
        if event.key() == Qt.Key_Escape:
            self._cancel()

    def deactivate(self) -> None:
        self._reset()
        super().deactivate()

    def _draw_rectangle(self, current: QgsPointXY) -> None:
        if self._anchor is None:
            return
        ring = _rectangle_corners(self._anchor, current)
        ring.append(ring[0])
        geometry = QgsGeometry.fromPolygonXY([ring])
        # setToGeometry replaces the entire rubber band geometry atomically;
        # this works reliably during a mouse drag, unlike incremental addPoint.
        self._rubber_band.setToGeometry(geometry, None)
        self._rubber_band.show()

        # Emit the live area so the message bar can show "… — 42.0 km²" as the
        # user sizes the box. Best-effort: skip if the geometry can't be measured
        # yet (degenerate box at press time).
        source_crs = self.canvas.mapSettings().destinationCrs()
        try:
            self.area_changed.emit(polygon_area_km2(geometry, source_crs))
        except Exception:  # noqa: BLE001
            pass

    def _finish(self, anchor: QgsPointXY, end: QgsPointXY) -> None:
        ring = _rectangle_corners(anchor, end)
        ring.append(ring[0])  # close the ring
        polygon_geometry = QgsGeometry.fromPolygonXY([ring])

        if polygon_geometry.isEmpty():
            self._cancel()
            return

        source_crs: QgsCoordinateReferenceSystem = self.canvas.mapSettings().destinationCrs()

        try:
            wkt = qgs_geometry_to_wkt_4326(polygon_geometry, source_crs)
            area = polygon_area_km2(polygon_geometry, source_crs)
        except ValueError:
            self._cancel()
            return

        self._reset()
        self.polygon_finished.emit(wkt, area)

    def _cancel(self) -> None:
        self._reset()
        self.polygon_cancelled.emit()

    def _reset(self) -> None:
        self._anchor = None
        self._rubber_band.reset(QgsWkbTypes.PolygonGeometry)

    def __del__(self) -> None:
        try:
            scene = self.canvas.scene()
            if scene is not None and self._rubber_band is not None:
                scene.removeItem(self._rubber_band)
        except Exception:  # noqa: BLE001
            pass


def _rectangle_corners(a: QgsPointXY, b: QgsPointXY) -> list[QgsPointXY]:
    """Return the four corners of the rectangle spanned by points a and b."""
    return [
        QgsPointXY(a.x(), a.y()),
        QgsPointXY(b.x(), a.y()),
        QgsPointXY(b.x(), b.y()),
        QgsPointXY(a.x(), b.y()),
    ]
