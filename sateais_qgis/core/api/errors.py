"""SateAIs API exception hierarchy.

Status-code based classes; the API's specific error code is preserved in
``APIError.code`` for finer-grained UX messages.
"""

from __future__ import annotations


class SateAIsError(Exception):
    """Base class for all SateAIs SDK exceptions."""


class APIError(SateAIsError):
    """Raised when the SateAIs API returns an error response."""

    def __init__(self, status_code: int, code: str | None, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        suffix = f" [{code}]" if code else ""
        super().__init__(f"HTTP {status_code}{suffix}: {message}")


class AuthenticationError(APIError):
    """API key is missing, malformed, or invalid (HTTP 401)."""


class PermissionDeniedError(APIError):
    """API key is valid but lacks permission for the requested resource (HTTP 403)."""


class ValidationError(APIError):
    """Request body or parameters failed validation (HTTP 400)."""


class InsufficientCreditsError(APIError):
    """Account credit balance is exhausted (HTTP 402)."""


class NotFoundError(APIError):
    """Resource not found or no longer available (HTTP 404 / 410).

    The exact reason is in ``APIError.code`` (e.g. ``SCENE_NOT_FOUND``,
    ``INSUFFICIENT_SCENES``, ``POLYGON_NOT_FOUND``, ``GONE``).
    """


class ConflictError(APIError):
    """Resource is not in a state that allows the operation (HTTP 409)."""


class PayloadTooLargeError(APIError):
    """Uploaded payload exceeds the server-side limit (HTTP 413)."""


class RateLimitError(APIError):
    """Too many concurrent or rapid requests (HTTP 429)."""


class ServerError(APIError):
    """Generic 5xx error from the server (500 / 502 / 504)."""


class JobFailedError(SateAIsError):
    """A job ended in the failed state while waiting."""

    def __init__(self, job) -> None:  # type: ignore[no-untyped-def]
        self.job = job
        msg = f"Job {job.job_id} failed"
        if job.error_code:
            msg += f" [{job.error_code}]"
        if job.error_message:
            msg += f": {job.error_message}"
        super().__init__(msg)


class JobTimeoutError(SateAIsError):
    """A job did not complete within the wait timeout."""


class CredentialsNotFoundError(SateAIsError):
    """No API key could be resolved from any source."""


class InvalidAnalysisRequestError(SateAIsError):
    """Required parameters for a AnalysisRequest are missing or incompatible."""


__all__ = [
    "SateAIsError",
    "APIError",
    "AuthenticationError",
    "PermissionDeniedError",
    "ValidationError",
    "InsufficientCreditsError",
    "NotFoundError",
    "ConflictError",
    "PayloadTooLargeError",
    "RateLimitError",
    "ServerError",
    "JobFailedError",
    "JobTimeoutError",
    "CredentialsNotFoundError",
    "InvalidAnalysisRequestError",
]
