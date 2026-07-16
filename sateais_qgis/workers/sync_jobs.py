"""QThread worker that fetches the user's recent jobs from the server.

Backs the Jobs tab's "Sync" button: jobs submitted outside this QGIS session
(console, CLI, another machine) are pulled in via ``GET /api/v1/jobs`` and
merged into the local tracker.

Emits ``finished_signal(ok, jobs_or_none, error_code)``:
    - ``ok=True``: ``jobs`` is a list of ``Job`` snapshots (newest first).
    - ``ok=False``: ``jobs`` is ``None``, ``error_code`` is one of the
      ``ERROR_*`` constants below (shared vocabulary with the other workers).
"""

from __future__ import annotations

import traceback
from typing import Any

from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtCore import QThread, pyqtSignal

LOG_TAG = "SateAIs"

ERROR_AUTH_NOT_CONFIGURED = "AUTH_NOT_CONFIGURED"
ERROR_AUTH_FAILED = "AUTH_FAILED"
ERROR_SERVER_ERROR = "SERVER_ERROR"
ERROR_NETWORK_ERROR = "NETWORK_ERROR"


class SyncJobsWorker(QThread):
    """Fetch ``client.jobs.list()`` in the background."""

    # (ok, jobs_or_none, error_code)
    finished_signal = pyqtSignal(bool, object, str)

    def run(self) -> None:
        from ..core.api.errors import APIError, AuthenticationError
        from ..core.client_factory import AuthNotConfiguredError, build_client

        try:
            client = build_client()
        except AuthNotConfiguredError:
            self._log("no API key configured", Qgis.Warning)
            self.finished_signal.emit(False, None, ERROR_AUTH_NOT_CONFIGURED)
            return

        try:
            jobs = client.jobs.list()
            self._log(f"synced {len(jobs)} jobs from server", Qgis.Success)
            self.finished_signal.emit(True, jobs, "")
        except AuthenticationError as e:
            self._log_api_error("authentication failed", e)
            self.finished_signal.emit(False, None, ERROR_AUTH_FAILED)
        except APIError as e:
            self._log_api_error("job list failed", e)
            self.finished_signal.emit(False, None, ERROR_SERVER_ERROR)
        except Exception as e:  # noqa: BLE001
            self._log(f"unexpected error: {e}\n{traceback.format_exc()}", Qgis.Critical)
            self.finished_signal.emit(False, None, ERROR_NETWORK_ERROR)
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
