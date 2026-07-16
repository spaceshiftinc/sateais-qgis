"""QgsGeometry ↔ WKT (EPSG:4326) conversion helpers.

The SateAIs API accepts polygons as EPSG:4326 (WGS84) WKT strings, while
QGIS layers can be in any CRS. This module is the boundary that handles
the conversion, area measurement, and WKT validation.
"""

from __future__ import annotations

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsGeometry,
    QgsProject,
    QgsUnitTypes,
)

TARGET_CRS_AUTH_ID = "EPSG:4326"


def qgs_geometry_to_wkt_4326(
    geometry: QgsGeometry,
    source_crs: QgsCoordinateReferenceSystem,
) -> str:
    """Convert a QgsGeometry to a WKT string in EPSG:4326.

    Args:
        geometry: Polygon or MultiPolygon to convert.
        source_crs: CRS the geometry is currently in.

    Returns:
        WKT in EPSG:4326, e.g. ``POLYGON((139.7 35.6, ...))``.

    Raises:
        ValueError: If the geometry is empty or is not a polygon type.
    """
    if geometry is None or geometry.isEmpty():
        raise ValueError("geometry is empty")

    type_str = geometry.asWkt()[:20].upper()
    if not (type_str.startswith("POLYGON") or type_str.startswith("MULTIPOLYGON")):
        raise ValueError(f"expected polygon/multipolygon, got wkbType={geometry.wkbType()}")

    target_crs = QgsCoordinateReferenceSystem(TARGET_CRS_AUTH_ID)
    if source_crs != target_crs:
        transform = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())
        # Clone before transforming so the caller's geometry is not mutated.
        geometry = QgsGeometry(geometry)
        geometry.transform(transform)

    return geometry.asWkt()


def polygon_area_km2(geometry: QgsGeometry, source_crs: QgsCoordinateReferenceSystem) -> float:
    """Return the area of a polygon in square kilometres.

    Uses :class:`QgsDistanceArea` with the WGS84 ellipsoid so the result is
    a true geodetic area, suitable for SateAIs per-detection area limits.

    Raises:
        ValueError: If the geometry is empty or is not a polygon type.
    """
    if geometry is None or geometry.isEmpty():
        raise ValueError("geometry is empty")

    type_str = geometry.asWkt()[:20].upper()
    if not (type_str.startswith("POLYGON") or type_str.startswith("MULTIPOLYGON")):
        raise ValueError("expected polygon/multipolygon for area measurement")

    distance_area = QgsDistanceArea()
    distance_area.setSourceCrs(source_crs, QgsProject.instance().transformContext())
    distance_area.setEllipsoid("WGS84")

    area_m2 = distance_area.measureArea(geometry)
    area_m2 = distance_area.convertAreaMeasurement(area_m2, QgsUnitTypes.AreaSquareMeters)
    return area_m2 / 1_000_000.0


def validate_wkt_polygon(wkt: str) -> None:
    """Validate that a string is a parseable polygon WKT.

    Raises:
        ValueError: If parsing fails or the geometry is not a polygon type.
    """
    if not wkt or not wkt.strip():
        raise ValueError("WKT is empty")

    geometry = QgsGeometry.fromWkt(wkt)
    if geometry.isNull() or geometry.isEmpty():
        raise ValueError(f"failed to parse WKT: {wkt[:50]}...")

    type_str = wkt.strip()[:20].upper()
    if not (type_str.startswith("POLYGON") or type_str.startswith("MULTIPOLYGON")):
        raise ValueError(f"expected polygon/multipolygon WKT: {wkt[:50]}...")
