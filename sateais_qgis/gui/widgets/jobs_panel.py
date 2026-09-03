"""Jobs tab: lists tracked detection jobs and triggers result loading."""

from __future__ import annotations

import contextlib
import traceback

from qgis.core import Qgis, QgsApplication, QgsMessageLog
from qgis.PyQt.QtCore import QCoreApplication, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core import job_summary, job_tracker, layer_loader, result_stats
from ...workers.lifecycle import detach_worker
from ...workers.poll_job_task import ABANDON_EXPIRED, ABANDON_GONE, PollJobsTask
from ...workers.result_loader import (
    ERROR_AUTH_FAILED,
    ERROR_AUTH_NOT_CONFIGURED,
    ERROR_GONE,
    ERROR_JOB_NOT_COMPLETED,
    ERROR_NETWORK_ERROR,
    ERROR_NOT_FOUND,
    ERROR_PERMISSION_DENIED,
    ERROR_SERVER_ERROR,
    ERROR_UNSUPPORTED_FORMAT,
    ResultLoaderWorker,
)
from ...workers.sync_jobs import SyncJobsWorker
from .empty_state import EmptyState
from .job_card import JobCard

LOG_TAG = "SateAIs"


# Error codes emitted by ``ResultLoaderWorker`` mapped to end-user messages.
_RESULT_ERROR_MESSAGES: dict[str, str] = {
    ERROR_AUTH_NOT_CONFIGURED: "Please register an API key first.",
    ERROR_AUTH_FAILED: "Invalid API key. Please check your settings.",
    ERROR_PERMISSION_DENIED: "Your account no longer has access to this result.",
    ERROR_NOT_FOUND: "Result not found. The job may have been removed on the server.",
    ERROR_GONE: "This result has expired and is no longer available.",
    # 種別を名指ししない。QGIS が地図に置ける形式かどうかだけが基準
    ERROR_UNSUPPORTED_FORMAT: (
        "This result is not a map layer, so it cannot be opened in QGIS. "
        "Open it in the console to download it."
    ),
    ERROR_JOB_NOT_COMPLETED: ("The job is not completed yet. Please wait a moment and try again."),
    ERROR_SERVER_ERROR: "The server is temporarily unavailable. Please try again later.",
    ERROR_NETWORK_ERROR: "No network connection. Please check your internet.",
}


