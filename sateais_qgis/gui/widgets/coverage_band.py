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

# 寄せ方は Jobs タブの AOI 表示と揃える（同じ余白・同じ見え方）
from .aoi_preview import ZOOM_PADDING_RATIO, _padded

# 要求範囲: 塗らない破線。widget の aoiStyle と同じ読ませ方
REQUESTED_COLOR = QColor(143, 160, 173, 230)  # #8fa0ad
REQUESTED_WIDTH = 2
# 実際に解析される範囲: SateAIs ブルーの塗り
ANALYSED_COLOR = QColor(0, 159, 232, 220)  # #009FE8
ANALYSED_FILL = QColor(0, 159, 232, 46)
ANALYSED_WIDTH = 2
# 解析されずに残る範囲。青い塗りの「外側」を目で追わせるのは読み取りが遅く、
# 「検知ゼロ」と「そもそも見ていない」の取り違えを生む。落ちる分を直接塗る。
# 色は警告色ではなく無彩色に寄せる: これは異常ではなく「衛星が撮っていない」
# という事実で、地図の主役は解析される範囲の青のほう。要求範囲の破線と同系の
# グレーだが、あちらは破線・こちらは塗りなので描き方で区別が付く
UNCOVERED_COLOR = QColor(124, 138, 148, 170)  # #7C8A94
UNCOVERED_FILL = QColor(124, 138, 148, 48)
UNCOVERED_WIDTH = 1


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
        self._uncovered: QgsRubberBand | None = None
        self._requested_wkt = ""

    def show_requested(self, wkt_4326: str, recenter: bool = False) -> bool:
        """Draw the requested polygon. Returns False for empty/invalid WKT.

        ``recenter`` reframes the canvas onto it. Off by default: after drawing
        on the map the user is already looking at the right place, and moving
        the view under them there would be disorienting. Pasting WKT is the
        opposite case — the area is usually nowhere near the current view, so
        without this the polygon is drawn somewhere the user cannot see.
        """
        self._requested_wkt = wkt_4326
        self._requested = self._draw(
            self._requested,
            wkt_4326,
            stroke=REQUESTED_COLOR,
            fill=QColor(0, 0, 0, 0),
            width=REQUESTED_WIDTH,
            dashed=True,
        )
        if recenter and self._requested is not None:
            self._zoom_to(wkt_4326)
        return self._requested is not None

    def _zoom_to(self, wkt_4326: str) -> None:
        """Frame the canvas on the polygon, with the same padding as the Jobs tab."""
        geometry = self._to_canvas_crs(wkt_4326)
        if geometry is None:
            return
        extent = geometry.boundingBox()
        if extent.isEmpty():
            return
        self.canvas.setExtent(_padded(extent, ZOOM_PADDING_RATIO))
        self.canvas.refresh()

    def show_analysed(self, wkt_4326: str | None) -> bool:
        """Draw the analysed coverage, and the requested area it leaves out.

        Passing None clears both — the shortfall only means anything against a
        coverage the server actually returned.
        """
        self._analysed = self._draw(
            self._analysed,
            wkt_4326 or "",
            stroke=ANALYSED_COLOR,
            fill=ANALYSED_FILL,
            width=ANALYSED_WIDTH,
            dashed=False,
        )
        self._uncovered = self._draw(
            self._uncovered,
            self._uncovered_wkt(wkt_4326),
            stroke=UNCOVERED_COLOR,
            fill=UNCOVERED_FILL,
            width=UNCOVERED_WIDTH,
            dashed=False,
        )
        return self._analysed is not None

    def has_uncovered(self) -> bool:
        """True when part of the requested area is drawn as not analysed."""
        return self._uncovered is not None

    def clear_analysed(self) -> None:
        """Drop the coverage bands only — used when inputs change and the old
        estimate no longer describes what is on screen."""
        self._analysed = self._remove(self._analysed)
        self._uncovered = self._remove(self._uncovered)

    def clear(self) -> None:
        self._requested_wkt = ""
        self._requested = self._remove(self._requested)
        self._analysed = self._remove(self._analysed)
        self._uncovered = self._remove(self._uncovered)

    def _uncovered_wkt(self, analysed_wkt: str | None) -> str:
        """The requested area minus what will be analysed.

        Returns "" when there is nothing to draw — no request, no coverage, or a
        coverage that already contains the whole request. Geometry operations on
        user-drawn shapes can fail (self-intersections, antimeridian crossings);
        a failure here must leave the map as it was rather than raise into the
        estimate flow, so it degrades to drawing nothing.
        """
        if not analysed_wkt or not self._requested_wkt:
            return ""
        requested = QgsGeometry.fromWkt(self._requested_wkt)
        analysed = QgsGeometry.fromWkt(analysed_wkt)
        if requested.isNull() or analysed.isNull():
            return ""
        try:
            remainder = requested.difference(analysed)
        except Exception:  # noqa: BLE001
            return ""
        if remainder.isNull() or remainder.isEmpty():
            return ""
        # 数値誤差で残る髪の毛のような差分を「解析されない範囲」として塗ると、
        # 全面カバーでも警告色が出てしまう。要求面積に対する比で捨てる
        if requested.area() > 0 and remainder.area() / requested.area() < 0.005:
            return ""
        return remainder.asWkt()

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
        geometry = self._to_canvas_crs(wkt_4326)
        if geometry is None:
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

    def _to_canvas_crs(self, wkt_4326: str) -> QgsGeometry | None:
        """Parse WKT and project it onto the canvas, or None if that is not possible."""
        if not wkt_4326:
            return None
        geometry = QgsGeometry.fromWkt(wkt_4326)
        if geometry.isNull() or geometry.isEmpty():
            return None
        source_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        if source_crs == canvas_crs:
            return geometry
        transform = QgsCoordinateTransform(source_crs, canvas_crs, QgsProject.instance())
        projected = QgsGeometry(geometry)
        try:
            projected.transform(transform)
        except Exception:  # noqa: BLE001
            # 投影できない座標系では描かない。ずれた図形を出すより出さない
            return None
        return projected

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
