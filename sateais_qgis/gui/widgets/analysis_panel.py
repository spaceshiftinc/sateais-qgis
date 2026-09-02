"""The Analyze tab: pick a analysis type, fill the form, submit a job.

When no API key is configured yet, the tab shows a welcome page (what the
plugin does + how to get a key) instead of the submit form, so first-run users
are guided to Settings before they can hit an auth error.
"""

from __future__ import annotations

from typing import Any

from qgis.core import Qgis
from qgis.PyQt.QtCore import QCoreApplication, Qt, QTimer, QUrl, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...core import client_factory, job_summary
from ...core.api.types import Preview
from ...workers import submit_task
from ...workers.lifecycle import detach_worker
from ...workers.preview_task import PreviewWorker
from ...workers.submit_task import SubmitAnalysisWorker
from ..auth_dialog import SIGNUP_URL
from ..icons import kind_icon
from .date_range_form import DateRangeForm
from .estimate_card import EstimateCard
from .scene_polygon_form import ScenePolygonForm

# 入力を打っている最中に投げない。止まってから見積もる
PREVIEW_DEBOUNCE_MS = 600

# (label, analysis_type, form_index, subtitle, tooltip)
# form_index: 0 = scene_polygon_form, 1 = date_range_form
# subtitle / tooltip: 数値 (面積上限や推論時間) は API 側と drift しやすいので書かず、
# 何を検出するか + 指定方法だけを添える。詳細は docs.spcsft.com 側で。
# label は core.job_summary から引く (Jobs カード・tooltip・検索と共通の単一定義)。
ANALYSIS_OPTIONS: list[tuple[str, str, int, str, str]] = [
    (
        job_summary.ANALYSIS_LABELS["ship"],
        "ship",
        0,
        "Detect ships (vessels)",
        "Detect ships from SAR satellite imagery. Specify a scene ID or an AOI + date.",
    ),
    (
        job_summary.ANALYSIS_LABELS["oilslick"],
        "oilslick",
        0,
        "Detect oil slicks on the sea surface",
        "Detect oil slicks (surface oil films) from SAR imagery. Specify a scene ID or an AOI + date.",
    ),
    (
        job_summary.ANALYSIS_LABELS["newbuilding"],
        "newbuilding",
        1,
        "Detect newly built structures in a period",
        "Detect buildings newly constructed within an AOI between date_start and date_end.",
    ),
    (
        job_summary.ANALYSIS_LABELS["disappearbuilding"],
        "disappearbuilding",
        1,
        "Detect demolished structures in a period",
        "Detect buildings demolished within an AOI between date_start and date_end.",
    ),
    (
        job_summary.ANALYSIS_LABELS["timeseries"],
        "timeseries",
        1,
        "Detect time-series changes over a period",
        "Detect time-series changes within an AOI between date_start and date_end.",
    ),
]

ERROR_MESSAGES: dict[str, str] = {
    submit_task.ERROR_AUTH_NOT_CONFIGURED: "Please register an API key first.",
    submit_task.ERROR_AUTH_FAILED: "Invalid API key. Please check your settings.",
    submit_task.ERROR_PERMISSION_DENIED: (
        "This analysis is not enabled for your account. Please request access from the console."
    ),
    submit_task.ERROR_INSUFFICIENT_CREDITS: ("Insufficient credits. Please top up in the console."),
    submit_task.ERROR_INVALID_INPUT: "Please fill in the required fields.",
    submit_task.ERROR_VALIDATION_FAILED: (
        "The server rejected the request. Please review the inputs."
    ),
    submit_task.ERROR_NOT_FOUND: (
        "The requested data was not found (no matching scene or polygon). "
        "Please adjust the area or date and try again."
    ),
    submit_task.ERROR_CONFLICT: (
        "The resource is not ready yet. Please wait a moment and try again."
    ),
    submit_task.ERROR_PAYLOAD_TOO_LARGE: (
        "The selected area is too large. Please choose a smaller area."
    ),
    submit_task.ERROR_RATE_LIMITED: "Too many requests. Please wait a moment and try again.",
    submit_task.ERROR_SERVER_ERROR: (
        "The server is temporarily unavailable. Please try again later."
    ),
    submit_task.ERROR_NETWORK_ERROR: "No network connection. Please check your internet.",
}


