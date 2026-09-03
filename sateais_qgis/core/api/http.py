"""HTTP transport for the SateAIs API, using only the Python stdlib."""

from __future__ import annotations

import contextlib
import json
import math
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, NoReturn, Protocol, runtime_checkable

from .errors import (
    APIError,
    AuthenticationError,
    ConflictError,
    InsufficientCreditsError,
    NotFoundError,
    PayloadTooLargeError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    UnsupportedResultFormatError,
    ValidationError,
)
from .types import Job, JobStatus, Preview, preview_from_dict

DEFAULT_API_BASE_URL = "https://api.spcsft.com"
API_VERSION_PATH = "/api/v1"
USER_AGENT = "sateais-qgis-plugin/0.3.0"


class _AuthStrippingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Drop the ``Authorization`` header on cross-origin redirects.

    The result endpoints reply with 302 to an S3 presigned URL. S3 rejects
    requests that present both the URL signature and a Bearer token
    (``InvalidArgument: Only one auth mechanism allowed``). Python's
    urllib keeps Authorization across redirects by default; ``requests``
    strips it. We follow the safer behaviour here.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req is None:
            return None
        original_host = urllib.parse.urlparse(req.full_url).netloc.lower()
        new_host = urllib.parse.urlparse(new_req.full_url).netloc.lower()
        if original_host != new_host:
            for header in ("Authorization", "Cookie"):
                # urllib uses a case-insensitive header dict internally but the
                # public API requires the exact stored key.
                new_req.headers.pop(header, None)
                new_req.unredirected_hdrs.pop(header, None)
        return new_req


# このクライアントは常にこの opener 経由で開く（base URL のスキームは
# __init__ で http/https に限定済み）。
# **install_opener() はしない。** プロセス全体の既定 opener を差し替えると、
# 同じ QGIS で動く他のプラグインの urlopen() まで巻き込む。プロキシや独自
# 認証ハンドラを入れている相手を、後から読み込まれた側が黙って上書きする。
# 安全側の挙動であっても、自分の外の状態を書き換えてよい理由にはならない。
_AUTH_STRIPPING_OPENER = urllib.request.build_opener(_AuthStrippingRedirectHandler())

_STATUS_TO_ERROR: dict[int, type[APIError]] = {
    400: ValidationError,
    401: AuthenticationError,
    402: InsufficientCreditsError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    410: NotFoundError,
    413: PayloadTooLargeError,
    429: RateLimitError,
    500: ServerError,
    502: ServerError,
    503: ServerError,
    504: ServerError,
}


@runtime_checkable
class ApiClient(Protocol):
    """Transport interface for the SateAIs API (swappable for tests)."""

    def submit_analysis(self, request) -> Job: ...  # type: ignore[no-untyped-def]
    def preview_analysis(self, request) -> Preview: ...  # type: ignore[no-untyped-def]
    def get_job(self, job_id: str) -> Job: ...
    def get_job_result(self, job_id: str) -> dict[str, Any]: ...
    def list_jobs(
        self,
        statuses: list[str] | None = None,
        endpoint_ids: list[str] | None = None,
        limit: int | None = None,
    ) -> list[Job]: ...
    def get_me(self) -> dict[str, Any]: ...
    def close(self) -> None: ...


