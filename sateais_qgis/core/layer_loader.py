"""Convert SateAIs GeoJSON results into QGIS memory layers and add them to the project."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from typing import Any

from qgis.core import (
    QgsCoordinateTransform,
    QgsFeature,
    QgsFillSymbol,
    QgsGeometry,
    QgsLayerTreeGroup,
    QgsMarkerSymbol,
    QgsProject,
    QgsRectangle,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
)
from qgis.PyQt.QtGui import QColor

# Quiet slate outline for the user's AOI frame — deliberately duller than any
# detection colour so the frame never competes with results drawn inside it.
_AOI_OUTLINE_COLOR = "#94a3b8"

RESULTS_GROUP_NAME = "SateAIs Results"
ZOOM_PADDING_RATIO = 0.15  # 15% buffer around features so they aren't at the very edge

# Per-detection style (border RGB + fill alpha). Choices match the COSMIC palette
# and keep good contrast over satellite and OSM basemaps.
_STYLE_BY_TYPE: dict[str, dict[str, Any]] = {
    "ship": {"color": "#00d4ff", "fill_alpha": 100, "point_size": 4},
    "oilslick": {"color": "#a855f7", "fill_alpha": 100, "point_size": 4},
    "newbuilding": {"color": "#10b981", "fill_alpha": 90},
    "disappearbuilding": {"color": "#ef4444", "fill_alpha": 90},
    "timeseries": {"color": "#f59e0b", "fill_alpha": 90},
}
_DEFAULT_STYLE = {"color": "#00d4ff", "fill_alpha": 90, "point_size": 4}


def load_geojson_as_layer(
    geojson: dict[str, Any],
    layer_name: str,
    analysis_type: str,
) -> QgsVectorLayer:
    """Materialise a GeoJSON FeatureCollection as an in-memory QgsVectorLayer.

    Writes the GeoJSON to a temp file so the OGR driver can validate and parse
    it; the file stays under the system temp dir (cleaned up by the OS).
    """
    fd, path = tempfile.mkstemp(prefix="sateais_", suffix=".geojson")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(geojson, f)
    except Exception:
        os.close(fd)
        raise

    layer = QgsVectorLayer(path, layer_name, "ogr")
    if not layer.isValid():
        raise ValueError(f"Could not load GeoJSON as a QGIS layer (file: {path})")

    apply_style(layer, analysis_type)
    return layer


def load_aoi_as_layer(polygon_wkt: str, layer_name: str) -> QgsVectorLayer | None:
    """Materialise the user-drawn AOI as an outline-only memory layer.

    Returned as a normal project layer (instead of a canvas rubber band) so
    the user can toggle the frame on/off in the layer tree when it overlaps
    the detections inside it. Returns None when the WKT cannot be parsed.
    """
    geometry = QgsGeometry.fromWkt(polygon_wkt)
    if geometry.isNull() or geometry.isEmpty():
        return None

    layer = QgsVectorLayer("Polygon?crs=EPSG:4326", layer_name, "memory")
    # The AOI frame is derived data (regenerable from the tracked job's WKT),
    # so exclude it from QGIS's "temporary scratch layers will be lost" warning
    # on exit — otherwise every result load makes closing QGIS nag the user.
    layer.setCustomProperty("skipMemoryLayersCheck", 1)
    feature = QgsFeature()
    feature.setGeometry(geometry)
    layer.dataProvider().addFeatures([feature])
    layer.updateExtents()

    symbol = QgsFillSymbol.createSimple(
        {
            "style": "no",  # no fill — only the frame, so detections stay visible
            "outline_color": _AOI_OUTLINE_COLOR,
            "outline_width": "0.5",
            "outline_style": "dash",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    return layer


def add_aoi_to_project(layer: QgsVectorLayer) -> None:
    """Add an AOI layer under the results group, below the result layers.

    No zooming here — the result layer that accompanies it drives the canvas.
    """
    QgsProject.instance().addMapLayer(layer, addToLegend=False)
    _ensure_results_group().addLayer(layer)


def add_to_project(layer: QgsVectorLayer, iface) -> None:
    """Add the layer to the project under the 'SateAIs Results' group and zoom to it."""
    QgsProject.instance().addMapLayer(layer, addToLegend=False)
    group = _ensure_results_group()
    group.insertLayer(0, layer)

    canvas = iface.mapCanvas()
    extent = layer.extent()
    if extent.isEmpty():
        return

    # The layer extent is in the layer's own CRS (EPSG:4326 for our GeoJSON);
    # transform into the canvas projection so setExtent lands the user where
    # the features actually are.
    layer_crs = layer.crs()
    canvas_crs = canvas.mapSettings().destinationCrs()
    if layer_crs.isValid() and layer_crs != canvas_crs:
        transform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
        # Fall back to the untransformed extent rather than skipping zoom.
        with contextlib.suppress(Exception):
            extent = transform.transformBoundingBox(extent)

    canvas.setExtent(_padded(extent, ZOOM_PADDING_RATIO))
    canvas.refresh()


def _padded(extent: QgsRectangle, ratio: float) -> QgsRectangle:
    """Return a slightly enlarged copy of the rectangle so features don't sit at the edge."""
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


