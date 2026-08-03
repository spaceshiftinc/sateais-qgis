"""A single tracked-job row in the Jobs tab."""

from __future__ import annotations

from qgis.PyQt.QtCore import QCoreApplication, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QCursor
from qgis.PyQt.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core import job_summary
from ...core.job_tracker import TrackedJob
from .loading_indicator import OrbitingSatellite

_STATUS_LABEL = {
    "pending": "Pending",
    "processing": "Processing",
    "completed": "Completed",
    "failed": "Failed",
    "unknown": "Unknown",
}

# How long the "just completed" glow stays on a card, in ms.
_PULSE_MS = 650

# The first UUID segment is enough to recognise a job at a glance (the layer
# names and the poll-abandoned notice already use it), and the full id stays one
# Copy ID click — or one hover — away. Showing it in full wrapped the meta line
# onto a second row at the default dock width.
_SHORT_ID_CHARS = 8


class JobCard(QFrame):
    """One Job entry: badge, metadata, action buttons. Clicking the card body
    requests an AOI preview on the map (when a polygon was stored)."""

    aoi_preview_requested = pyqtSignal(str, str)  # (job_id, polygon_wkt)
    load_requested = pyqtSignal(str)  # job_id
    remove_requested = pyqtSignal(str)  # job_id
    id_copied = pyqtSignal(str)  # job_id

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
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(8)

        self.type_label = QLabel(job_summary.format_analysis_label(self._job.analysis_type))
        self.type_label.setObjectName("SectionLabel")
        # The type can come from the server (a synced endpoint_id), so never let
        # QLabel's rich-text auto-detection interpret it as markup.
        self.type_label.setTextFormat(Qt.TextFormat.PlainText)
        header.addWidget(self.type_label)

        self.status_badge = QLabel("")
        self.status_badge.setObjectName("StatusBadge")
        header.addWidget(self.status_badge)
        header.addStretch()

        outer.addLayout(header)

        # What was requested (period, or the scene for scene-id submissions).
        # Hidden entirely when unknown, so a job tracked before this existed
        # doesn't leave a blank gap in the card.
        self.request_label = QLabel("")
        self.request_label.setObjectName("SubtitleLabel")
        self.request_label.setTextFormat(Qt.TextFormat.PlainText)
        self.request_label.setWordWrap(True)
        outer.addWidget(self.request_label)

        self.meta_label = QLabel("")
        self.meta_label.setObjectName("HintLabel")
        self.meta_label.setWordWrap(True)
        outer.addWidget(self.meta_label)

        self.error_label = QLabel("")
        self.error_label.setObjectName("StatusError")
        # Server-supplied text; same reasoning as the type label above.
        self.error_label.setTextFormat(Qt.TextFormat.PlainText)
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        outer.addWidget(self.error_label)

        actions = QHBoxLayout()
        actions.setSpacing(6)

        self.copy_id_button = QPushButton(self.tr("Copy ID"))
        self.copy_id_button.setObjectName("GhostButton")
        self.copy_id_button.clicked.connect(self._on_copy_id_clicked)
        actions.addWidget(self.copy_id_button)
        actions.addStretch()

        self.load_button = QPushButton(self.tr("Load on Map"))
        self.load_button.setObjectName("PrimaryButton")
        self.load_button.clicked.connect(self._on_load_clicked)
        self.load_button.setVisible(False)
        actions.addWidget(self.load_button)

        self.remove_button = QPushButton(self.tr("Remove"))
        self.remove_button.setObjectName("GhostButton")
        self.remove_button.clicked.connect(self._on_remove_clicked)
        actions.addWidget(self.remove_button)

        outer.addLayout(actions)

        # Loading indicator shown only while the result GeoJSON is being fetched
        # (S3 302 + parse + layer add): a small satellite orbiting Earth plus a
        # short caption. Lives inside the card (a widget subtree we own) — never
        # reparented into the QGIS message bar, which segfaults on macOS.
        self.loading_row = QWidget()
        loading_layout = QHBoxLayout(self.loading_row)
        loading_layout.setContentsMargins(0, 2, 0, 0)
        loading_layout.setSpacing(8)

        self.loading_spinner = OrbitingSatellite(size=20, parent=self.loading_row)
        loading_layout.addWidget(self.loading_spinner)

        self.loading_label = QLabel(self.tr("Fetching result…"))
        self.loading_label.setObjectName("HintLabel")
        loading_layout.addWidget(self.loading_label)
        loading_layout.addStretch()

        self.loading_row.setVisible(False)
        outer.addWidget(self.loading_row)

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

        self.load_button.setVisible(status == "completed")

        # Status transitions should also drop any leftover loading UI (e.g. the
        # user retried a job and it moved back to processing while the previous
        # fetch was still in flight).
        if status != "completed":
            self.set_loading(False)

        if status == "failed" and (error_code or error_message):
            text = error_message or error_code or self.tr("Job failed.")
            self.error_label.setText(text)
            self.error_label.setVisible(True)
        else:
            self.error_label.setVisible(False)

        # Celebrate the moment a job flips to completed. Not on the initial
        # build (where prior_status already equals the new status), only on a
        # real processing→completed transition from polling.
        if status == "completed" and prior_status != "completed":
            self._pulse()

    def set_detection_count(self, count: int) -> None:
        """Record how many features were found and surface it in the badge."""
        self._job.detection_count = count
        self._refresh_status_badge()

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

        self.meta_label.setText(
            f"{job_summary.format_submitted_at(self._job.submitted_at)}"
            f"  ·  {self._job.job_id[:_SHORT_ID_CHARS]}…"
        )
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

    def _refresh_status_badge(self) -> None:
        """Render the status badge, promoting a completed job to its find count."""
        status = self._job.status
        count = self._job.detection_count
        if status == "completed" and count is not None and count > 0:
            text = "✦ " + job_summary.format_detection_summary(self._job.analysis_type, count)
            obj = "StatusOk"
        elif status == "completed" and count == 0:
            text = "No detections"
            obj = "HintLabel"
        else:
            text = _STATUS_LABEL.get(status, status)
            obj = (
                "StatusOk"
                if status == "completed"
                else "StatusError"
                if status == "failed"
                else "HintLabel"
            )
        self.status_badge.setText(text)
        self.status_badge.setObjectName(obj)
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
        self.load_button.setEnabled(not loading)
        self.loading_row.setVisible(loading)
        if loading:
            self.loading_spinner.start()
        else:
            self.loading_spinner.stop()

    # --- mouse handling ------------------------------------------------------

    def mouseReleaseEvent(self, event):  # type: ignore[override]
        # Buttons capture their own clicks; this fires only when the card body
        # was clicked. Emit a preview request when we have geometry to show.
        if event.button() == Qt.MouseButton.LeftButton and self._job.polygon:
            self.aoi_preview_requested.emit(self._job.job_id, self._job.polygon)
        super().mouseReleaseEvent(event)

    # --- private handlers ----------------------------------------------------

    def _on_load_clicked(self) -> None:
        self.load_requested.emit(self._job.job_id)

    def _on_remove_clicked(self) -> None:
        self.remove_requested.emit(self._job.job_id)

    def _on_copy_id_clicked(self) -> None:
        QApplication.clipboard().setText(self._job.job_id)
        self.id_copied.emit(self._job.job_id)

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("JobCard", message)
