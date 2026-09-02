"""QThread worker that fetches a pre-run estimate off the UI thread.

Same shape as ``submit_task.SubmitAnalysisWorker`` (and shares its error
codes). The retry-once policy and the "drop stale responses" sequencing live
in the panel, mirroring the MCP widget — the worker stays a single attempt.
"""

from __future__ import annotations

import contextlib
import traceback
from typing import Any

from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtCore import QThread, pyqtSignal

from .submit_task import (
    ERROR_AUTH_FAILED,
    ERROR_AUTH_NOT_CONFIGURED,
    ERROR_INVALID_INPUT,
    ERROR_NETWORK_ERROR,
    ERROR_NOT_FOUND,
    ERROR_PAYLOAD_TOO_LARGE,
    ERROR_PERMISSION_DENIED,
    ERROR_RATE_LIMITED,
    ERROR_SERVER_ERROR,
    ERROR_VALIDATION_FAILED,
)

LOG_TAG = "SateAIs"


class PreviewWorker(QThread):
    """Fetch coverage and credit estimate for a would-be job.

    Emits:
        finished_signal(success: bool, payload: object):
            On success ``payload`` is a ``Preview``.
            On failure ``payload`` is one of the ``ERROR_*`` codes (str).
    """

    finished_signal = pyqtSignal(bool, object)

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
            InvalidAnalysisRequestError,
            NotFoundError,
            PayloadTooLargeError,
            PermissionDeniedError,
            RateLimitError,
            ServerError,
            ValidationError,
        )
        from ..core.client_factory import AuthNotConfiguredError, build_client

        try:
            client = build_client()
        except AuthNotConfiguredError:
            self.finished_signal.emit(False, ERROR_AUTH_NOT_CONFIGURED)
            return

        try:
            preview = client.analyze.preview(self._analysis_type, **self._kwargs)
            self.finished_signal.emit(True, preview)
        except InvalidAnalysisRequestError:
            self.finished_signal.emit(False, ERROR_INVALID_INPUT)
        except AuthenticationError as e:
            self._log_api_error("preview auth failed", e)
            self.finished_signal.emit(False, ERROR_AUTH_FAILED)
        except ValidationError as e:
            self._log_api_error("preview validation failed", e)
            self.finished_signal.emit(False, ERROR_VALIDATION_FAILED)
        except PermissionDeniedError as e:
            self._log_api_error("preview permission denied", e)
            self.finished_signal.emit(False, ERROR_PERMISSION_DENIED)
        except NotFoundError as e:
            self._log_api_error("preview not found", e)
            self.finished_signal.emit(False, ERROR_NOT_FOUND)
        except PayloadTooLargeError as e:
            # 巨大なポリゴンで起きる。ここを SERVER_ERROR に丸めると、
            # 利用者は範囲を狭めればよいことに気付けない
            self._log_api_error("preview payload too large", e)
            self.finished_signal.emit(False, ERROR_PAYLOAD_TOO_LARGE)
        except RateLimitError as e:
            self._log_api_error("preview rate limited", e)
            self.finished_signal.emit(False, ERROR_RATE_LIMITED)
        except ServerError as e:
            self._log_api_error("preview server error", e)
            self.finished_signal.emit(False, ERROR_SERVER_ERROR)
        except APIError as e:
            self._log_api_error("preview API error", e)
            self.finished_signal.emit(False, ERROR_SERVER_ERROR)
        except Exception as e:  # noqa: BLE001
            QgsMessageLog.logMessage(
                f"preview unexpected error: {e}\n{traceback.format_exc()}",
                LOG_TAG,
                Qgis.MessageLevel.Warning,
            )
            self.finished_signal.emit(False, ERROR_NETWORK_ERROR)
        finally:
            with contextlib.suppress(Exception):
                client.close()

    @staticmethod
    def _log_api_error(label: str, exc: Any) -> None:
        status = getattr(exc, "status_code", "?")
        code = getattr(exc, "code", None) or "-"
        message = getattr(exc, "message", str(exc))
        QgsMessageLog.logMessage(
            f"{label} [HTTP {status} / {code}]: {message}", LOG_TAG, Qgis.MessageLevel.Warning
        )


__all__ = ["PreviewWorker"]