def apply_style(layer: QgsVectorLayer, analysis_type: str) -> None:
    """Apply a single-symbol renderer keyed by analysis type."""
    style = _STYLE_BY_TYPE.get(analysis_type, _DEFAULT_STYLE)
    base_color = QColor(style["color"])
    fill_color = QColor(base_color)
    fill_color.setAlpha(int(style.get("fill_alpha", 90)))

    geometry_type = layer.geometryType()
    # 0 = Point, 1 = Line, 2 = Polygon (QgsWkbTypes.GeometryType enum values)
    if geometry_type == 0:
        symbol = QgsMarkerSymbol.createSimple(
            {
                "name": "circle",
                "color": base_color.name(),
                "size": str(style.get("point_size", 4)),
                "outline_color": "white",
                "outline_width": "0.4",
            }
        )
    else:
        symbol = QgsFillSymbol.createSimple(
            {
                "color": fill_color.name(QColor.NameFormat.HexArgb),
                "color_named": fill_color.name(),
                "outline_color": base_color.name(),
                "outline_width": "0.6",
            }
        )
        # The dict-based color above doesn't honour alpha reliably; set explicitly.
        symbol.setColor(fill_color)

    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.triggerRepaint()


def _ensure_results_group() -> QgsLayerTreeGroup:
    root = QgsProject.instance().layerTreeRoot()
    existing = root.findGroup(RESULTS_GROUP_NAME)
    if existing is not None:
        return existing
    return root.insertGroup(0, RESULTS_GROUP_NAME)


def build_layer_name(
    analysis_type: str,
    job_id: str,
    submitted_at: str,
    count: int | None = None,
) -> str:
    """Stable, plain-text layer name. ``submitted_at`` is ISO 8601.

    When ``count`` is given, the detected-feature count is appended so the
    layer tree reads e.g. ``SateAIs ship a1b2c3d4 (2026-07-03) · 23``.
    """
    short = job_id.split("-")[0] if job_id else "unknown"
    date = submitted_at[:10] if submitted_at else "n/a"
    name = f"SateAIs {analysis_type} {short} ({date})"
    if count is not None and count >= 0:
        name += f" · {count}"
    return name


def build_aoi_layer_name(analysis_type: str, job_id: str) -> str:
    """Layer-tree name for the AOI frame, e.g. ``SateAIs AOI ship a1b2c3d4``."""
    short = job_id.split("-")[0] if job_id else "unknown"
    return f"SateAIs AOI {analysis_type} {short}"


__all__ = [
    "RESULTS_GROUP_NAME",
    "load_geojson_as_layer",
    "load_aoi_as_layer",
    "add_to_project",
    "add_aoi_to_project",
    "apply_style",
    "build_layer_name",
    "build_aoi_layer_name",
]
