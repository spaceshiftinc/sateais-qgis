"""SateAIs API client for the QGIS plugin (zero third-party dependencies)."""

from .client import Analyze, Client, Jobs
from .errors import (
    APIError,
    AuthenticationError,
    ConflictError,
    CredentialsNotFoundError,
    InsufficientCreditsError,
    InvalidAnalysisRequestError,
    JobFailedError,
    JobTimeoutError,
    NotFoundError,
    PayloadTooLargeError,
    PermissionDeniedError,
    RateLimitError,
    SateAIsError,
    ServerError,
    ValidationError,
)
from .http import DEFAULT_API_BASE_URL, ApiClient, UrllibApiClient
from .types import AnalysisRequest, AnalysisType, Job, JobStatus

__all__ = [
    "Client",
    "Analyze",
    "Jobs",
    "ApiClient",
    "UrllibApiClient",
    "DEFAULT_API_BASE_URL",
    "AnalysisRequest",
    "AnalysisType",
    "Job",
    "JobStatus",
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
