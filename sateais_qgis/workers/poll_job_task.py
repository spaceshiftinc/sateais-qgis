"""QgsTask that polls all pending jobs and emits status updates."""

from __future__ import annotations

import contextlib
import time
import traceback
from typing import Any

from qgis.core import Qgis, QgsMessageLog, QgsTask
from qgis.PyQt.QtCore import pyqtSignal

LOG_TAG = "SateAIs"
POLL_INTERVAL_SECONDS = 30

# Escape hatches so the task can never poll forever (a job that the server
# keeps reporting as non-terminal, or one whose status request keeps failing,
# would otherwise keep this thread alive until QGIS exits).
MAX_CONSECUTIVE_POLL_ERRORS = 5
MAX_TRACKING_SECONDS = 24 * 60 * 60  # give up after 24h; Refresh re-arms it

# Reasons carried by ``job_poll_abandoned``.
ABANDON_ERRORS = "errors"
ABANDON_EXPIRED = "expired"
# サーバがそのジョブを知らない（404 / 410）。保持期間を過ぎて結果が消えた場合が
# これで、何度聞いても答えは変わらない
ABANDON_GONE = "gone"


class PollJobsTask(QgsTask):
    """Long-running task that polls a set of job ids until they all reach a terminal state.

    Emits:
        status_changed(job_id, status):
            Whenever the server returns a new status for a tracked job.
        job_completed(job_id):
            When a job transitions to ``completed``.
        job_failed(job_id, error_code, error_message):
            When a job transitions to ``failed``.
        job_poll_abandoned(job_id, reason):
            When the task gives up on a job without reaching a terminal state
            (``reason`` is ``ABANDON_ERRORS`` or ``ABANDON_EXPIRED``). The job
            itself may still be running server-side; the UI should mark it
            "unknown" and offer Refresh to resume tracking.
        auth_missing():
            When polling cannot start because no API key is configured.
    """

    status_changed = pyqtSignal(str, str)
    job_completed = pyqtSignal(str)
    job_failed = pyqtSignal(str, str, str)
    job_poll_abandoned = pyqtSignal(str, str)
    auth_missing = pyqtSignal()

    def __init__(self, job_ids: list[str]) -> None:
        super().__init__("SateAIs: tracking jobs", QgsTask.Flag.CanCancel)
        # _pending / _last_status / _errors / _first_seen are mutated from the
        # task thread (run()) and the UI thread (add_job()). Reads/writes of
        # list / dict are atomic in CPython, which is sufficient for the simple
        # operations used here.
        self._pending: list[str] = list(dict.fromkeys(job_ids))
        self._last_status: dict[str, str] = {}
        self._errors: dict[str, int] = {}
        now = time.monotonic()
        self._first_seen: dict[str, float] = {job_id: now for job_id in self._pending}

    def add_job(self, job_id: str) -> None:
        """Append a freshly submitted job to the polling set (UI-thread safe enough)."""
        if job_id not in self._pending and self._last_status.get(job_id) not in {
            "completed",
            "failed",
        }:
            self._first_seen.setdefault(job_id, time.monotonic())
            self._pending.append(job_id)

    def has_pending(self) -> bool:
        return bool(self._pending)

    # --- QgsTask hooks -------------------------------------------------------

    def run(self) -> bool:
        from ..core.api.errors import APIError, NotFoundError
        from ..core.client_factory import AuthNotConfiguredError, build_client

        try:
            client = build_client()
        except AuthNotConfiguredError:
            self._log("no API key configured; stopping poll task", Qgis.MessageLevel.Warning)
            self.auth_missing.emit()
            return False

        try:
            while self._pending and not self.isCanceled():
                # Snapshot to allow add_job() to mutate during iteration.
                for job_id in list(self._pending):
                    if self.isCanceled():
                        break

                    started = self._first_seen.setdefault(job_id, time.monotonic())
                    if time.monotonic() - started > MAX_TRACKING_SECONDS:
                        self._drop(job_id)
                        self._log(f"gave up tracking {job_id} after 24h", Qgis.MessageLevel.Warning)
                        self.job_poll_abandoned.emit(job_id, ABANDON_EXPIRED)
                        continue

                    try:
                        job = client.jobs.status(job_id)
                    except NotFoundError as e:
                        # 恒久的な答え。再試行の予算を使い切ってから「Refresh を
                        # 押せ」と案内すると、成功しない操作を繰り返させることになる
                        self._log_api_error(f"poll {job_id}", e)
                        self._drop(job_id)
                        self.job_poll_abandoned.emit(job_id, ABANDON_GONE)
                        continue
                    except APIError as e:
                        self._log_api_error(f"poll {job_id}", e)
                        self._register_error(job_id)
                        continue
                    except Exception as e:  # noqa: BLE001
                        self._log(
                            f"unexpected error polling {job_id}: {e}\n{traceback.format_exc()}",
                            Qgis.MessageLevel.Critical,
                        )
                        self._register_error(job_id)
                        continue

                    # A successful poll resets the consecutive-error budget.
                    self._errors.pop(job_id, None)

                    status_value = job.status.value
                    previous = self._last_status.get(job_id)
                    if status_value != previous:
                        self._last_status[job_id] = status_value
                        self.status_changed.emit(job_id, status_value)

                    if job.is_completed:
                        self._drop(job_id)
                        self.job_completed.emit(job_id)
                    elif job.is_failed:
                        self._drop(job_id)
                        self.job_failed.emit(
                            job_id,
                            job.error_code or "",
                            job.error_message or "",
                        )

                if not self._pending:
                    break
                self._sleep(POLL_INTERVAL_SECONDS)

            return True
        finally:
            with contextlib.suppress(Exception):
                client.close()

    def finished(self, result: bool) -> None:  # pragma: no cover - UI hook
        if not result:
            self._log("poll task ended early (no client or error)", Qgis.MessageLevel.Warning)

    # --- helpers -------------------------------------------------------------

    def _register_error(self, job_id: str) -> None:
        """Count a failed poll; abandon the job after too many in a row.

        Transient errors (one-off network blips) should not drop the job, so
        the budget only runs out on *consecutive* failures.
        """
        count = self._errors.get(job_id, 0) + 1
        self._errors[job_id] = count
        if count >= MAX_CONSECUTIVE_POLL_ERRORS:
            self._drop(job_id)
            self._log(
                f"gave up tracking {job_id} after {count} consecutive poll errors",
                Qgis.MessageLevel.Warning,
            )
            self.job_poll_abandoned.emit(job_id, ABANDON_ERRORS)

    def _drop(self, job_id: str) -> None:
        """Forget a job entirely (pending set + bookkeeping)."""
        if job_id in self._pending:
            self._pending.remove(job_id)
        self._errors.pop(job_id, None)
        self._first_seen.pop(job_id, None)

    def _sleep(self, seconds: float) -> None:
        """Sleep in small chunks so cancellation is responsive."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.isCanceled():
                return
            time.sleep(min(0.5, deadline - time.monotonic()))

    @staticmethod
    def _log(message: str, level: int = Qgis.MessageLevel.Info) -> None:
        QgsMessageLog.logMessage(message, LOG_TAG, level)

    def _log_api_error(self, label: str, exc: Any) -> None:
        status = getattr(exc, "status_code", "?")
        code = getattr(exc, "code", None) or "-"
        message = getattr(exc, "message", str(exc))
        self._log(f"{label} [HTTP {status} / {code}]: {message}", Qgis.MessageLevel.Warning)
