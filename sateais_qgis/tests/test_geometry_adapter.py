"""Unit tests for core.geometry_adapter.

These require PyQGIS and are skipped automatically in environments where
``qgis.core`` cannot be imported.
"""

from __future__ import annotations

import pytest

qgis_available = True
try:
    from qgis.core import QgsCoordinateReferenceSystem, QgsGeometry
except ImportError:
    qgis_available = False

pytestmark = pytest.mark.skipif(
    not qgis_available, reason="QGIS (PyQGIS) is not available in this environment"
)

if qgis_available:
    from sateais_qgis.core.geometry_adapter import (
        polygon_area_km2,
        qgs_geometry_to_wkt_4326,
        validate_wkt_polygon,
    )


class TestQgsGeometryToWkt4326:
    def test_passthrough_when_already_4326(self):
        wkt = "POLYGON((139.7 35.6, 139.8 35.6, 139.8 35.7, 139.7 35.7, 139.7 35.6))"
        geometry = QgsGeometry.fromWkt(wkt)
        source_crs = QgsCoordinateReferenceSystem("EPSG:4326")

        result = qgs_geometry_to_wkt_4326(geometry, source_crs)

        assert "POLYGON" in result.upper()
        assert "139.7" in result
        assert "35.6" in result

    def test_transforms_from_3857(self):
        # A small polygon near Tokyo Station in Web Mercator coordinates.
        wkt_3857 = (
            "POLYGON((15554253 4255480, 15554500 4255480, "
            "15554500 4255700, 15554253 4255700, 15554253 4255480))"
        )
        geometry = QgsGeometry.fromWkt(wkt_3857)
        source_crs = QgsCoordinateReferenceSystem("EPSG:3857")

        result = qgs_geometry_to_wkt_4326(geometry, source_crs)

        assert "139" in result
        assert "35" in result

    def test_rejects_empty_geometry(self):
        with pytest.raises(ValueError, match="empty"):
            qgs_geometry_to_wkt_4326(QgsGeometry(), QgsCoordinateReferenceSystem("EPSG:4326"))

    def test_rejects_point_geometry(self):
        geometry = QgsGeometry.fromWkt("POINT(139.7 35.6)")
        with pytest.raises(ValueError, match="polygon"):
            qgs_geometry_to_wkt_4326(geometry, QgsCoordinateReferenceSystem("EPSG:4326"))


class TestPolygonAreaKm2:
    def test_calculates_tokyo_bay_area(self):
        # ~0.1 deg x 0.1 deg around Tokyo Bay is roughly 11 km x 9 km ~= 100 km².
        wkt = "POLYGON((139.7 35.6, 139.8 35.6, 139.8 35.7, 139.7 35.7, 139.7 35.6))"
        geometry = QgsGeometry.fromWkt(wkt)
        source_crs = QgsCoordinateReferenceSystem("EPSG:4326")

        area = polygon_area_km2(geometry, source_crs)
        assert 80 < area < 120

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            polygon_area_km2(QgsGeometry(), QgsCoordinateReferenceSystem("EPSG:4326"))


class TestValidateWktPolygon:
    def test_valid_polygon(self):
        validate_wkt_polygon(
            "POLYGON((139.7 35.6, 139.8 35.6, 139.8 35.7, 139.7 35.7, 139.7 35.6))"
        )

    def test_valid_multipolygon(self):
        validate_wkt_polygon(
            "MULTIPOLYGON(((139.7 35.6, 139.8 35.6, 139.8 35.7, 139.7 35.7, 139.7 35.6)))"
        )

    def test_empty_string(self):
        with pytest.raises(ValueError, match="empty"):
            validate_wkt_polygon("")

    def test_point_wkt_rejected(self):
        with pytest.raises(ValueError, match="polygon"):
            validate_wkt_polygon("POINT(139.7 35.6)")

    def test_invalid_wkt(self):
        with pytest.raises(ValueError):
            validate_wkt_polygon("NOT_VALID_WKT")
