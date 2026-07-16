"""QThread worker that submits a detection job off the UI thread."""

from __future__ import annotations

import traceback
from typing import Any

from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtCore import QThread, pyqtSignal

LOG_TAG = "SateAIs"

# Error codes emitted via finished_signal. The UI layer maps these to messages.
ERROR_AUTH_NOT_CONFIGURED = "AUTH_NOT_CONFIGURED"
ERROR_AUTH_FAILED = "AUTH_FAILED"
ERROR_PERMISSION_DENIED = "PERMISSION_DENIED"
ERROR_INSUFFICIENT_CREDITS = "INSUFFICIENT_CREDITS"
ERROR_INVALID_INPUT = "INVALID_INPUT"
ERROR_VALIDATION_FAILED = "VALIDATION_FAILED"
ERROR_NOT_FOUND = "NOT_FOUND"
ERROR_CONFLICT = "CONFLICT"
ERROR_PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
ERROR_RATE_LIMITED = "RATE_LIMITED"
ERROR_SERVER_ERROR = "SERVER_ERROR"
ERROR_NETWORK_ERROR = "NETWORK_ERROR"


class SubmitAnalysisWorker(QThread):
    """Submit a detection job in the background and emit the resulting job id.

    Emits:
        finished_signal(success: bool, payload: str):
            On success ``payload`` is the job id.
            On failure ``payload`` is one of the ``ERROR_*`` codes above.
    """

    finished_signal = pyqtSignal(bool, str)

    def __init__(
        self,
        analysis_type: str,
        kwargs: dict[str, Any],
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self._analysis_type = analysis_type
        self._kwargs = kwargs

    def run(self) -> None:
        from ..core.api.errors import (
            APIError,
            AuthenticationError,
            ConflictError,
            InsufficientCreditsError,
            InvalidAnalysisRequestError,
            NotFoundError,
            PayloadTooLargeError,
            PermissionDeniedError,
            RateLimitError,
            ServerError,
            ValidationError,
        )
        from ..core.client_factory import AuthNotConfiguredError, build_client

        self._log(f"submit {self._analysis_type} kwargs={self._mask_kwargs()}", Qgis.Info)

        try:
            client = build_client()
        except AuthNotConfiguredError:
            self._log("no API key configured", Qgis.Warning)
            self.finished_signal.emit(False, ERROR_AUTH_NOT_CONFIGURED)
            return

        try:
            method = getattr(client.analyze, self._analysis_type)
            job = method(**self._kwargs)
            self._log(f"submitted job_id={job.job_id}", Qgis.Success)
            self.finished_signal.emit(True, job.job_id)
        except InvalidAnalysisRequestError as e:
            self._log(f"client-side validation failed: {e}", Qgis.Warning)
            self.finished_signal.emit(False, ERROR_INVALID_INPUT)
        except AuthenticationError as e:
            self._log_api_error("authentication failed", e)
            self.finished_signal.emit(False, ERROR_AUTH_FAILED)
        except PermissionDeniedError as e:
            self._log_api_error("permission denied", e)
            self.finished_signal.emit(False, ERROR_PERMISSION_DENIED)
        except InsufficientCreditsError as e:
            self._log_api_error("insufficient credits", e)
            self.finished_signal.emit(False, ERROR_INSUFFICIENT_CREDITS)
        except ValidationError as e:
            self._log_api_error("server validation failed", e)
            self.finished_signal.emit(False, ERROR_VALIDATION_FAILED)
        except NotFoundError as e:
            self._log_api_error("not found", e)
            self.finished_signal.emit(False, ERROR_NOT_FOUND)
        except ConflictError as e:
            self._log_api_error("conflict", e)
            self.finished_signal.emit(False, ERROR_CONFLICT)
        except PayloadTooLargeError as e:
            self._log_api_error("payload too large", e)
            self.finished_signal.emit(False, ERROR_PAYLOAD_TOO_LARGE)
        except RateLimitError as e:
            self._log_api_error("rate limit exceeded", e)
            self.finished_signal.emit(False, ERROR_RATE_LIMITED)
        except ServerError as e:
            self._log_api_error("server error", e)
            self.finished_signal.emit(False, ERROR_SERVER_ERROR)
        except APIError as e:
            self._log_api_error("API error", e)
            self.finished_signal.emit(False, ERROR_SERVER_ERROR)
        except Exception as e:  # noqa: BLE001
            self._log(f"unexpected error: {e}\n{traceback.format_exc()}", Qgis.Critical)
            self.finished_signal.emit(False, ERROR_NETWORK_ERROR)
        finally:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _log(message: str, level: int = Qgis.Info) -> None:
        QgsMessageLog.logMessage(message, LOG_TAG, level)

    def _log_api_error(self, label: str, exc: Any) -> None:
        status = getattr(exc, "status_code", "?")
        code = getattr(exc, "code", None) or "-"
        message = getattr(exc, "message", str(exc))
        self._log(f"{label} [HTTP {status} / {code}]: {message}", Qgis.Warning)

    def _mask_kwargs(self) -> dict[str, Any]:
        """Build a log-safe copy of kwargs.

        Polygon WKT is summarised by length only (a malformed multi-megabyte
        WKT could otherwise dominate the QGIS log). All other long strings
        get truncated.
        """
        masked: dict[str, Any] = {}
        for key, value in self._kwargs.items():
            if key == "polygon" and isinstance(value, str):
                masked[key] = f"<wkt len={len(value)}>"
            elif isinstance(value, str) and len(value) > 80:
                masked[key] = value[:60] + f"…(+{len(value) - 60} chars)"
            else:
                masked[key] = value
        return masked
