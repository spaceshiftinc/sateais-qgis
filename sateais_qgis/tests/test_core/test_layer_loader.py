"""Renderer tests for core.layer_loader (needs PyQGIS; skipped where unavailable)."""

from __future__ import annotations

import pytest

pyqgis_available = True
try:
    from qgis.core import (
        QgsRuleBasedRenderer,
        QgsSingleSymbolRenderer,
        QgsVectorLayer,
    )
except ImportError:
    pyqgis_available = False

pytestmark = pytest.mark.skipif(
    not pyqgis_available, reason="PyQGIS not available in this environment"
)

if pyqgis_available:
    from sateais_qgis.core import layer_loader


def _polygon_layer(fields_uri: str = "") -> QgsVectorLayer:
    uri = "Polygon?crs=EPSG:4326"
    if fields_uri:
        uri += f"&{fields_uri}"
    layer = QgsVectorLayer(uri, "test", "memory")
    assert layer.isValid()
    return layer


class TestApplyStyleFallback:
    def test_polygon_without_deviation_gets_a_flat_symbol(self, qgis_app):
        # The guard that matters: a result whose schema changed must still be
        # drawn, just in one colour.
        layer = _polygon_layer()
        layer_loader.apply_style(layer, "timeseries")
        assert isinstance(layer.renderer(), QgsSingleSymbolRenderer)

    def test_other_types_keep_the_flat_symbol(self, qgis_app):
        layer = _polygon_layer("field=deviation:double")
        layer_loader.apply_style(layer, "newbuilding")
        assert isinstance(layer.renderer(), QgsSingleSymbolRenderer)

    def test_point_layer_keeps_the_flat_symbol(self, qgis_app):
        layer = QgsVectorLayer("Point?crs=EPSG:4326&field=deviation:double", "test", "memory")
        assert layer.isValid()
        layer_loader.apply_style(layer, "timeseries")
        assert isinstance(layer.renderer(), QgsSingleSymbolRenderer)


class TestTimeseriesChangeRamp:
    @pytest.fixture
    def layer(self, qgis_app):
        # Yield the layer, not its renderer: the renderer's C++ object is owned
        # by the layer, so returning it alone lets sip delete it mid-test.
        layer = _polygon_layer("field=deviation:double")
        layer_loader.apply_style(layer, "timeseries")
        yield layer

    def test_uses_a_rule_based_renderer(self, layer):
        assert isinstance(layer.renderer(), QgsRuleBasedRenderer)

    def test_has_one_rule_per_class_plus_a_catch_all(self, layer):
        children = layer.renderer().rootRule().children()
        assert len(children) == len(layer_loader._TIMESERIES_CHANGE_RULES) + 1

    def test_only_the_last_rule_is_the_catch_all(self, layer):
        children = layer.renderer().rootRule().children()
        assert [rule.isElse() for rule in children] == [False] * (len(children) - 1) + [True]

    def test_every_classified_rule_has_a_filter_and_a_label(self, layer):
        for rule in layer.renderer().rootRule().children()[:-1]:
            assert rule.filterExpression()
            assert rule.label()

    def test_legend_reads_pole_to_pole_with_the_neutral_class_in_the_middle(self, layer):
        labels = [rule.label() for rule in layer.renderer().rootRule().children()]
        assert labels[2] == "No significant change"
        assert labels[0].startswith("Increase (strong)")
        assert labels[-2].startswith("Decrease (strong)")
        assert labels[-1] == "Unclassified"

    def test_neutral_class_draws_no_fill(self, layer):
        neutral = next(
            rule
            for rule in layer.renderer().rootRule().children()
            if rule.label() == "No significant change"
        )
        # Outline only: 2402 of 2409 cells land here on a real job, and filling
        # them buries the findings.
        assert neutral.symbol().symbolLayerCount() == 1
        assert neutral.symbol().symbolLayer(0).brushStyle() == 0  # Qt.BrushStyle.NoBrush

    def test_change_classes_carry_a_constant_size_marker(self, layer):
        for rule in layer.renderer().rootRule().children()[:-1]:
            if rule.label() == "No significant change":
                continue
            # Fill layer plus the centroid marker that keeps cells findable when
            # zoomed out to the whole AOI.
            assert rule.symbol().symbolLayerCount() == 2
