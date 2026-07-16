"""Transient AOI overlay drawn with QgsRubberBand on the map canvas."""

from __future__ import annotations

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsProject,
    QgsRectangle,
    QgsWkbTypes,
)
from qgis.gui import QgsMapCanvas, QgsRubberBand
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor

PREVIEW_COLOR = QColor(0, 160, 233, 220)  # SateAIs blue
PREVIEW_FILL = QColor(0, 160, 233, 60)
PREVIEW_WIDTH = 2

ZOOM_PADDING_RATIO = 0.1  # 10% buffer around the AOI on zoom


class AoiPreview:
    """Transient AOI overlay. Each call to ``show_polygon`` replaces the previous
    overlay (we tear the rubber band down and rebuild it; a plain ``reset()``
    leaves stale visuals on some QGIS builds)."""

    def __init__(self, canvas: QgsMapCanvas) -> None:
        self.canvas = canvas
        self._rubber_band: QgsRubberBand | None = None

    def show_polygon(self, wkt_4326: str, zoom_to_fit: bool = True) -> bool:
        """Render the polygon (WKT in EPSG:4326) as a rubber band overlay.

        Args:
            wkt_4326: polygon geometry in EPSG:4326.
            zoom_to_fit: when True (the default, used from the Jobs tab),
                reframe the canvas to the AOI. When False (used right after the
                user drags a polygon on the map), keep the current view — the
                user just drew there and is already looking at the right place.

        Returns False if the WKT is empty or invalid.
        """
        if not wkt_4326:
            return False
        geometry = QgsGeometry.fromWkt(wkt_4326)
        if geometry.isNull() or geometry.isEmpty():
            return False

        source_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        if source_crs != canvas_crs:
            transform = QgsCoordinateTransform(source_crs, canvas_crs, QgsProject.instance())
            geometry = QgsGeometry(geometry)
            try:
                geometry.transform(transform)
            except Exception:  # noqa: BLE001
                return False

        self._discard_rubber_band()
        self._rubber_band = self._make_rubber_band()
        self._rubber_band.setToGeometry(geometry, None)
        self._rubber_band.show()

        if zoom_to_fit:
            extent = geometry.boundingBox()
            if not extent.isEmpty():
                self.canvas.setExtent(_padded(extent, ZOOM_PADDING_RATIO))
        self.canvas.refresh()
        return True

    def clear(self) -> None:
        self._discard_rubber_band()
        self.canvas.refresh()

    def dispose(self) -> None:
        """Release the rubber band (call on dock teardown)."""
        self._discard_rubber_band()

    # --- internal ------------------------------------------------------------

    def _make_rubber_band(self) -> QgsRubberBand:
        rb = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        rb.setStrokeColor(PREVIEW_COLOR)
        rb.setFillColor(PREVIEW_FILL)
        rb.setWidth(PREVIEW_WIDTH)
        rb.setLineStyle(Qt.DashLine)
        return rb

    def _discard_rubber_band(self) -> None:
        if self._rubber_band is None:
            return
        self._rubber_band.reset(QgsWkbTypes.PolygonGeometry)
        try:
            scene = self.canvas.scene()
            if scene is not None:
                scene.removeItem(self._rubber_band)
        except Exception:  # noqa: BLE001
            pass
        self._rubber_band = None


def _padded(extent: QgsRectangle, ratio: float) -> QgsRectangle:
    """Return a slightly enlarged copy of the rectangle for comfortable zoom."""
    width = extent.width() or 1.0
    height = extent.height() or 1.0
    dx = width * ratio
    dy = height * ratio
    return QgsRectangle(
        extent.xMinimum() - dx,
        extent.yMinimum() - dy,
        extent.xMaximum() + dx,
        extent.yMaximum() + dy,
    )
