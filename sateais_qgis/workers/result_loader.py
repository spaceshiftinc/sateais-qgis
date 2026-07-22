"""QThread worker that fetches a completed job's result GeoJSON off the UI thread.

Load on Map click used to hit `client.jobs.result(job_id)` synchronously on the
UI thread, blocking QGIS for the duration of the S3 302 redirect + JSON parse
(up to 30 seconds with our urllib timeout). This worker moves that fetch into a
background thread so the UI stays responsive and progress indicators can tick.

Emits ``finished_signal(ok, geojson_or_none, error_code)``:
    - ``ok=True``: ``geojson`` is a dict, ``error_code`` is an empty string.
    - ``ok=False``: ``geojson`` is ``None``, ``error_code`` is one of the
      ``ERROR_*`` constants defined below.

The GeoJSON is emitted as ``object`` so Qt signal marshalling keeps the dict
intact across the thread boundary.
"""

from __future__ import annotations

import contextlib
import traceback
from typing import Any

from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtCore import QThread, pyqtSignal

LOG_TAG = "SateAIs"

# Error codes emitted via finished_signal. Kept in sync with submit_task's set
# where they overlap so the UI can reuse ERROR_MESSAGES entries directly.
ERROR_AUTH_NOT_CONFIGURED = "AUTH_NOT_CONFIGURED"
ERROR_AUTH_FAILED = "AUTH_FAILED"
ERROR_PERMISSION_DENIED = "PERMISSION_DENIED"
ERROR_NOT_FOUND = "NOT_FOUND"
ERROR_GONE = "GONE"
ERROR_JOB_NOT_COMPLETED = "JOB_NOT_COMPLETED"
ERROR_SERVER_ERROR = "SERVER_ERROR"
ERROR_NETWORK_ERROR = "NETWORK_ERROR"


class ResultLoaderWorker(QThread):
    """Fetch ``client.jobs.result(job_id)`` in the background."""

    # (ok, geojson_or_none, error_code)
    finished_signal = pyqtSignal(bool, object, str)

    def __init__(self, job_id: str, parent: Any = None) -> None:
        super().__init__(parent)
        self._job_id = job_id

    def run(self) -> None:
        # Outer guard: run() must ALWAYS emit exactly one terminal signal. If it
        # returned without emitting (e.g. build_client raised something other
        # than AuthNotConfiguredError, or an import failed), the JobCard would
        # spin forever and the worker would leak. Any escaped exception here is
        # therefore turned into a terminal error signal.
        try:
            self._run()
        except Exception as e:  # noqa: BLE001
            self._log(
                f"worker crashed before emitting: {e}\n{traceback.format_exc()}",
                Qgis.MessageLevel.Critical,
            )
            self.finished_signal.emit(False, None, ERROR_SERVER_ERROR)

    def _run(self) -> None:
        # The API exposes a status-code-based exception hierarchy; there is no
        # dedicated GoneError / JobNotCompletedError class. 410 (result expired)
        # arrives as NotFoundError with ``code == "GONE"``; 409 (job not in a
        # completable state) arrives as ConflictError.
        from ..core.api.errors import (
            APIError,
            AuthenticationError,
            ConflictError,
            NotFoundError,
            PermissionDeniedError,
            ServerError,
        )
        from ..core.client_factory import AuthNotConfiguredError, build_client

        self._log(f"fetching result job_id={self._job_id}", Qgis.MessageLevel.Info)

        try:
            client = build_client()
        except AuthNotConfiguredError:
            self._log("no API key configured", Qgis.MessageLevel.Warning)
            self.finished_signal.emit(False, None, ERROR_AUTH_NOT_CONFIGURED)
            return

        try:
            geojson = client.jobs.result(self._job_id)
            self._log(f"fetched result job_id={self._job_id}", Qgis.MessageLevel.Success)
            self.finished_signal.emit(True, geojson, "")
        except AuthenticationError as e:
            self._log_api_error("authentication failed", e)
            self.finished_signal.emit(False, None, ERROR_AUTH_FAILED)
        except PermissionDeniedError as e:
            self._log_api_error("permission denied", e)
            self.finished_signal.emit(False, None, ERROR_PERMISSION_DENIED)
        except ConflictError as e:
            self._log_api_error("job not completed", e)
            self.finished_signal.emit(False, None, ERROR_JOB_NOT_COMPLETED)
        except NotFoundError as e:
            # 410 (retention expired) is a NotFoundError tagged code == "GONE".
            if getattr(e, "code", None) == "GONE":
                self._log_api_error("result gone (retention expired)", e)
                self.finished_signal.emit(False, None, ERROR_GONE)
            else:
                self._log_api_error("not found", e)
                self.finished_signal.emit(False, None, ERROR_NOT_FOUND)
        except ServerError as e:
            self._log_api_error("server error", e)
            self.finished_signal.emit(False, None, ERROR_SERVER_ERROR)
        except APIError as e:
            # Base class: connection errors (status 0), validation, timeouts, etc.
            self._log_api_error("API error", e)
            self.finished_signal.emit(False, None, ERROR_SERVER_ERROR)
        except Exception as e:  # noqa: BLE001
            self._log(
                f"unexpected error: {e}\n{traceback.format_exc()}", Qgis.MessageLevel.Critical
            )
            self.finished_signal.emit(False, None, ERROR_NETWORK_ERROR)
        finally:
            with contextlib.suppress(Exception):
                client.close()

    @staticmethod
    def _log(message: str, level: int = Qgis.MessageLevel.Info) -> None:
        QgsMessageLog.logMessage(message, LOG_TAG, level)

    def _log_api_error(self, label: str, exc: Any) -> None:
        status = getattr(exc, "status_code", "?")
        code = getattr(exc, "code", None) or "-"
        message = getattr(exc, "message", str(exc))
        self._log(f"{label} [HTTP {status} / {code}]: {message}", Qgis.MessageLevel.Warning)
