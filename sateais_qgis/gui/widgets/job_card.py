"""A single tracked-job row in the Jobs tab."""

from __future__ import annotations

from html import escape

from qgis.PyQt.QtCore import QCoreApplication, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QCursor
from qgis.PyQt.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QWidget,
)

from ...core import job_summary, wording
from ...core.job_tracker import TrackedJob
from ..brand import spark
from ..icons import kind_icon
from .loading_indicator import OrbitingSatellite

# MCP のジョブ一覧と同じ表記。未知の状態もそのまま大文字で出す
_STATUS_LABEL = {
    "pending": "PENDING",
    "processing": "PROCESSING",
    "completed": "COMPLETED",
    "failed": "FAILED",
    "unknown": "UNKNOWN",
}

# How long the "just completed" glow stays on a card, in ms.
_PULSE_MS = 650


class JobCard(QFrame):
    """One Job entry: badge, metadata, action buttons. Clicking the card body
    requests an AOI preview on the map (when a polygon was stored)."""

    aoi_preview_requested = pyqtSignal(str, str)  # (job_id, polygon_wkt)
    load_requested = pyqtSignal(str)  # job_id

    def __init__(self, job: TrackedJob, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("JobCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._job = job
        if job.polygon:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._build_ui()
        self._refresh_request()
        self.set_status(job.status, job.error_code, job.error_message)

    def _build_ui(self) -> None:
        """Lay the row out as MCP does: a 3-column grid.

        ``auto | 1fr | auto`` — icon, name (the only column that stretches),
        status pill. That is what pins the pill to the right edge on every row;
        packing the three into a box with a spacer lets the pill drift with the
        length of the name. The meta line starts in column 2, clearing the icon.
        """
        grid = QGridLayout(self)
        grid.setContentsMargins(14, 12, 14, 12)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(5)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 0)

        self.type_icon = QLabel()
        self.type_icon.setPixmap(kind_icon(self._job.analysis_type, 16).pixmap(16, 16))
        self.type_icon.setFixedSize(16, 16)
        grid.addWidget(self.type_icon, 0, 0)

        self.type_label = QLabel(job_summary.format_analysis_label(self._job.analysis_type))
        self.type_label.setObjectName("JobTitle")
        # The type can come from the server (a synced endpoint_id), so never let
        # QLabel's rich-text auto-detection interpret it as markup.
        self.type_label.setTextFormat(Qt.TextFormat.PlainText)
        # Ignored にすると入れ子のレイアウトでは幅 0 まで潰れて名前が消える。
        # 縮められるが自然幅は主張する Preferred + 伸ばさない、が正しい
        self.type_label.setMinimumWidth(0)

        # 名前は縮む側。実測で "New building detection" は 138px あり、ドックの
        # 使える幅 291px では件数と状態の両方を横に並べられない
        self.type_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        grid.addWidget(self.type_label, 0, 1)

        # 1 行目 = 何を・幾つ。種別名のすぐ右に、間を空けて置く
        finds_row = QWidget()
        finds_layout = QHBoxLayout(finds_row)
        finds_layout.setContentsMargins(0, 0, 0, 0)
        finds_layout.setSpacing(5)
        # 閃光の有無で数字の左端が動かないよう、枠は常に確保する
        # （レイアウトは既定で隠した部品を詰めるので、明示的に場所を残す）
        self.find_spark = QLabel()
        self.find_spark.setPixmap(spark(height=11))
        spark_policy = self.find_spark.sizePolicy()
        spark_policy.setRetainSizeWhenHidden(True)
        self.find_spark.setSizePolicy(spark_policy)
        finds_layout.addWidget(self.find_spark)
        self.find_label = QLabel("")
        self.find_label.setObjectName("FindCount")
        finds_layout.addWidget(self.find_label)
        self.finds_row = finds_row
        self.finds_row.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.finds_row.setVisible(False)
        grid.addWidget(finds_row, 0, 2, Qt.AlignmentFlag.AlignRight)

        # 2 行目 = いつ・どの状態。1 行目と軸を分けることで、名前も件数も
        # 状態も省略せずに置ける
        self.request_label = QLabel("")
        self.request_label.setObjectName("SubtitleLabel")
        self.request_label.setTextFormat(Qt.TextFormat.PlainText)
        self.request_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        grid.addWidget(self.request_label, 1, 1)

        self.status_badge = QLabel("")
        self.status_badge.setObjectName("PillMuted")
        # 状態は常に読める必要がある。日付に押されて縮まないよう固定する
        self.status_badge.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        grid.addWidget(self.status_badge, 1, 2, Qt.AlignmentFlag.AlignRight)

        self.meta_label = QLabel("")
        self.meta_label.setObjectName("JobMeta")
        # 見出し付きなので 1 行には収まらない。折り返して全部見せる
        self.meta_label.setTextFormat(Qt.TextFormat.RichText)
        self.meta_label.setWordWrap(True)
        self.meta_label.setMinimumWidth(0)
        grid.addWidget(self.meta_label, 2, 1, 1, 2)

        # ID は 36 桁。数字の行に混ぜると読む値を押し出すので、独立した行に置き、
        # 一番弱い色にして「控えるときだけ見る」ものにする。選択してコピーできる
        self.id_label = QLabel("")
        self.id_label.setObjectName("JobId")
        self.id_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(self.id_label, 3, 1, 1, 2)

        self.error_label = QLabel("")
        self.error_label.setObjectName("StatusError")
        self.error_label.setTextFormat(Qt.TextFormat.PlainText)
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        grid.addWidget(self.error_label, 4, 1, 1, 2)

        self.loading_row = QWidget()
        loading = QHBoxLayout(self.loading_row)
        loading.setContentsMargins(0, 2, 0, 0)
        loading.setSpacing(8)
        self.loading_spinner = OrbitingSatellite(size=18, parent=self.loading_row)
        loading.addWidget(self.loading_spinner)
        self.loading_label = QLabel(self.tr("Fetching result…"))
        self.loading_label.setObjectName("HintLabel")
        loading.addWidget(self.loading_label)
        loading.addStretch()
        self.loading_row.setVisible(False)
        grid.addWidget(self.loading_row, 5, 1, 1, 2)

    # --- public API ----------------------------------------------------------

    @property
    def job_id(self) -> str:
        return self._job.job_id

    @property
    def job(self) -> TrackedJob:
        return self._job

    def set_status(
        self,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        prior_status = self._job.status
        self._job.status = status
        self._job.error_code = error_code
        self._job.error_message = error_message

        self._refresh_status_badge()

        # Status transitions should also drop any leftover loading UI (e.g. the
        # user retried a job and it moved back to processing while the previous
        # fetch was still in flight).
        if status != "completed":
            self.set_loading(False)

        if status == "failed" and (error_code or error_message):
            # サーバの原文もコードもそのままは出さない。内部の実装都合が混ざり、
            # 次に何をすればよいかも伝わらない（core.wording の説明を参照）
            self.error_label.setText(wording.failure_label(error_code, error_message))
            self.error_label.setVisible(True)
        else:
            self.error_label.setVisible(False)

        # Celebrate the moment a job flips to completed. Not on the initial
        # build (where prior_status already equals the new status), only on a
        # real processing→completed transition from polling.
        if status == "completed" and prior_status != "completed":
            self._pulse()

    def _refresh_finds(self) -> None:
        """State the outcome in words: what was counted, and how many."""
        count = self._job.detection_count
        known = self._job.status == "completed" and count is not None
        self.finds_row.setVisible(known)
        if not known:
            return
        # 閃光は「見つかった」ときの印。ゼロに付けると意味が薄れる
        self.find_spark.setVisible(bool(count))
        # 種別名がすぐ左にあるので名詞は繰り返さない。長い形はツールチップへ
        self.find_label.setText(job_summary.format_detection_count(count))
        self.find_label.setToolTip(
            job_summary.format_detection_outcome(self._job.analysis_type, count)
        )
        # 何も無かったのも結果。見つかったときの緑とは別の重さで置く
        self.find_label.setObjectName("FindCount" if count else "HintLabel")
        self.find_label.style().unpolish(self.find_label)
        self.find_label.style().polish(self.find_label)

    def set_detection_count(self, count: int) -> None:
        """Record how many features were found and surface it next to the name."""
        self._job.detection_count = count
        self._refresh_finds()

    def apply_request_context(self, job: TrackedJob) -> None:
        """Adopt request details resolved after the card was built (i.e. by Sync)."""
        for field in ("scene_id", "date", "date_start", "date_end", "request_source", "polygon"):
            setattr(self._job, field, getattr(job, field))
        self._refresh_request()
        # A backfilled polygon makes the card clickable for the first time.
        if self._job.polygon:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def _refresh_request(self) -> None:
        """Render the request line and the full-detail tooltip."""
        summary = job_summary.build_request_summary(self._job)
        self.request_label.setText(summary)
        self.request_label.setVisible(bool(summary))

        # 値には必ず見出しを付ける。単位だけでは「3m 31s」が待ち時間なのか
        # 実行時間なのか、「1.96」が使った分なのか残りなのかが読めない
        fields = wording.job_meta_fields(
            job_summary.format_submitted_short(self._job.submitted_at),
            self._job.area_sqkm,
            self._job.credits_used,
            wording.took_label(self._job.submitted_at, self._job.completed_at),
        )
        self.meta_label.setText(self._meta_markup(fields))
        self.meta_label.setVisible(bool(fields))
        # ID は控えるための値。省略すると写せず、目立たせる必要もない
        self.id_label.setText(self._job.job_id)
        self._refresh_finds()
        # Escape rather than trust: tooltips have no setTextFormat, and Qt decides
        # rich vs plain by sniffing the string. Today's tooltip always starts with
        # plain text so it renders as plain, but that would flip if a value ever
        # led with markup — convertFromPlainText makes the docstring's promise real.
        # WhiteSpaceNormal is passed explicitly: PyQt defaults to WhiteSpacePre,
        # which turns every space into &nbsp; and stops the tooltip from wrapping.
        self.setToolTip(
            Qt.convertFromPlainText(
                job_summary.build_request_tooltip(self._job),
                Qt.WhiteSpaceMode.WhiteSpaceNormal,
            )
        )

    @staticmethod
    def _meta_markup(fields: list[tuple[str, str]]) -> str:
        """Captions one step back from their values, so the figures still lead.

        Every space inside a pair is non-breaking: the line wraps in the dock, and
        a plain space let it break as "Cost 1.96 / credits", which reads as two
        different values. The only breakable space is the one between pairs.
        """
        pairs = [
            f'<span style="color:#5A6771">{escape(label)}</span>&nbsp;'
            f'<span style="color:#A9B7C2">{escape(value).replace(" ", "&nbsp;")}</span>'
            for label, value in fields
        ]
        return "&nbsp;&nbsp; ".join(pairs)

    def _refresh_status_badge(self) -> None:
        """Render the status pill.

        **状態は常にここに出す。** 以前は完了時だけ件数に差し替えていたため、
        カードによって "Completed" だったり "7 new buildings" だったりして、
        同じ列が何を示すのか読めなかった。件数は数であってジョブの状態ではない
        ので、メタ行（日付・面積・クレジット…）の側に置く。
        """
        status = self._job.status
        self.status_badge.setText(_STATUS_LABEL.get(status, status.upper()))
        self.status_badge.setObjectName(
            "PillOk"
            if status == "completed"
            else "PillError"
            if status == "failed"
            else "PillMuted"
        )
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)

    def _pulse(self) -> None:
        """Briefly glow the card frame so a fresh completion is noticed."""
        self.setObjectName("JobCardPulse")
        self.style().unpolish(self)
        self.style().polish(self)
        QTimer.singleShot(_PULSE_MS, self._end_pulse)

    def _end_pulse(self) -> None:
        # The card may have been removed before the timer fired.
        try:
            self.setObjectName("JobCard")
            self.style().unpolish(self)
            self.style().polish(self)
        except RuntimeError:
            pass

    def set_loading(self, loading: bool) -> None:
        """Reflect an in-flight Load-on-Map fetch in the UI.

        Disables the Load button, reveals the orbiting-satellite indicator, and
        keeps the Copy ID / Remove buttons available so the card still feels
        alive. The animation timer is driven explicitly here (rather than only
        via show/hide events) so it never keeps ticking on a hidden card.
        """
        self.loading_row.setVisible(loading)
        self.loading_spinner.start() if loading else self.loading_spinner.stop()

    # --- mouse handling ------------------------------------------------------

    def mouseReleaseEvent(self, event):  # type: ignore[override]
        # カード自体が操作系。MCP のジョブ一覧と同じで、行を押すと地図が
        # そのジョブに切り替わる。完了していれば結果、まだなら要求範囲
        if event.button() == Qt.MouseButton.LeftButton:
            if self._job.status == "completed":
                self.load_requested.emit(self._job.job_id)
            elif self._job.polygon:
                self.aoi_preview_requested.emit(self._job.job_id, self._job.polygon)
        super().mouseReleaseEvent(event)

    # --- private handlers ----------------------------------------------------

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("JobCard", message)