class JobsPanel(QWidget):
    """Scrollable list of TrackedJob cards backed by job_tracker storage."""

    aoi_preview_requested = pyqtSignal(str, str)  # (job_id, polygon_wkt)
    aoi_preview_unavailable = pyqtSignal(str)  # job_id
    job_removed = pyqtSignal(str)  # job_id
    result_loaded = pyqtSignal(str)  # job_id — result (and AOI layer) added to the map
    start_analysis_requested = pyqtSignal()  # empty-state CTA → switch to Analysis

    def __init__(self, iface, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.iface = iface
        self._cards: dict[str, JobCard] = {}
        # サーバが知らないジョブ。まとめて 1 通知にするため貯める
        self._forgotten: list[str] = []
        self._poll_task: PollJobsTask | None = None
        # Result-fetch workers keyed by job_id so multiple Load-on-Map clicks
        # can run in parallel without stepping on each other. Freed when the
        # worker's finished_signal fires.
        self._loaders: dict[str, ResultLoaderWorker] = {}
        self._sync_worker: SyncJobsWorker | None = None
        self._build_ui()
        self._load_existing_jobs()

    # --- lifecycle -----------------------------------------------------------

    def teardown(self) -> None:
        """Stop in-flight background work before this panel is destroyed.

        A QThread whose C++ object is deleted while the OS thread is still
        running makes Qt abort() the whole process. On plugin unload / QGIS
        close a Load-on-Map fetch may still be running (up to the client's HTTP
        timeout), so we detach the panel callback, ask each worker to stop, and
        wait briefly. If a worker does not finish in time we orphan it (see
        ``detach_worker``) so the panel can be destroyed while the thread winds
        down on its own.
        """
        # The poll task goes first, so a running poll cannot start further work
        # while the rest of this teardown runs.
        #
        # It also matters on QGIS exit: QGIS destroys the auth manager before it
        # waits for the task pool, so a pooled task thread that finishes during
        # shutdown can trip a use-after-free inside QGIS itself (observed on
        # 3.40.5: QgsAuthConfigurationStorageDb's per-thread cleanup slot firing
        # after the storage is gone). Cancelling here does not fix that bug — it
        # stops this plugin from keeping the pool alive long enough to hit it.
        # No wait(): the task belongs to QgsTaskManager, so we request the cancel
        # and let go. It polls isCanceled() every 0.5s, so it returns promptly.
        poll_task = self._poll_task
        self._poll_task = None
        if poll_task is not None:
            for signal in (
                poll_task.status_changed,
                poll_task.job_completed,
                poll_task.job_failed,
                poll_task.job_poll_abandoned,
                poll_task.auth_missing,
                # The completion signals too: their slots hold a reference to
                # this panel, and cancelling is exactly what makes them fire.
                poll_task.taskCompleted,
                poll_task.taskTerminated,
            ):
                with contextlib.suppress(TypeError, RuntimeError):
                    signal.disconnect()
            with contextlib.suppress(RuntimeError):
                poll_task.cancel()

        for worker in list(self._loaders.values()):
            try:
                worker.finished_signal.disconnect()
            except (TypeError, RuntimeError):
                # Already disconnected or the C++ object is gone; nothing to do.
                pass
            worker.requestInterruption()
            if worker.isRunning() and not worker.wait(1000):
                detach_worker(worker)
        self._loaders.clear()

        sync_worker = self._sync_worker
        self._sync_worker = None
        if sync_worker is not None:
            try:
                sync_worker.finished_signal.disconnect(self._on_sync_finished)
            except (TypeError, RuntimeError):
                pass
            if sync_worker.isRunning():
                detach_worker(sync_worker)

    # --- UI ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel(self.tr("Jobs"))
        title.setObjectName("TitleLabel")
        header.addWidget(title)
        header.addStretch()

        # ボタンは 1 つだけ。Sync（サーバからの取り込み）と Refresh（進行中の
        # 再ポーリング）は利用者から見て同じ「最新にする」なので分けない
        self.refresh_button = QPushButton(self.tr("Refresh"))
        self.refresh_button.setObjectName("Chip")
        self.refresh_button.clicked.connect(self._on_refresh_clicked)
        header.addWidget(self.refresh_button)
        outer.addLayout(header)

        # ID は 36 桁。打ち切る人はいないので、部分一致で打った端から絞り込む。
        # 種別名・シーン ID・日付も同じ箱で引ける（core.job_summary の haystack）
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("Chip")
        self.search_edit.setPlaceholderText(self.tr("Search jobs — ID, type, scene, date"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_search)
        search_row.addWidget(self.search_edit)
        # 絞り込みが効いていることが常に見えていないと、「ジョブが消えた」になる
        self.match_count_label = QLabel("")
        self.match_count_label.setObjectName("HintLabel")
        self.match_count_label.setVisible(False)
        search_row.addWidget(self.match_count_label)
        outer.addLayout(search_row)

        # 「まだ 1 件も無い」と「条件に合うものが無い」は別の状態。
        # 同じ文言にすると、絞り込んだだけなのに消えたと読まれる
        self.no_match_label = QLabel(self.tr("No jobs match this search."))
        self.no_match_label.setObjectName("HintLabel")
        self.no_match_label.setWordWrap(True)
        self.no_match_label.setVisible(False)
        outer.addWidget(self.no_match_label)

        # Cosmic empty state (starfield + CTA) shown when there are no jobs.
        self.empty_state = EmptyState()
        self.empty_state.start_requested.connect(self.start_analysis_requested)
        outer.addWidget(self.empty_state, 1)

        scroll = QScrollArea()
        scroll.setObjectName("JobsScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        # カード同士は下罫線で区切る。隙間まで空けると、内側が詰まっているのに
        # 外側だけ離れて見える（MCP の .row と同じ、内に余白・外は連続）
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_container)
        outer.addWidget(scroll, 1)

    # --- public API ----------------------------------------------------------

    def add_job(self, job_id: str, analysis_type: str, request: dict | None = None) -> None:
        """Called when AnalysisPanel reports a successful submit.

        ``request`` is the parameter set that was submitted, so the new card can
        say what it asked for without waiting for a Sync.
        """
        job = job_tracker.add(analysis_type, job_id, request=request, request_source="local")
        self._insert_card(job)
        self._ensure_polling([job_id])
        self._refresh_empty_state()

    # --- internal ------------------------------------------------------------

    def _load_existing_jobs(self) -> None:
        for job in job_tracker.list_all():
            self._insert_card(job, prepend=False)
        pending = [
            job.job_id
            for job in job_tracker.list_all()
            if job.status in {"pending", "processing", "unknown"}
        ]
        if pending:
            self._ensure_polling(pending)
        self._refresh_empty_state()

    def _insert_card(self, job, prepend: bool = True) -> None:
        if job.job_id in self._cards:
            return
        card = JobCard(job, parent=self._list_container)
        card.load_requested.connect(self._on_load_requested)
        card.aoi_preview_requested.connect(self._on_aoi_preview_requested)
        self._cards[job.job_id] = card
        # The stretch lives at index `count - 1`; insert above it.
        insert_at = 0 if prepend else max(0, self._list_layout.count() - 1)
        self._list_layout.insertWidget(insert_at, card)
        self._apply_search()

    def _apply_search(self, text: str = "") -> None:
        """Show only the cards matching the query. Runs on every keystroke.

        Two things keep this cheap as the list grows: each card's haystack is
        built once (not per keystroke), and ``setVisible`` is only called when
        the answer actually changes — a redundant call still invalidates the
        layout, which is the expensive part, not the string compare.
        """
        query = (text or self.search_edit.text()).strip().lower()
        shown = 0
        for card in self._cards.values():
            match = (not query) or (query in card.search_text)
            if card.isVisibleTo(self) != match:
                card.setVisible(match)
            shown += match
        total = len(self._cards)
        self.match_count_label.setText(f"{shown} / {total}")
        self.match_count_label.setVisible(bool(query) and total > 0)
        self.no_match_label.setVisible(bool(query) and total > 0 and shown == 0)

    def _refresh_empty_state(self) -> None:
        self.empty_state.setVisible(not self._cards)

    # --- polling -------------------------------------------------------------

    def _ensure_polling(self, job_ids: list[str]) -> None:
        if not job_ids:
            return
        if self._poll_task is not None and self._poll_task.has_pending():
            for job_id in job_ids:
                self._poll_task.add_job(job_id)
            return
        task = PollJobsTask(job_ids)
        task.status_changed.connect(self._on_status_changed)
        task.job_completed.connect(self._on_job_completed)
        task.job_failed.connect(self._on_job_failed)
        task.job_poll_abandoned.connect(self._on_poll_abandoned)
        task.auth_missing.connect(self._on_poll_auth_missing)
        # Bind the task into the slot so a late completion of an *old* task can
        # never clear (or disconnect) a newer task that replaced it.
        task.taskCompleted.connect(lambda t=task: self._on_task_finished(t))
        task.taskTerminated.connect(lambda t=task: self._on_task_finished(t))
        self._poll_task = task
        QgsApplication.taskManager().addTask(task)

    def _restart_polling(self) -> None:
        pending = [
            job.job_id
            for job in job_tracker.list_all()
            if job.status in {"pending", "processing", "unknown"}
        ]
        if not pending:
            self.iface.messageBar().pushMessage(
                "SateAIs",
                self.tr("All jobs are in a terminal state — nothing to refresh."),
                level=Qgis.MessageLevel.Info,
                duration=4,
            )
            return
        self._ensure_polling(pending)

    # --- server sync ---------------------------------------------------------

    # Types this plugin can track and load. Anything else the server reports
    # (e.g. a type whose result is a ZIP rather than GeoJSON) is skipped.
    _SYNCABLE_TYPES = frozenset(
        {"ship", "oilslick", "newbuilding", "disappearbuilding", "timeseries"}
    )

    def _on_refresh_clicked(self) -> None:
        """Pull the latest jobs from the server, then re-arm polling."""
        if self._sync_worker is not None:
            return
        self.refresh_button.setEnabled(False)
        worker = SyncJobsWorker(parent=self)
        worker.finished_signal.connect(self._on_sync_finished)
        worker.finished.connect(worker.deleteLater)
        self._sync_worker = worker
        worker.start()

    def _on_sync_finished(self, ok: bool, jobs: object, error_code: str) -> None:
        worker = self._sync_worker
        self._sync_worker = None
        if worker is not None:
            try:
                worker.finished_signal.disconnect(self._on_sync_finished)
            except (TypeError, RuntimeError):
                pass
        self.refresh_button.setEnabled(True)

        if not ok or not isinstance(jobs, list):
            message = _RESULT_ERROR_MESSAGES.get(
                error_code, _RESULT_ERROR_MESSAGES[ERROR_SERVER_ERROR]
            )
            self.iface.messageBar().pushMessage(
                "SateAIs", self.tr(message), level=Qgis.MessageLevel.Warning, duration=6
            )
            return

        imported = updated = skipped = 0
        active: list[str] = []
        # The server returns newest first; iterate oldest→newest with prepend
        # so freshly imported cards end up newest-on-top like local submits.
        for job in reversed(jobs):
            analysis_type = job.endpoint_id or ""
            if analysis_type not in self._SYNCABLE_TYPES:
                skipped += 1
                continue
            status = job.status.value
            # The list endpoint echoes back what the job was submitted with —
            # the only way to learn that for jobs submitted from the console, the
            # CLI or MCP (the single-job status endpoint omits it). Backfilling
            # the AOI here is also what makes those jobs previewable on the map.
            source = "server" if job.request_params else "unavailable"
            if job_id := job.job_id:
                if job_id in self._cards:
                    tracked = job_tracker.update_status(
                        job_id,
                        status,
                        job.error_code,
                        job.error_message,
                        completed_at=job.completed_at,
                        area_sqkm=job.area_sqkm,
                        credits_used=job.credits_used,
                    )
                    if tracked is not None:
                        card = self._cards[job_id]
                        card.set_status(status, job.error_code, job.error_message)
                        resolved = job_tracker.set_request_context(
                            job_id, job.request_params, source
                        )
                        if resolved is not None:
                            card.apply_request_context(resolved)
                        updated += 1
                else:
                    tracked = job_tracker.add(
                        analysis_type,
                        job_id,
                        submitted_at=job.created_at,
                        status=status,
                        request=job.request_params,
                        request_source=source,
                    )
                    job_tracker.update_status(
                        job_id,
                        status,
                        job.error_code,
                        job.error_message,
                        completed_at=job.completed_at,
                        area_sqkm=job.area_sqkm,
                        credits_used=job.credits_used,
                    )
                    self._insert_card(tracked)
                    imported += 1
                if status in {"pending", "processing"}:
                    active.append(job_id)
        if active:
            self._ensure_polling(active)
        self._refresh_empty_state()

        summary = self.tr(f"Refreshed — {imported} new, {updated} updated.")
        if skipped:
            summary += self.tr(f" {skipped} unsupported job(s) skipped.")
        self.iface.messageBar().pushMessage(
            "SateAIs", summary, level=Qgis.MessageLevel.Success, duration=5
        )

    def _on_task_finished(self, task: PollJobsTask) -> None:
        if task is self._poll_task:
            self._poll_task = None
        # Drop every connection into this panel so a finished task object can
        # never re-enter our handlers (QgsTaskManager may keep it alive briefly).
        for signal in (
            task.status_changed,
            task.job_completed,
            task.job_failed,
            task.job_poll_abandoned,
            task.auth_missing,
        ):
            try:
                signal.disconnect()
            except (TypeError, RuntimeError):
                pass

    # --- signal handlers -----------------------------------------------------

    def _on_status_changed(self, job_id: str, status: str) -> None:
        job_tracker.update_status(job_id, status)
        card = self._cards.get(job_id)
        if card is not None:
            card.set_status(status)

    def _on_job_completed(self, job_id: str) -> None:
        job_tracker.update_status(job_id, "completed")
        card = self._cards.get(job_id)
        if card is not None:
            card.set_status("completed")

    def _on_poll_auth_missing(self) -> None:
        self.iface.messageBar().pushMessage(
            "SateAIs",
            self.tr(
                "Job statuses cannot be updated — no API key is configured. "
                "Open Plugins → SateAIs API for QGIS → Settings… to set one."
            ),
            level=Qgis.MessageLevel.Warning,
            duration=8,
        )

    def _on_poll_abandoned(self, job_id: str, reason: str) -> None:
        """The poll task gave up on this job without a terminal state.

        The job may still be running server-side, so it is marked "unknown"
        (not "failed") and Refresh re-arms tracking for it — except when the
        server says the job is gone, which Refresh cannot change.
        """
        job_tracker.update_status(job_id, "unknown")
        card = self._cards.get(job_id)
        if card is not None:
            card.set_status("unknown")
        short_id = f"{job_id[:8]}…" if len(job_id) > 8 else job_id
        if reason == ABANDON_GONE:
            # ジョブのメタデータはサーバ側で永久保持される（保持期限があるのは
            # 結果ファイルだけ）。したがって status の 404 は「このアカウントに
            # 無いジョブ」であって、待てば直るものではない。一覧から取り除く
            self._forget_job(job_id)
            return
        if reason == ABANDON_EXPIRED:
            message = self.tr(
                f"Stopped tracking job {short_id} after 24 hours. "
                "Press Refresh to resume, or check the job in the console."
            )
        else:
            message = self.tr(
                f"Could not retrieve the status of job {short_id} after repeated attempts. "
                "Press Refresh to retry, or check the job in the console."
            )
        self.iface.messageBar().pushMessage(
            "SateAIs",
            message,
            level=Qgis.MessageLevel.Warning,
            duration=8,
        )

    def _forget_job(self, job_id: str) -> None:
        """Drop a job the server does not know about, from the list and the store.

        These are ids that never belonged to this account — a key swapped between
        environments, or entries written by something other than a real submit.
        Leaving them behind means the same warning on every Refresh, forever, for
        a job the user cannot act on.
        """
        job_tracker.remove(job_id)
        card = self._cards.pop(job_id, None)
        if card is not None:
            self._list_layout.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        # 地図に出ているのがこのジョブの範囲なら、それも一緒に消える必要がある
        # （受け手は dock の _on_job_removed）
        self.job_removed.emit(job_id)
        self._forgotten.append(job_id)
        # 6 件まとめて消えることもある。1 件ずつ通知すると画面が埋まる
        QTimer.singleShot(0, self._flush_forgotten)

    def _flush_forgotten(self) -> None:
        count = len(self._forgotten)
        if not count:
            return
        self._forgotten.clear()
        self._apply_search()
        self.iface.messageBar().pushMessage(
            "SateAIs",
            self.tr(f"Removed {count} job(s) from this list: they are not on your account."),
            level=Qgis.MessageLevel.Info,
            duration=6,
        )
        self._refresh_empty_state()

    def _on_job_failed(self, job_id: str, error_code: str, error_message: str) -> None:
        job_tracker.update_status(
            job_id, "failed", error_code=error_code or None, error_message=error_message or None
        )
        card = self._cards.get(job_id)
        if card is not None:
            card.set_status(
                "failed", error_code=error_code or None, error_message=error_message or None
            )

    def _on_aoi_preview_requested(self, job_id: str, polygon_wkt: str) -> None:
        if not polygon_wkt:
            self.aoi_preview_unavailable.emit(job_id)
            return
        self.aoi_preview_requested.emit(job_id, polygon_wkt)

    def _on_load_requested(self, job_id: str) -> None:
        """Kick off the background fetch for a completed job's GeoJSON.

        The card immediately switches to loading state (disabled Load button +
        thin cyan progress bar) so the click has visible feedback. The actual
        S3 302 redirect + JSON parse happens on a background QThread; the layer
        is added back on the UI thread once the worker signals completion.
        """
        card = self._cards.get(job_id)
        if card is None:
            return

        # Ignore extra clicks while a fetch for this job is already running.
        if job_id in self._loaders:
            return

        # Make the actual id we are about to use visible in the log; a mismatch
        # with the server's UUID validator is the most common cause of a 400
        # VALIDATION_ERROR on this endpoint.
        QgsMessageLog.logMessage(
            f"load result requested job_id={job_id!r} (len={len(job_id)})",
            LOG_TAG,
            Qgis.MessageLevel.Info,
        )

        # The card shows an in-place orbiting-satellite indicator while the
        # fetch is in flight (see JobCard.set_loading). We intentionally do NOT
        # push a custom animated widget into the QGIS message bar — doing so
        # segfaults QGIS on macOS.
        card.set_loading(True)

        worker = ResultLoaderWorker(job_id, parent=self)
        worker.finished_signal.connect(
            lambda ok, geojson, code, jid=job_id: self._on_result_loaded(jid, ok, geojson, code)
        )
        # Free the QThread's C++ object once the thread has fully finished. The
        # Qt parent (self) keeps it alive during the run; deleteLater collects
        # it afterwards so finished workers don't pile up as child objects.
        worker.finished.connect(worker.deleteLater)
        self._loaders[job_id] = worker
        worker.start()

    def _on_result_loaded(
        self,
        job_id: str,
        ok: bool,
        geojson: object,
        error_code: str,
    ) -> None:
        """Runs on the UI thread. Add the fetched GeoJSON as a layer or show an error."""
        card = self._cards.get(job_id)
        if card is not None:
            card.set_loading(False)
        self._loaders.pop(job_id, None)

        if not ok:
            message = _RESULT_ERROR_MESSAGES.get(
                error_code, _RESULT_ERROR_MESSAGES[ERROR_SERVER_ERROR]
            )
            self.iface.messageBar().pushMessage(
                "SateAIs",
                self.tr(message),
                level=Qgis.MessageLevel.Warning,
                duration=6,
            )
            return

        if card is None or geojson is None:
            # Card was removed while the fetch was in flight; nothing to do.
            return

        job = card.job
        count = result_stats.count_detections(geojson, job.analysis_type)
        try:
            layer_name = layer_loader.build_layer_name(
                job.analysis_type, job.job_id, job.submitted_at, count
            )
            layer = layer_loader.load_geojson_as_layer(geojson, layer_name, job.analysis_type)
            layer_loader.add_to_project(layer, self.iface)
        except Exception as e:  # noqa: BLE001
            QgsMessageLog.logMessage(
                f"failed to add layer for {job_id}: {e}\n{traceback.format_exc()}",
                LOG_TAG,
                Qgis.MessageLevel.Critical,
            )
            self.iface.messageBar().pushMessage(
                "SateAIs",
                self.tr("Could not add the result as a layer."),
                level=Qgis.MessageLevel.Warning,
                duration=6,
            )
            return

        # The user's AOI frame becomes its own outline-only layer (below the
        # result in the layer tree) so it can be toggled off when it overlaps
        # the detections. The always-on-top rubber-band preview is cleared by
        # the dock via result_loaded for the same reason.
        if job.polygon:
            try:
                aoi_layer = layer_loader.load_aoi_as_layer(
                    job.polygon,
                    layer_loader.build_aoi_layer_name(job.analysis_type, job.job_id),
                )
                if aoi_layer is not None:
                    layer_loader.add_aoi_to_project(aoi_layer)
            except Exception as e:  # noqa: BLE001
                # The AOI frame is auxiliary; never fail the result load over it.
                QgsMessageLog.logMessage(
                    f"could not add AOI layer for {job_id}: {e}", LOG_TAG, Qgis.MessageLevel.Warning
                )
        self.result_loaded.emit(job_id)

        # Persist the find count and surface it on the card badge so the job
        # reads e.g. "✦ 23 ships" from now on (survives restarts).
        job_tracker.set_detection_count(job_id, count)
        card.set_detection_count(count)

        if count > 0:
            message = (
                f"{job_summary.format_detection_summary(job.analysis_type, count)}"
                " detected — added to map"
            )
        else:
            message = "No detections found in this result."
        self.iface.messageBar().pushMessage(
            "SateAIs",
            self.tr(message),
            level=Qgis.MessageLevel.Success,
            duration=5,
        )

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("JobsPanel", message)