class AnalysisPanel(QWidget):
    """Analysis type selector + dynamic form + submit button."""

    polygon_picker_requested = pyqtSignal()
    # (job_id, analysis_type, request_params) — the whole submitted parameter set
    # travels with the job so the Jobs tab can say what was asked for.
    job_submitted = pyqtSignal(str, str, object)
    settings_requested = pyqtSignal()  # welcome-page CTA → open the auth dialog
    # (requested_wkt, analysed_wkt|None) — キャンバスに重ねる 2 つの範囲。
    # 見積もりが取れないうちは analysed=None で「まだ分からない」を表す
    coverage_changed = pyqtSignal(str, object)

    def __init__(self, iface, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.iface = iface
        self._worker: SubmitAnalysisWorker | None = None
        # Request captured at submit time: the AOI so the Jobs tab can preview it,
        # plus the dates / scene id so the card is identifiable. Snapshotted at
        # submit rather than read back on completion, because the user is free to
        # change the form (including the analysis type) while a submit is in
        # flight.
        self._submit_request: dict[str, Any] = {}
        self._submit_type: str = ""
        # 見積もりは入力のたびに投げ直す。古い応答が新しい入力の値として
        # 表示されないよう、投げるたびに世代を進めて着信時に照合する
        self._preview_worker: PreviewWorker | None = None
        self._preview_seq = 0
        self._preview_retried = False
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._preview_timer.timeout.connect(self._start_preview)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        # Page 0: first-run welcome (no API key yet). Page 1: the submit form.
        self._root_stack = QStackedWidget()
        self._root_stack.addWidget(self._build_welcome_page())
        self._root_stack.addWidget(self._build_form_page())
        root.addWidget(self._root_stack)
        self.refresh_auth_state()

    def _build_welcome_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 32, 24, 24)
        layout.setSpacing(12)

        title = QLabel(self.tr("Welcome to SateAIs"))
        title.setObjectName("TitleLabel")
        layout.addWidget(title)

        subtitle = QLabel(
            self.tr(
                "Run SAR satellite detections — ships, oil slicks, building changes — "
                "right from QGIS, and get the results back as map layers."
            )
        )
        subtitle.setObjectName("SubtitleLabel")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        steps = QLabel(
            self.tr(
                "1.  Create a free account — new accounts include welcome credits\n"
                "2.  Copy your API key and paste it into Settings\n"
                "3.  Draw an area on the map and submit your first analysis"
            )
        )
        steps.setObjectName("HintLabel")
        steps.setWordWrap(True)
        layout.addWidget(steps)

        layout.addSpacing(8)

        # 初回の人が取るべき行動は「アカウントを作る」なので、そちらを主ボタンに
        # 置く。以前は Settings が主ボタンだったが、鍵を持っていない人にとっては
        # 開いても何もできない。
        create_account = QPushButton(self.tr("Create a free account →"))
        create_account.setObjectName("PrimaryButton")
        create_account.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(SIGNUP_URL)))
        layout.addWidget(create_account)

        open_settings = QPushButton(self.tr("I already have an API key — open Settings"))
        open_settings.setObjectName("GhostButton")
        open_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        open_settings.setFlat(True)
        open_settings.clicked.connect(self.settings_requested)
        layout.addWidget(open_settings)

        layout.addStretch()
        return page

    def refresh_auth_state(self) -> None:
        """Show the submit form when an API key is configured, else the welcome page."""
        self._root_stack.setCurrentIndex(1 if client_factory.has_api_key() else 0)

    def _build_form_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(12)

        title = QLabel(self.tr("Submit an analysis"))
        title.setObjectName("TitleLabel")
        outer.addWidget(title)

        outer.addWidget(self._section_label(self.tr("Analysis Type")))
        self.type_combo = QComboBox()
        for label, analysis_type, _, _, _ in ANALYSIS_OPTIONS:
            # アイコンと色は MCP ウィジェット・結果レイヤーと同じ出どころ
            self.type_combo.addItem(kind_icon(analysis_type), label)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        outer.addWidget(self.type_combo)

        # QGIS ネイティブの QComboBox のすぐ下に、選択中の 1 行 subtitle を静かに置く。
        # 数値 (面積上限や所要時間) はここには書かず、詳細は combo に付けた tooltip で。
        self.type_subtitle = QLabel("")
        self.type_subtitle.setObjectName("HintLabel")
        self.type_subtitle.setWordWrap(True)
        outer.addWidget(self.type_subtitle)

        self._stack = QStackedWidget()
        self.scene_polygon_form = ScenePolygonForm(self)
        self.date_range_form = DateRangeForm(self)
        self.scene_polygon_form.polygon_picker_requested.connect(self.polygon_picker_requested.emit)
        self.date_range_form.polygon_picker_requested.connect(self.polygon_picker_requested.emit)
        self.scene_polygon_form.inputs_changed.connect(self._on_inputs_changed)
        self.date_range_form.inputs_changed.connect(self._on_inputs_changed)
        self._stack.addWidget(self.scene_polygon_form)
        self._stack.addWidget(self.date_range_form)
        outer.addWidget(self._stack)

        # 投入ボタンの真上。押す直前に、何が解析され幾ら掛かるかを読む場所
        self.estimate_card = EstimateCard(self)
        outer.addWidget(self.estimate_card)

        # Status + submit
        self.status_label = QLabel("")
        self.status_label.setObjectName("HintLabel")
        self.status_label.setWordWrap(True)
        outer.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        outer.addWidget(self.progress)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.submit_button = QPushButton(self.tr("Submit"))
        self.submit_button.setObjectName("PrimaryButton")
        self.submit_button.setDefault(True)
        self.submit_button.clicked.connect(self._on_submit_clicked)
        btn_row.addWidget(self.submit_button)
        outer.addLayout(btn_row)

        outer.addStretch()

        self._on_type_changed(0)
        return page

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionLabel")
        return label

    def _current_form(self):
        return self._stack.currentWidget()

    def _current_analysis_type(self) -> str:
        return ANALYSIS_OPTIONS[self.type_combo.currentIndex()][1]

    # --- public API ----------------------------------------------------------

    def set_polygon(self, wkt: str, area_km2: float) -> None:
        """Forward a picked polygon to whichever form is currently visible."""
        form = self._current_form()
        form.set_polygon(wkt, area_km2)

    def set_pick_in_progress(self, in_progress: bool) -> None:
        """Reflect the polygon-picker state in the form (disable Submit, show hint)."""
        self.submit_button.setEnabled(not in_progress)
        if in_progress:
            self._show_status(
                True,
                self.tr("Drag a rectangle on the map to set the polygon."),
            )
        else:
            self._clear_status()

    # --- handlers ------------------------------------------------------------

    def _on_type_changed(self, combo_index: int) -> None:
        _, _, form_index, subtitle, tooltip = ANALYSIS_OPTIONS[combo_index]
        self._stack.setCurrentIndex(form_index)
        self.type_subtitle.setText(subtitle)
        self.type_combo.setToolTip(tooltip)
        self._clear_status()
        # 種別が変われば解析されるシーンも料金も変わる。前の見積もりは捨てる
        self._on_inputs_changed()

    # --- pre-run estimate ----------------------------------------------------

    def _on_inputs_changed(self) -> None:
        """Inputs changed: drop the stale estimate and schedule a fresh one."""
        self._drop_preview()
        kwargs = self._current_form().build_kwargs()
        polygon = (kwargs or {}).get("polygon")
        # scene_id 指定では解析範囲がシーンで決まるので、地図に重ねる要求範囲もない
        self.coverage_changed.emit(polygon or "", None)
        if kwargs is None or not polygon:
            return
        self._preview_retried = False
        self._preview_timer.start()

    def _drop_preview(self) -> None:
        """Invalidate any in-flight estimate and clear what is on screen.

        Advancing the sequence is what makes a late response harmless: it
        arrives, fails the check, and is discarded instead of being shown
        against inputs it was never computed for.
        """
        self._preview_seq += 1
        self._preview_timer.stop()
        self.estimate_card.reset()

    def _detach_preview_worker(self) -> None:
        """Let go of the current estimate worker without waiting for it.

        Its result is already invalidated by the sequence number, so there is
        nothing to wait for. Blocking on it instead would mean that redrawing
        the area while an estimate is in flight leaves the card empty until the
        user touches an input again.
        """
        worker = self._preview_worker
        self._preview_worker = None
        if worker is None:
            return
        try:
            worker.finished_signal.disconnect()
        except (TypeError, RuntimeError):
            pass
        if worker.isRunning():
            detach_worker(worker)

    def _start_preview(self) -> None:
        kwargs = self._current_form().build_kwargs()
        if kwargs is None or not kwargs.get("polygon"):
            return

        # 前の問い合わせが残っていても待たない（結果は seq で無効化済み）
        self._detach_preview_worker()
        self._preview_seq += 1
        seq = self._preview_seq
        self.estimate_card.show_busy()

        worker = PreviewWorker(self._current_analysis_type(), dict(kwargs), parent=self)
        worker.finished_signal.connect(
            lambda ok, payload, seq=seq: self._on_preview_finished(ok, payload, seq)
        )
        worker.finished.connect(worker.deleteLater)
        self._preview_worker = worker
        worker.start()

    def _on_preview_finished(self, ok: bool, payload: Any, seq: int) -> None:
        if seq != self._preview_seq:
            # 入力が変わった後に届いた応答。捨てる。**_preview_worker は触らない**
            # ——すでに次の問い合わせが入っているので、ここで消すと取り違える
            return
        self._preview_worker = None

        if ok and isinstance(payload, Preview):
            self._preview_retried = False
            self.estimate_card.show_preview(payload)
            coverage = payload.coverage.polygon if payload.coverage else None
            requested = (self._current_form().build_kwargs() or {}).get("polygon") or ""
            self.coverage_changed.emit(requested, coverage)
            return

        # 一度だけ聞き直す。コールドスタート直後は落ちても、二度目は返る
        if not self._preview_retried:
            self._preview_retried = True
            self._preview_timer.start()
            return
        self.estimate_card.show_failed()

    def _on_submit_clicked(self) -> None:
        # The button is disabled while a submit is in flight, but guard anyway:
        # a second worker would race the first one's completion handler.
        if self._worker is not None:
            return

        form = self._current_form()
        kwargs = form.build_kwargs()
        if kwargs is None:
            self._show_status(False, self.tr(ERROR_MESSAGES[submit_task.ERROR_INVALID_INPUT]))
            return

        analysis_type = self._current_analysis_type()
        # Snapshot what is being submitted. ``build_kwargs`` stays a pure API
        # payload, so this is a copy rather than a reference the form could reuse.
        self._submit_request = dict(kwargs)
        self._submit_type = analysis_type

        self.submit_button.setEnabled(False)
        self.progress.setVisible(True)
        self.status_label.setText(self.tr("Submitting…"))
        self.status_label.setObjectName("HintLabel")
        self._refresh_style(self.status_label)

        worker = SubmitAnalysisWorker(analysis_type, kwargs, parent=self)
        worker.finished_signal.connect(self._on_submit_finished)
        # Collect the thread object once the OS thread has fully stopped, so
        # finished workers don't pile up as child objects of this panel.
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def teardown(self) -> None:
        """Detach in-flight workers before this panel is destroyed."""
        self._preview_timer.stop()
        # 見積もりは投げっぱなしになりうるので、投入と同じ手順で必ず切り離す。
        # 残したまま panel が消えると、応答時に破棄済みオブジェクトへ配送される
        self._detach_preview_worker()

        worker = self._worker
        self._worker = None
        if worker is not None:
            try:
                worker.finished_signal.disconnect(self._on_submit_finished)
            except (TypeError, RuntimeError):
                pass
            if worker.isRunning():
                detach_worker(worker)

    def _on_submit_finished(self, ok: bool, payload: str) -> None:
        # Disconnect so this (now finished) worker can never re-enter the
        # handler; the next submit gets a fresh worker and a fresh connection.
        worker = self._worker
        self._worker = None
        if worker is not None:
            try:
                worker.finished_signal.disconnect(self._on_submit_finished)
            except (TypeError, RuntimeError):
                pass

        self.progress.setVisible(False)
        self.submit_button.setEnabled(True)

        if ok:
            job_id = payload
            # Use the snapshot taken at submit time, not the form's current
            # state: the user may have switched analysis type while the request
            # was in flight, which would otherwise mislabel the job for good.
            analysis_type = self._submit_type
            request = self._submit_request
            QApplication.clipboard().setText(job_id)
            self._show_status(True, self.tr(f"Submitted: {job_id} (copied to clipboard)"))
            self.iface.messageBar().pushMessage(
                "SateAIs",
                self.tr(f"Job submitted — ID {job_id} copied to clipboard."),
                level=Qgis.MessageLevel.Success,
                duration=6,
            )
            self._current_form().clear()
            # clear() が inputs_changed を出すので見積もりは自動で消えるが、
            # 依存させず明示的に落とす
            self._drop_preview()
            self.job_submitted.emit(job_id, analysis_type, request)
        else:
            message = ERROR_MESSAGES.get(payload, ERROR_MESSAGES[submit_task.ERROR_SERVER_ERROR])
            self._show_status(False, self.tr(message))

    def _show_status(self, ok: bool, msg: str) -> None:
        self.status_label.setText(msg)
        self.status_label.setObjectName("StatusOk" if ok else "StatusError")
        self._refresh_style(self.status_label)

    def _clear_status(self) -> None:
        self.status_label.setText("")
        self.status_label.setObjectName("HintLabel")
        self._refresh_style(self.status_label)

    @staticmethod
    def _refresh_style(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("AnalysisPanel", message)
