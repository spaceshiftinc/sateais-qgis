"""Unit tests for core.result_stats (pure Python — no PyQGIS, so these run in CI)."""

from __future__ import annotations

import copy

from sateais_qgis.core import result_stats


def _feature(properties):
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
        "properties": properties,
    }


def _collection(*properties):
    return {"type": "FeatureCollection", "features": [_feature(p) for p in properties]}


class TestThresholds:
    def test_significant_below_strong(self):
        # The rule expressions and the badge count are both derived from these,
        # so an inverted pair would silently produce an empty middle class.
        assert 0 < result_stats.SIGNIFICANT_DEVIATION < result_stats.STRONG_DEVIATION


class TestCountDetections:
    def test_non_timeseries_counts_features(self):
        geojson = _collection({"idx": 1}, {"idx": 2}, {"idx": 3})
        assert result_stats.count_detections(geojson, "ship") == 3
        assert result_stats.count_detections(geojson, "newbuilding") == 3

    def test_timeseries_counts_only_significant_cells(self):
        # Values observed on a real job: two strong changes, one moderate, and
        # noise cells that must not be counted.
        geojson = _collection(
            {"deviation": 1.1421},
            {"deviation": -0.7641},
            {"deviation": 0.0},
            {"deviation": 0.04},
            {"deviation": -0.04},
            {"deviation": 0.06},
        )
        assert result_stats.count_detections(geojson, "timeseries") == 3

    def test_timeseries_boundary_is_inclusive(self):
        geojson = _collection({"deviation": result_stats.SIGNIFICANT_DEVIATION})
        assert result_stats.count_detections(geojson, "timeseries") == 1

    def test_timeseries_without_deviation_falls_back_to_feature_count(self):
        # An unknown or changed schema must not read as "No detections".
        geojson = _collection({"i_h": 1}, {"i_h": 2})
        assert result_stats.count_detections(geojson, "timeseries") == 2

    def test_timeseries_ignores_non_numeric_deviation(self):
        geojson = _collection({"deviation": "1.5"}, {"deviation": True}, {"deviation": 0.9})
        assert result_stats.count_detections(geojson, "timeseries") == 1

    def test_malformed_payloads_count_zero(self):
        assert result_stats.count_detections(None, "ship") == 0
        assert result_stats.count_detections({}, "ship") == 0
        assert result_stats.count_detections({"features": "nope"}, "ship") == 0
        assert result_stats.count_detections({"features": []}, "timeseries") == 0


class TestStripHeavyProperties:
    def test_timeseries_drops_charts_and_keeps_the_rest(self):
        geojson = _collection(
            {
                "deviation": 1.14,
                "changePointDates": ["2026-06-25"],
                "fill": "#FF0000",
                "upper_chart": {"data_series": [1, 2, 3]},
                "lower_chart": {"main_series": {}},
            }
        )
        slimmed, removed = result_stats.strip_heavy_properties(geojson, "timeseries")

        assert removed == 2
        properties = slimmed["features"][0]["properties"]
        assert "upper_chart" not in properties
        assert "lower_chart" not in properties
        assert properties["deviation"] == 1.14
        assert properties["changePointDates"] == ["2026-06-25"]
        assert properties["fill"] == "#FF0000"

    def test_input_is_not_mutated(self):
        geojson = _collection({"deviation": 0.1, "upper_chart": {"a": 1}})
        before = copy.deepcopy(geojson)

        result_stats.strip_heavy_properties(geojson, "timeseries")

        # The worker keeps this same object; slimming is for the QGIS load only.
        assert geojson == before

    def test_other_types_are_returned_untouched(self):
        geojson = _collection({"idx": 1, "upper_chart": {"a": 1}})
        slimmed, removed = result_stats.strip_heavy_properties(geojson, "ship")

        assert removed == 0
        assert slimmed is geojson

    def test_timeseries_without_charts_is_returned_untouched(self):
        geojson = _collection({"deviation": 0.1})
        slimmed, removed = result_stats.strip_heavy_properties(geojson, "timeseries")

        assert removed == 0
        assert slimmed is geojson

    def test_malformed_features_survive(self):
        geojson = {
            "type": "FeatureCollection",
            "features": [
                "not a feature",
                {"type": "Feature"},
                {"type": "Feature", "properties": None},
                _feature({"deviation": 0.9, "upper_chart": {}}),
            ],
        }
        slimmed, removed = result_stats.strip_heavy_properties(geojson, "timeseries")

        assert removed == 1
        assert slimmed["features"][0] == "not a feature"
        assert slimmed["features"][2]["properties"] is None
        assert "upper_chart" not in slimmed["features"][3]["properties"]

    def test_malformed_payloads_are_returned_untouched(self):
        for payload in (None, {}, {"features": "nope"}):
            slimmed, removed = result_stats.strip_heavy_properties(payload, "timeseries")
            assert slimmed is payload
            assert removed == 0
