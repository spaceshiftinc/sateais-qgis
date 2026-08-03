"""Unit tests for core.api.http (urllib.request is mocked)."""

from __future__ import annotations

import io
import json
import socket
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from sateais_qgis.core.api.errors import (
    APIError,
    AuthenticationError,
    ConflictError,
    InsufficientCreditsError,
    NotFoundError,
    PayloadTooLargeError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from sateais_qgis.core.api.http import (
    UrllibApiClient,
    _AuthStrippingRedirectHandler,
    _job_from_dict,
)
from sateais_qgis.core.api.types import (
    AnalysisRequest,
    AnalysisType,
    JobStatus,
)


def _mock_response(body_dict, status: int = 200):
    """Return a mock that behaves like the urlopen context manager."""
    mock = MagicMock()
    mock.read.return_value = json.dumps(body_dict).encode("utf-8")
    mock.__enter__.return_value = mock
    mock.__exit__.return_value = None
    return mock


def _http_error(status: int, body_dict, reason: str = "error"):
    """urllib.error.HTTPError mock"""
    err = urllib.error.HTTPError(
        url="https://api.spcsft.com/x",
        code=status,
        msg=reason,
        hdrs={},  # type: ignore[arg-type]
        fp=io.BytesIO(json.dumps(body_dict).encode("utf-8")),
    )
    return err


class TestUrllibApiClientSubmit:
    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_submit_ship_with_scene_id(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(
            {
                "job_id": "job-1",
                "status": "pending",
                "created_at": "2024-01-01T00:00:00Z",
            }
        )

        client = UrllibApiClient(api_key="sk_test")
        request = AnalysisRequest(analysis_type=AnalysisType.SHIP, scene_id="S1A_test")
        job = client.submit_analysis(request)

        assert job.job_id == "job-1"
        assert job.status == JobStatus.PENDING

        sent_req = mock_urlopen.call_args[0][0]
        assert sent_req.method == "POST"
        assert sent_req.full_url == "https://api.spcsft.com/api/v1/analyze/ship"
        assert sent_req.get_header("Authorization") == "Bearer sk_test"
        assert sent_req.get_header("Content-type") == "application/json"
        body = json.loads(sent_req.data.decode("utf-8"))
        assert body["scene_id"] == "S1A_test"
        assert body["satellite_id"] == "sentinel-1"
        assert "polygon" not in body

    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_submit_newbuilding_polygon_dates(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({"job_id": "job-2", "status": "pending"})

        client = UrllibApiClient(api_key="sk_test")
        request = AnalysisRequest(
            analysis_type=AnalysisType.NEWBUILDING,
            polygon="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            date_start="2024-01-01",
            date_end="2024-12-01",
        )
        client.submit_analysis(request)

        sent_req = mock_urlopen.call_args[0][0]
        assert sent_req.full_url == "https://api.spcsft.com/api/v1/analyze/newbuilding"
        body = json.loads(sent_req.data.decode("utf-8"))
        assert body["date_start"] == "2024-01-01"
        assert body["date_end"] == "2024-12-01"


class TestUrllibApiClientGetJob:
    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_get_job_completed(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(
            {
                "job_id": "job-1",
                "status": "completed",
                "created_at": "2024-01-01T00:00:00Z",
                "completed_at": "2024-01-01T00:05:00Z",
                "result_path": "/api/v1/jobs/job-1/result.geojson",
            }
        )

        client = UrllibApiClient(api_key="sk_test")
        job = client.get_job("job-1")

        assert job.is_completed
        assert job.result_path is not None

        sent_req = mock_urlopen.call_args[0][0]
        assert sent_req.method == "GET"
        assert sent_req.full_url == "https://api.spcsft.com/api/v1/jobs/job-1"

    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_get_job_result_returns_geojson(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(
            {"type": "FeatureCollection", "features": [{"type": "Feature"}]}
        )
        client = UrllibApiClient(api_key="sk_test")
        geojson = client.get_job_result("job-1")
        assert geojson["type"] == "FeatureCollection"


class TestUrllibApiClientErrorMapping:
    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_401_maps_to_authentication_error(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(
            401, {"error": {"code": "UNAUTHORIZED", "message": "Invalid API key"}}
        )
        client = UrllibApiClient(api_key="sk_bad")
        with pytest.raises(AuthenticationError) as exc:
            client.get_job("x")
        assert exc.value.status_code == 401
        assert exc.value.code == "UNAUTHORIZED"
        assert "Invalid" in exc.value.message

    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_402_maps_to_insufficient_credits(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(
            402, {"error": {"code": "INSUFFICIENT_CREDITS", "message": "no money"}}
        )
        client = UrllibApiClient(api_key="sk_test")
        with pytest.raises(InsufficientCreditsError):
            client.get_job("x")

    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_403_maps_to_permission_denied(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(
            403,
            {"error": {"code": "FORBIDDEN", "message": "No permission for ship"}},
        )
        client = UrllibApiClient(api_key="sk_test")
        with pytest.raises(PermissionDeniedError) as exc:
            client.get_job("x")
        assert exc.value.status_code == 403
        assert exc.value.code == "FORBIDDEN"
        # PermissionDeniedError must NOT subclass AuthenticationError
        assert not isinstance(exc.value, AuthenticationError)

    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_404_maps_to_not_found(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(
            404, {"error": {"code": "NOT_FOUND", "message": "Job not found"}}
        )
        client = UrllibApiClient(api_key="sk_test")
        with pytest.raises(NotFoundError):
            client.get_job("nope")

    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_429_maps_to_rate_limit(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(
            429, {"error": {"code": "RATE_LIMIT_EXCEEDED", "message": "slow down"}}
        )
        client = UrllibApiClient(api_key="sk_test")
        with pytest.raises(RateLimitError):
            client.get_job("x")

    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_400_maps_to_validation_error(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(
            400,
            {"error": {"code": "VALIDATION_ERROR", "message": "polygon too large"}},
        )
        client = UrllibApiClient(api_key="sk_test")
        with pytest.raises(ValidationError):
            client.get_job("x")

    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_409_maps_to_conflict(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(
            409,
            {"error": {"code": "POLYGON_NOT_READY", "message": "still processing"}},
        )
        client = UrllibApiClient(api_key="sk_test")
        with pytest.raises(ConflictError):
            client.get_job("x")

    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_410_maps_to_not_found(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(
            410, {"error": {"code": "GONE", "message": "expired"}}
        )
        client = UrllibApiClient(api_key="sk_test")
        with pytest.raises(NotFoundError) as exc:
            client.get_job("x")
        assert exc.value.code == "GONE"

    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_413_maps_to_payload_too_large(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(
            413, {"error": {"code": "PAYLOAD_TOO_LARGE", "message": "too big"}}
        )
        client = UrllibApiClient(api_key="sk_test")
        with pytest.raises(PayloadTooLargeError):
            client.get_job("x")

    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_500_maps_to_server_error(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(500, {})
        client = UrllibApiClient(api_key="sk_test")
        with pytest.raises(ServerError) as exc:
            client.get_job("x")
        assert exc.value.status_code == 500

    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_502_and_504_map_to_server_error(self, mock_urlopen):
        for status in (502, 504):
            mock_urlopen.side_effect = _http_error(status, {})
            client = UrllibApiClient(api_key="sk_test")
            with pytest.raises(ServerError):
                client.get_job("x")

    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_unmapped_status_falls_back_to_apierror(self, mock_urlopen):
        # 418 is not in the table; the generic APIError must be raised.
        mock_urlopen.side_effect = _http_error(418, {})
        client = UrllibApiClient(api_key="sk_test")
        with pytest.raises(APIError) as exc:
            client.get_job("x")
        assert type(exc.value) is APIError
        assert exc.value.status_code == 418

    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_url_error_maps_to_connection_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("name resolution failed")
        client = UrllibApiClient(api_key="sk_test")
        with pytest.raises(APIError, match="connection error"):
            client.get_job("x")

    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_socket_timeout_wrapped_in_url_error_maps_to_timeout(self, mock_urlopen):
        # urllib wraps socket timeouts in URLError, so the timeout branch must
        # inspect ``reason`` — a bare ``except TimeoutError`` never fires here.
        mock_urlopen.side_effect = urllib.error.URLError(socket.timeout("timed out"))
        client = UrllibApiClient(api_key="sk_test")
        with pytest.raises(APIError, match="timed out"):
            client.get_job("x")

    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_bare_socket_timeout_maps_to_timeout(self, mock_urlopen):
        # Timeouts raised outside urlopen's URLError wrapping (e.g. during read()).
        mock_urlopen.side_effect = socket.timeout("timed out")
        client = UrllibApiClient(api_key="sk_test")
        with pytest.raises(APIError, match="timed out"):
            client.get_job("x")

    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_legacy_error_format_compat(self, mock_urlopen):
        """Legacy ``{"error_code": ..., "error_message": ...}`` is also supported."""
        mock_urlopen.side_effect = _http_error(
            404, {"error_code": "JOB_NOT_FOUND", "error_message": "not found"}
        )
        client = UrllibApiClient(api_key="sk_test")
        with pytest.raises(NotFoundError) as exc:
            client.get_job("x")
        assert exc.value.code == "JOB_NOT_FOUND"


class TestListJobs:
    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_parses_items_including_endpoint_id(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(
            {
                "jobs": [
                    {"job_id": "a", "status": "completed", "endpoint_id": "ship"},
                    {"job_id": "b", "status": "processing", "endpoint_id": "timeseries"},
                ]
            }
        )
        client = UrllibApiClient(api_key="sk_test")
        jobs = client.list_jobs()
        assert [j.job_id for j in jobs] == ["a", "b"]
        assert jobs[0].endpoint_id == "ship"
        assert jobs[1].status == JobStatus.PROCESSING

    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_builds_filter_query(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({"jobs": []})
        client = UrllibApiClient(api_key="sk_test")
        client.list_jobs(statuses=["pending", "processing"], endpoint_ids=["ship"], limit=5)
        url = mock_urlopen.call_args[0][0].full_url
        assert "/api/v1/jobs?" in url
        assert "status=pending%2Cprocessing" in url
        assert "endpoint_id=ship" in url
        assert "limit=5" in url

    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_no_query_string_without_filters(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({"jobs": []})
        client = UrllibApiClient(api_key="sk_test")
        client.list_jobs()
        url = mock_urlopen.call_args[0][0].full_url
        assert url.endswith("/api/v1/jobs")

    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_rejects_malformed_payload(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({"unexpected": True})
        client = UrllibApiClient(api_key="sk_test")
        with pytest.raises(APIError, match="unexpected jobs payload"):
            client.list_jobs()


class TestJobFromDict:
    def test_minimal_payload(self):
        job = _job_from_dict({"job_id": "x", "status": "pending"})
        assert job.job_id == "x"
        assert job.status == JobStatus.PENDING

    def test_full_payload(self):
        job = _job_from_dict(
            {
                "job_id": "x",
                "status": "completed",
                "created_at": "2024-01-01T00:00:00Z",
                "completed_at": "2024-01-01T00:05:00Z",
                "result_path": "/api/v1/jobs/x/result.geojson",
            }
        )
        assert job.is_completed
        assert job.result_path is not None

    def test_legacy_error_field(self):
        """The legacy 'error' field is read as error_code."""
        job = _job_from_dict({"job_id": "x", "status": "failed", "error": "VALIDATION_ERROR"})
        assert job.error_code == "VALIDATION_ERROR"

    def test_unknown_status_fallback(self):
        job = _job_from_dict({"job_id": "x", "status": "weird"})
        assert job.status == JobStatus.UNKNOWN

    def test_request_params_are_kept(self):
        # Only the job-list endpoint returns these; they are what lets the Jobs
        # tab describe a job submitted from the console / CLI / MCP.
        params = {"polygon": "POLYGON((0 0,1 0,1 1,0 0))", "date_start": "2026-01-03"}
        job = _job_from_dict({"job_id": "x", "status": "completed", "request_params": params})
        assert job.request_params == params

    def test_request_params_default_to_none(self):
        job = _job_from_dict({"job_id": "x", "status": "pending"})
        assert job.request_params is None

    def test_non_dict_request_params_are_dropped(self):
        for value in ("nope", ["a"], 3, True):
            job = _job_from_dict({"job_id": "x", "status": "pending", "request_params": value})
            assert job.request_params is None


class TestGetMe:
    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_returns_user_info(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(
            {
                "user_id": "uuid-1",
                "email": "user@example.com",
                "plan": "pro",
                "credits": {"balance": 1420.0},
            }
        )

        client = UrllibApiClient(api_key="sk_test")
        me = client.get_me()

        assert me["user_id"] == "uuid-1"
        assert me["email"] == "user@example.com"
        assert me["credits"]["balance"] == 1420.0

        sent_req = mock_urlopen.call_args[0][0]
        assert sent_req.method == "GET"
        assert sent_req.full_url == "https://api.spcsft.com/api/v1/me"

    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_invalid_key_raises_auth_error(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(
            401, {"error": {"code": "UNAUTHORIZED", "message": "Invalid API key"}}
        )
        client = UrllibApiClient(api_key="sk_bad")
        with pytest.raises(AuthenticationError):
            client.get_me()


class TestAuthStrippingRedirectHandler:
    """The result endpoint replies with 302 to an S3 presigned URL; S3 rejects
    requests that present both the Authorization header and the URL signature.
    """

    def _redirect(self, original_url: str, new_url: str):
        handler = _AuthStrippingRedirectHandler()
        original_req = urllib.request.Request(
            url=original_url,
            headers={"Authorization": "Bearer sk_test", "User-Agent": "x"},
        )
        # urllib calls redirect_request via the handler chain; the body and
        # response headers are unused for the host check we care about.
        return handler.redirect_request(
            original_req, fp=None, code=302, msg="Found", headers={}, newurl=new_url
        )

    def test_strips_authorization_on_cross_origin(self):
        new_req = self._redirect(
            "https://api.spcsft.com/api/v1/jobs/x/result.geojson",
            "https://example-bucket.s3.amazonaws.com/results/x.geojson?X-Amz-Signature=…",
        )
        assert new_req.get_header("Authorization") is None
        # Other headers are preserved.
        assert new_req.get_header("User-agent") == "x"

    def test_preserves_authorization_on_same_origin(self):
        new_req = self._redirect(
            "https://api.spcsft.com/api/v1/old",
            "https://api.spcsft.com/api/v1/new",
        )
        assert new_req.get_header("Authorization") == "Bearer sk_test"


class TestBaseUrlSchemeValidation:
    def test_rejects_file_scheme(self):
        with pytest.raises(APIError, match="unsupported base URL scheme"):
            UrllibApiClient(api_key="sk_x", base_url="file:///etc/passwd")

    def test_rejects_ftp_scheme(self):
        with pytest.raises(APIError):
            UrllibApiClient(api_key="sk_x", base_url="ftp://example.com")

    def test_accepts_https(self):
        UrllibApiClient(api_key="sk_x", base_url="https://api.spcsft.com")

    def test_accepts_http_for_local_testing(self):
        UrllibApiClient(api_key="sk_x", base_url="http://localhost:8080")


class TestPathParameterEscaping:
    @patch("sateais_qgis.core.api.http._AUTH_STRIPPING_OPENER.open")
    def test_job_id_with_slash_is_escaped(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({"job_id": "x", "status": "pending"})
        client = UrllibApiClient(api_key="sk_test")
        # A malformed job_id must not break out of the /jobs/{id} segment.
        client.get_job("evil/../admin")
        sent_req = mock_urlopen.call_args[0][0]
        assert "/jobs/evil%2F..%2Fadmin" in sent_req.full_url
        assert "../admin" not in sent_req.full_url


class TestJobFromDictRobustness:
    def test_missing_job_id_raises_apierror(self):
        with pytest.raises(APIError, match="missing a valid job_id"):
            _job_from_dict({"status": "pending"})

    def test_non_string_job_id_raises_apierror(self):
        with pytest.raises(APIError):
            _job_from_dict({"job_id": 123, "status": "pending"})

    def test_empty_string_job_id_raises_apierror(self):
        with pytest.raises(APIError):
            _job_from_dict({"job_id": "", "status": "pending"})
