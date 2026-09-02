"""Convert SateAIs GeoJSON results into QGIS memory layers and add them to the project."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from typing import Any

from qgis.core import (
    Qgis,
    QgsCentroidFillSymbolLayer,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFillSymbol,
    QgsGeometry,
    QgsLayerTreeGroup,
    QgsMarkerSymbol,
    QgsMessageLog,
    QgsProject,
    QgsRectangle,
    QgsRuleBasedRenderer,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
)
from qgis.PyQt.QtGui import QColor

from . import result_stats

LOG_TAG = "SateAIs"

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


def type_color(analysis_type: str | None) -> str:
    """Border colour for the analysis type.

    This dict is the single source of the type palette (the MCP widget copies
    these values); icons and panels must read colours through here.
    """
    style = _STYLE_BY_TYPE.get(analysis_type or "", _DEFAULT_STYLE)
    return str(style["color"])


# --- signed-change ramp ------------------------------------------------------
# Diverging scheme for results whose value carries a direction as well as a
# magnitude. Direction is hue, magnitude is depth within that hue, and the
# midpoint is achromatic — never a third hue. Red = increase and blue = decrease
# match the colours the server itself emits and the web viewer's legend, so one
# result reads the same way in QGIS as it does in the console.
#
# Checked for colour-vision deficiency rather than eyeballed: the pair most at
# risk of confusion (the two pale arms) separates by ΔE 11.9 under deuteranopia
# and 20.2 under tritanopia, against a target of 8.
_CHANGE_INCREASE_STRONG = "#c2312f"
_CHANGE_INCREASE = "#f0a0a0"
_CHANGE_DECREASE = "#9ec5f4"
_CHANGE_DECREASE_STRONG = "#2a78d6"
# Achromatic midpoint. Unchanged cells are drawn as a hairline outline with no
# fill: on a real job 2402 of 2409 cells land here, and filling 99.7% of the AOI
# produces a wall of colour that buries the findings whatever hue it uses. The
# hairline still distinguishes "analysed, no change" from "not analysed".
_CHANGE_NEUTRAL = "#898781"

_DEVIATION_FIELD = "deviation"
_SIGNIFICANT = result_stats.SIGNIFICANT_DEVIATION
_STRONG = result_stats.STRONG_DEVIATION

# (legend label, filter expression, colour, fill alpha, centroid marker).
# Ordered pole-to-pole with the neutral class in the middle, the way a diverging
# legend is read. Rule order does not affect draw order (QGIS renders feature by
# feature unless symbol levels are enabled), so this is purely legend ordering.
# Thresholds are interpolated from the shared constants so the legend labels, the
# filter expressions and the badge count can never drift apart.
_TIMESERIES_CHANGE_RULES = (
    (
        f"Increase (strong) ≥ {_STRONG:g}",
        f'"{_DEVIATION_FIELD}" >= {_STRONG}',
        _CHANGE_INCREASE_STRONG,
        200,
        True,
    ),
    (
        f"Increase ≥ {_SIGNIFICANT:g}",
        f'"{_DEVIATION_FIELD}" >= {_SIGNIFICANT} AND "{_DEVIATION_FIELD}" < {_STRONG}',
        _CHANGE_INCREASE,
        170,
        True,
    ),
    (
        "No significant change",
        f'abs("{_DEVIATION_FIELD}") < {_SIGNIFICANT}',
        _CHANGE_NEUTRAL,
        0,
        False,
    ),
    (
        f"Decrease ≤ -{_SIGNIFICANT:g}",
        f'"{_DEVIATION_FIELD}" <= -{_SIGNIFICANT} AND "{_DEVIATION_FIELD}" > -{_STRONG}',
        _CHANGE_DECREASE,
        170,
        True,
    ),
    (
        f"Decrease (strong) ≤ -{_STRONG:g}",
        f'"{_DEVIATION_FIELD}" <= -{_STRONG}',
        _CHANGE_DECREASE_STRONG,
        200,
        True,
    ),
)

_RULES_BY_TYPE: dict[str, tuple] = {
    "timeseries": _TIMESERIES_CHANGE_RULES,
}


def load_geojson_as_layer(
    geojson: dict[str, Any],
    layer_name: str,
    analysis_type: str,
) -> QgsVectorLayer:
    """Materialise a GeoJSON FeatureCollection as an in-memory QgsVectorLayer.

    Writes the GeoJSON to a temp file so the OGR driver can validate and parse
    it; the file stays under the system temp dir (cleaned up by the OS).
    """
    geojson, dropped = result_stats.strip_heavy_properties(geojson, analysis_type)
    if dropped:
        QgsMessageLog.logMessage(
            f"dropped {dropped} chart properties from the {analysis_type} result "
            "before loading (not renderable in QGIS; still available from the API)",
            LOG_TAG,
            Qgis.MessageLevel.Info,
        )

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
    """Apply the richest renderer the result's attributes support.

    Detection types that carry a signed magnitude (currently timeseries) get a
    diverging rule-based renderer; everything else keeps the flat per-type symbol.

    Deliberately fail-open: the caller aborts the whole layer load on an
    exception, and "the result never reaches the map" is a far worse outcome than
    "the result is drawn in one colour", so a renderer that cannot be built falls
    back to the single symbol instead of propagating.
    """
    renderer = None
    try:
        renderer = _change_renderer(layer, analysis_type)
    except Exception as e:  # noqa: BLE001
        QgsMessageLog.logMessage(
            f"change ramp unavailable for {analysis_type}, using a flat symbol: {e}",
            LOG_TAG,
            Qgis.MessageLevel.Warning,
        )

    if renderer is None:
        renderer = QgsSingleSymbolRenderer(_flat_symbol(layer.geometryType(), analysis_type))
    else:
        QgsMessageLog.logMessage(
            f"applied the {analysis_type} change ramp "
            f"({len(renderer.rootRule().children())} classes)",
            LOG_TAG,
            Qgis.MessageLevel.Info,
        )

    layer.setRenderer(renderer)
    layer.triggerRepaint()


def _flat_symbol(geometry_type: int, analysis_type: str):
    """One colour for the whole layer, keyed by analysis type."""
    style = _STYLE_BY_TYPE.get(analysis_type, _DEFAULT_STYLE)
    base_color = QColor(style["color"])
    fill_color = QColor(base_color)
    fill_color.setAlpha(int(style.get("fill_alpha", 90)))

    # 0 = Point, 1 = Line, 2 = Polygon (QgsWkbTypes.GeometryType enum values)
    if geometry_type == 0:
        return QgsMarkerSymbol.createSimple(
            {
                "name": "circle",
                "color": base_color.name(),
                "size": str(style.get("point_size", 4)),
                "outline_color": "white",
                "outline_width": "0.4",
            }
        )

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
    return symbol


def _change_renderer(layer: QgsVectorLayer, analysis_type: str):
    """Build the diverging renderer, or None when this result cannot use one."""
    rules = _RULES_BY_TYPE.get(analysis_type)
    if not rules:
        return None
    if layer.geometryType() != 2:  # polygons only — the ramp fills cells
        return None
    if layer.fields().lookupField(_DEVIATION_FIELD) < 0:
        # Older or changed result schema: nothing to classify on.
        return None

    root = QgsRuleBasedRenderer.Rule(None)
    for label, expression, color, fill_alpha, with_marker in rules:
        symbol = _change_symbol(color, fill_alpha, with_marker)
        # Positional args: the keyword names for the scale bounds differ between
        # QGIS versions, the positions do not.
        root.appendChild(QgsRuleBasedRenderer.Rule(symbol, 0, 0, expression, label))

    # Catch-all so a NULL or non-numeric deviation is still drawn rather than
    # silently vanishing from the map (in QGIS expressions NULL fails every
    # comparison above).
    fallback = QgsRuleBasedRenderer.Rule(
        _flat_symbol(layer.geometryType(), analysis_type), 0, 0, "", "Unclassified"
    )
    fallback.setIsElse(True)
    root.appendChild(fallback)

    return QgsRuleBasedRenderer(root)


def _change_symbol(color: str, fill_alpha: int, with_marker: bool) -> QgsFillSymbol:
    """Fill for one class of the diverging ramp."""
    base_color = QColor(color)

    if fill_alpha <= 0:
        # The neutral class: outline only, and faint, so it reads as background.
        symbol = QgsFillSymbol.createSimple(
            {"style": "no", "outline_color": base_color.name(), "outline_width": "0.1"}
        )
        hairline = QColor(base_color)
        hairline.setAlpha(70)
        symbol.symbolLayer(0).setStrokeColor(hairline)
        return symbol

    fill_color = QColor(base_color)
    fill_color.setAlpha(int(fill_alpha))
    symbol = QgsFillSymbol.createSimple(
        {
            "color": fill_color.name(QColor.NameFormat.HexArgb),
            "color_named": fill_color.name(),
            # White hairline rather than a darker shade of the fill: the backdrop
            # is arbitrary imagery, so the separator has to hold against both a
            # bright and a dark basemap.
            "outline_color": "#ffffff",
            "outline_width": "0.2",
        }
    )
    symbol.setColor(fill_color)

    if with_marker:
        symbol.appendSymbolLayer(_centroid_marker(base_color))
    return symbol


def _centroid_marker(color: QColor) -> QgsCentroidFillSymbolLayer:
    """A constant-size dot per cell so findings stay visible when zoomed out.

    A timeseries cell is roughly 50 m across, so at AOI-wide zoom it covers a
    couple of pixels — a handful of changed cells is unfindable however saturated
    the fill is. This marker keeps the same on-screen size at every scale, and
    zooming in reveals the real cell footprint underneath it.
    """
    marker = QgsMarkerSymbol.createSimple(
        {
            "name": "circle",
            "color": color.name(),
            "outline_color": "#ffffff",
            "outline_width": "0.3",
            "size": "2.6",
        }
    )
    layer = QgsCentroidFillSymbolLayer()
    layer.setSubSymbol(marker)
    return layer


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
    "type_color",
    "load_geojson_as_layer",
    "load_aoi_as_layer",
    "add_to_project",
    "add_aoi_to_project",
    "apply_style",
    "build_layer_name",
    "build_aoi_layer_name",
]
