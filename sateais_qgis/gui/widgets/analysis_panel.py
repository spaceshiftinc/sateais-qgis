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
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...core import client_factory
from ...core.api.types import Preview
from ...workers import submit_task
from ...workers.lifecycle import detach_worker
from ...workers.preview_task import PreviewWorker
from ...workers.submit_task import SubmitAnalysisWorker
from ..auth_dialog import SIGNUP_URL
from .balance_footer import BalanceFooter
from .estimate_card import EstimateCard
from .setup_card import SetupCard

# 入力を打っている最中に投げない。止まってから見積もる
PREVIEW_DEBOUNCE_MS = 600

ERROR_MESSAGES: dict[str, str] = {
    submit_task.ERROR_AUTH_NOT_CONFIGURED: "Please register an API key first.",
    submit_task.ERROR_AUTH_FAILED: "Invalid API key. Please check your settings.",
    submit_task.ERROR_PERMISSION_DENIED: (
        "This analysis is not enabled for your account. Please request access from the console."
    ),
    submit_task.ERROR_INSUFFICIENT_CREDITS: ("Insufficient credits. Please top up in the console."),
    submit_task.ERROR_INVALID_INPUT: "Please fill in the required fields.",
    # 面積超過は wording.area_limit_reason が数値付きの文に差し替える。
    # ここに来るのは WKT 不正・期間の上限・入力パターン違反
    submit_task.ERROR_VALIDATION_FAILED: (
        "This request could not be run as written. Check the area and the dates."
    ),
    submit_task.ERROR_NOT_FOUND: (
        "The requested data was not found (no matching scene or polygon). "
        "Please adjust the area or date and try again."
    ),
    submit_task.ERROR_CONFLICT: (
        "The resource is not ready yet. Please wait a moment and try again."
    ),
    # 413 はアップロードサイズの上限 (polygon 1 GiB / geotiff 4 GiB)。面積の
    # 超過は 400 で返り wording.area_limit_reason が数値付きで説明するので、
    # ここで「範囲が広すぎる」と言うと誤った直し方へ誘導してしまう
    submit_task.ERROR_PAYLOAD_TOO_LARGE: "The request was too large for the server.",
    # 429 は同時ジョブ数の上限 (RATE_LIMIT_EXCEEDED)。「少し待って再試行」では
    # 直らない — 走っているジョブが終わるのを待つのが正しい次の一手
    submit_task.ERROR_RATE_LIMITED: (
        "You already have the maximum number of jobs running. "
        "Wait for one to finish, then submit again."
    ),
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
    # (要求範囲 WKT, 解析範囲 WKT | None, 画面をそこへ寄せるか)
    coverage_changed = pyqtSignal(str, object, bool)

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
        # 直前に地図へ描いた要求範囲。同じものを描き直すだけなら画面を動かさない
        self._shown_polygon = ""
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

        # 手順はカードが持つ。種別・日付・範囲が揃うまで、残りを一覧で見せる
        self.form = SetupCard(self)
        self.form.polygon_picker_requested.connect(self.polygon_picker_requested.emit)
        self.form.inputs_changed.connect(self._on_inputs_changed)
        outer.addWidget(self.form)

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

        # 「1.44 使う」の相方。幾ら持っていて、押した後に幾ら残るかを、
        # 押す前に読めるようにする。値はプレビュー応答に既に入っている
        outer.addStretch()
        self.balance_footer = BalanceFooter(self)
        outer.addWidget(self.balance_footer)
        return page

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionLabel")
        return label

    def _current_form(self):
        return self.form

    def _current_analysis_type(self) -> str | None:
        return self.form.analysis_type

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

    # --- pre-run estimate ----------------------------------------------------

    def _on_inputs_changed(self) -> None:
        """Inputs changed: drop the stale estimate and schedule a fresh one."""
        # 手順が揃うまでは投入させない。カードが残りを示している
        self.submit_button.setEnabled(self.form.is_complete())
        self._drop_preview()
        kwargs = self._current_form().build_kwargs()
        polygon = (kwargs or {}).get("polygon")
        # 打ち込まれた範囲は、いま見ている場所とは無関係なことがほとんどで、
        # 寄せないと「描いたのに何も出ない」に見える。地図で描いた場合は
        # 既にそこを見ているので動かさない。日付や種別を変えただけのときも同じ
        polygon = polygon or ""
        recenter = bool(polygon) and polygon != self._shown_polygon
        recenter = recenter and not self.form.polygon_from_map
        self._shown_polygon = polygon
        # scene_id 指定では解析範囲がシーンで決まるので、地図に重ねる要求範囲もない
        self.coverage_changed.emit(polygon, None, recenter)
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
        # 残高も見積もり応答から来た値。入力が変われば前の応答の数字であって、
        # 残したままだとエラー表示の下に無関係な数字が居座り続ける
        self.balance_footer.clear()

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
        # deleteLater は非同期。ここに来る前に Qt が壊していることがあるので、
        # 触る操作はまとめて RuntimeError を受ける
        try:
            worker.finished_signal.disconnect()
        except (TypeError, RuntimeError):
            pass
        try:
            if worker.isRunning():
                detach_worker(worker)
        except RuntimeError:
            pass

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
            lambda ok, payload, seq=seq, w=worker: self._on_preview_finished(ok, payload, seq, w)
        )
        worker.finished.connect(worker.deleteLater)
        self._preview_worker = worker
        worker.start()

    def _on_preview_finished(self, ok: bool, payload: Any, seq: int, worker: Any = None) -> None:
        # **終わった worker は必ず手放す。** seq が古いからと参照を残すと、Qt が
        # deleteLater で C++ 側を壊した後の殻を掴み続け、次に触った時点で
        # "wrapped C/C++ object ... has been deleted" で落ちる。
        # 誰を消すかは seq ではなく同一性で決める（新しい worker は消さない）
        if worker is not None and self._preview_worker is worker:
            self._preview_worker = None

        if seq != self._preview_seq:
            return  # 入力が変わった後に届いた応答。表示はしない

        if ok and isinstance(payload, Preview):
            self._preview_retried = False
            self.estimate_card.show_preview(payload)
            credits = payload.credits
            self.balance_footer.set_balance(
                credits.balance if credits else None,
                credits.estimated if credits else None,
            )
            coverage = payload.coverage.polygon if payload.coverage else None
            requested = (self._current_form().build_kwargs() or {}).get("polygon") or ""
            # 見積もりの応答で画面を動かさない。範囲は既に描かれている
            self.coverage_changed.emit(requested, coverage, False)
            return

        # 一度だけ聞き直す。コールドスタート直後は落ちても、二度目は返る
        if not self._preview_retried:
            self._preview_retried = True
            self._preview_timer.start()
            return
        # worker がせっかく分類したコードを捨てない。413 なら「範囲が広すぎる」と
        # 言えるのに、一律「取得できなかった」では次の一手が分からない
        # payload はエラーコードか、wording が組み立て済みの文のどちらか。
        # 表に無い文字列は後者なので、そのまま見せる（生のサーバ文面は届かない）
        if isinstance(payload, str):
            mapped = ERROR_MESSAGES.get(payload)
            reason = self.tr(mapped) if mapped else payload
        else:
            reason = ""
        self.estimate_card.show_failed(reason)

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
            # ID はジョブのカードに出ており、そこで選択してコピーできる。
            # 通知に 36 桁を並べる必要はなく、クリップボードを黙って
            # 書き換えるのは利用者が今持っているものを捨てることになる
            self._show_status(True, self.tr("Submitted."))
            self.iface.messageBar().pushMessage(
                "SateAIs",
                self.tr("Job submitted. It is now tracked in the Jobs tab."),
                level=Qgis.MessageLevel.Success,
                duration=5,
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