class UrllibApiClient:
    """ApiClient implementation backed by urllib (no third-party deps)."""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_API_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        scheme = urllib.parse.urlparse(base_url).scheme.lower()
        if scheme not in ("http", "https"):
            raise APIError(0, None, f"unsupported base URL scheme: {scheme!r}")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def submit_analysis(self, request) -> Job:  # type: ignore[no-untyped-def]
        # analysis_type values come from a closed Enum but we still escape so
        # the URL composition stays robust if the enum is ever extended with a
        # value that needs encoding.
        path = f"/analyze/{urllib.parse.quote(request.analysis_type.value, safe='')}"
        data = self._request("POST", path, json_body=request.to_body())
        return _job_from_dict(data)

    def preview_analysis(self, request) -> Preview:  # type: ignore[no-untyped-def]
        # ボディはジョブ投入と完全に同一 (docs/API.md の preview 節)。ジョブは
        # 作られずクレジットも消費しないので、入力が変わるたびに呼んでよい
        path = f"/analyze/{urllib.parse.quote(request.analysis_type.value, safe='')}/preview"
        data = self._request("POST", path, json_body=request.to_body())
        if not isinstance(data, dict):
            raise APIError(0, None, f"unexpected preview payload: {type(data).__name__}")
        return preview_from_dict(data)

    def get_job(self, job_id: str) -> Job:
        data = self._request("GET", f"/jobs/{urllib.parse.quote(job_id, safe='')}")
        return _job_from_dict(data)

    def get_job_result(self, job_id: str) -> dict[str, Any]:
        data = self._request(
            "GET",
            f"/jobs/{urllib.parse.quote(job_id, safe='')}/result.geojson",
            require_json=True,
        )
        if not isinstance(data, dict):
            raise APIError(0, None, f"unexpected result payload: {type(data).__name__}")
        return data

    def list_jobs(
        self,
        statuses: list[str] | None = None,
        endpoint_ids: list[str] | None = None,
        limit: int | None = None,
    ) -> list[Job]:
        """GET /jobs — the caller's most recent jobs (server caps at 30)."""
        params: dict[str, str] = {}
        if statuses:
            params["status"] = ",".join(statuses)
        if endpoint_ids:
            params["endpoint_id"] = ",".join(endpoint_ids)
        if limit is not None:
            params["limit"] = str(limit)
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        data = self._request("GET", f"/jobs{query}")
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
            raise APIError(0, None, f"unexpected jobs payload: {type(data).__name__}")
        return [_job_from_dict(item) for item in data["jobs"]]

    def get_me(self) -> dict[str, Any]:
        data = self._request("GET", "/me")
        if not isinstance(data, dict):
            raise APIError(0, None, f"unexpected /me payload: {type(data).__name__}")
        return data

    def close(self) -> None:
        """urllib is stateless; nothing to release."""

    def _request(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
        require_json: bool = False,
    ) -> Any:
        url = self.base_url + API_VERSION_PATH + path
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }

        body: bytes | None = None
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url=url, data=body, headers=headers, method=method)

        try:
            with _AUTH_STRIPPING_OPENER.open(req, timeout=self.timeout) as response:
                # 本文を読む前に形式を確かめる。GeoJSON でない結果は 200 で
                # 数十 MB の別形式が返ることがあり、読んでから捨てるのは無駄
                if require_json:
                    _require_json_body(response.headers.get("Content-Type", ""))
                raw = response.read()
        except urllib.error.HTTPError as e:
            _raise_api_error(e)
        except urllib.error.URLError as e:
            # urllib wraps socket timeouts in URLError, so a bare
            # ``except TimeoutError`` would never fire; inspect the reason.
            reason = getattr(e, "reason", None)
            if isinstance(reason, (socket.timeout, TimeoutError)):
                raise APIError(0, None, f"request timed out after {self.timeout}s") from e
            raise APIError(0, None, f"connection error: {reason}") from e
        except (socket.timeout, TimeoutError) as e:
            # Timeouts raised outside urlopen's wrapping (e.g. during read()).
            raise APIError(0, None, f"request timed out after {self.timeout}s") from e

        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise APIError(0, None, f"invalid JSON response: {e}") from e


def _require_json_body(content_type: str) -> None:
    """Reject a successful response whose body is not JSON.

    ``/result.geojson`` answers 200 with the archive itself for result types
    that are not GeoJSON, so there is no HTTP error to catch — the only signal
    is the media type. Checking it keeps the client free of any list of which
    detection types return what.
    """
    media = content_type.split(";", 1)[0].strip().lower()
    if media and not (media == "application/json" or media.endswith("+json")):
        raise UnsupportedResultFormatError(media)


def _raise_api_error(http_error: urllib.error.HTTPError) -> NoReturn:
    status = http_error.code
    raw_body = b""
    # Best-effort: the body is a bonus for diagnostics, never a requirement.
    with contextlib.suppress(Exception):
        raw_body = http_error.read() or b""

    code: str | None = None
    message: str = http_error.reason or f"HTTP {status}"

    if raw_body:
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = None
            # Surface a body excerpt so QGIS log captures the raw server reply
            # (e.g., when an S3 redirect target replies with XML or HTML).
            try:
                snippet = raw_body[:200].decode("utf-8", errors="replace").strip()
            except Exception:  # noqa: BLE001
                snippet = ""
            if snippet:
                message = f"{message} (body: {snippet})"

        if isinstance(body, dict):
            err = body.get("error")
            if isinstance(err, dict):
                code = err.get("code")
                message = err.get("message", message)
            elif isinstance(err, str):
                code = err
                message = body.get("error_message") or body.get("message") or message
            else:
                code = body.get("error_code")
                message = body.get("error_message") or body.get("message") or message

    cls = _STATUS_TO_ERROR.get(status, APIError)
    raise cls(status, code, message)


def _job_from_dict(data: Any) -> Job:
    if not isinstance(data, dict):
        raise APIError(0, None, f"unexpected job payload: {type(data).__name__}")
    job_id = data.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise APIError(0, None, "response is missing a valid job_id")
    request_params = data.get("request_params")
    coverage = data.get("coverage")
    coverage_polygon = coverage.get("polygon") if isinstance(coverage, dict) else None
    return Job(
        job_id=job_id,
        status=JobStatus.parse(data.get("status")),
        created_at=data.get("created_at"),
        completed_at=data.get("completed_at"),
        result_path=data.get("result_path"),
        error_code=data.get("error_code") or data.get("error"),
        error_message=data.get("error_message"),
        endpoint_id=data.get("endpoint_id"),
        coverage_polygon=coverage_polygon if isinstance(coverage_polygon, str) else None,
        area_sqkm=_opt_number(data.get("area_sqkm")),
        credits_used=_opt_number(data.get("credits_used")),
        request_params=request_params if isinstance(request_params, dict) else None,
    )


def _opt_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


__all__ = [
    "ApiClient",
    "UrllibApiClient",
    "DEFAULT_API_BASE_URL",
]
