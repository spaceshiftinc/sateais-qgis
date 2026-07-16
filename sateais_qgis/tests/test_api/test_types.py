"""Unit tests for core.api.types."""

from __future__ import annotations

import pytest

from sateais_qgis.core.api.errors import InvalidAnalysisRequestError
from sateais_qgis.core.api.types import (
    AnalysisRequest,
    AnalysisType,
    Job,
    JobStatus,
)


class TestJobStatus:
    def test_parse_known_values(self):
        assert JobStatus.parse("pending") == JobStatus.PENDING
        assert JobStatus.parse("completed") == JobStatus.COMPLETED
        assert JobStatus.parse("failed") == JobStatus.FAILED

    def test_parse_unknown_falls_back(self):
        assert JobStatus.parse("xyz") == JobStatus.UNKNOWN
        assert JobStatus.parse(None) == JobStatus.UNKNOWN


class TestJob:
    def test_is_completed_property(self):
        job = Job(job_id="x", status=JobStatus.COMPLETED)
        assert job.is_completed is True
        assert job.is_failed is False
        assert job.is_terminal is True

    def test_is_failed_property(self):
        job = Job(job_id="x", status=JobStatus.FAILED, error_code="E", error_message="m")
        assert job.is_failed is True
        assert job.is_terminal is True

    def test_pending_not_terminal(self):
        job = Job(job_id="x", status=JobStatus.PENDING)
        assert job.is_terminal is False


class TestAnalysisType:
    def test_ship_accepts_scene_or_polygon_date(self):
        assert AnalysisType.SHIP.accepts_scene_or_polygon_date is True
        assert AnalysisType.SHIP.requires_date_range is False

    def test_oilslick_accepts_scene_or_polygon_date(self):
        assert AnalysisType.OILSLICK.accepts_scene_or_polygon_date is True

    def test_newbuilding_requires_date_range(self):
        assert AnalysisType.NEWBUILDING.requires_date_range is True
        assert AnalysisType.NEWBUILDING.accepts_scene_or_polygon_date is False

    def test_timeseries_requires_date_range(self):
        assert AnalysisType.TIMESERIES.requires_date_range is True


class TestAnalysisRequestValidate:
    def test_ship_with_scene_id_ok(self):
        AnalysisRequest(analysis_type=AnalysisType.SHIP, scene_id="S1A_test").validate()

    def test_ship_with_polygon_and_date_ok(self):
        AnalysisRequest(
            analysis_type=AnalysisType.SHIP,
            polygon="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            date="2024-01-01",
        ).validate()

    def test_ship_with_both_rejected(self):
        with pytest.raises(InvalidAnalysisRequestError):
            AnalysisRequest(
                analysis_type=AnalysisType.SHIP,
                scene_id="S1A_test",
                polygon="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
                date="2024-01-01",
            ).validate()

    def test_ship_with_neither_rejected(self):
        with pytest.raises(InvalidAnalysisRequestError):
            AnalysisRequest(analysis_type=AnalysisType.SHIP).validate()

    def test_ship_polygon_without_date_rejected(self):
        # polygon without date counts as "neither scene_id nor polygon+date".
        with pytest.raises(InvalidAnalysisRequestError):
            AnalysisRequest(
                analysis_type=AnalysisType.SHIP,
                polygon="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            ).validate()

    def test_newbuilding_all_required_ok(self):
        AnalysisRequest(
            analysis_type=AnalysisType.NEWBUILDING,
            polygon="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            date_start="2024-01-01",
            date_end="2024-12-01",
        ).validate()

    def test_newbuilding_missing_polygon_rejected(self):
        with pytest.raises(InvalidAnalysisRequestError, match="polygon"):
            AnalysisRequest(
                analysis_type=AnalysisType.NEWBUILDING,
                date_start="2024-01-01",
                date_end="2024-12-01",
            ).validate()

    def test_newbuilding_missing_date_end_rejected(self):
        with pytest.raises(InvalidAnalysisRequestError, match="date_end"):
            AnalysisRequest(
                analysis_type=AnalysisType.NEWBUILDING,
                polygon="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
                date_start="2024-01-01",
            ).validate()


class TestAnalysisRequestToBody:
    def test_excludes_none_fields(self):
        body = AnalysisRequest(analysis_type=AnalysisType.SHIP, scene_id="S1A_test").to_body()
        assert "scene_id" in body
        # None fields are omitted and analysis_type goes into the URL, not the body.
        assert "polygon" not in body
        assert "analysis_type" not in body
        assert body["satellite_id"] == "sentinel-1"

    def test_includes_all_set_fields(self):
        body = AnalysisRequest(
            analysis_type=AnalysisType.NEWBUILDING,
            polygon="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            date_start="2024-01-01",
            date_end="2024-12-01",
            orbit_direction="ascending",
        ).to_body()
        assert body["polygon"].startswith("POLYGON")
        assert body["date_start"] == "2024-01-01"
        assert body["date_end"] == "2024-12-01"
        assert body["orbit_direction"] == "ascending"
        assert body["satellite_id"] == "sentinel-1"
