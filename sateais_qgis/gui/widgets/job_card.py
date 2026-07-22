"""A single tracked-job row in the Jobs tab."""

from __future__ import annotations

from datetime import datetime, timezone

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

from ...core.job_tracker import TrackedJob
from .loading_indicator import OrbitingSatellite

_STATUS_LABEL = {
    "pending": "Pending",
    "processing": "Processing",
    "completed": "Completed",
    "failed": "Failed",
    "unknown": "Unknown",
}

# Human-readable (singular, plural) nouns per analysis type, so a completed job
# reads "23 ships" / "1 change" rather than a bare count. Shared with the
# Jobs-panel success toast.
_DETECTION_NOUN = {
    "ship": ("ship", "ships"),
    "oilslick": ("oil slick", "oil slicks"),
    "newbuilding": ("new building", "new buildings"),
    "disappearbuilding": ("removed building", "removed buildings"),
    "timeseries": ("change", "changes"),
}

# How long the "just completed" glow stays on a card, in ms.
_PULSE_MS = 650


def format_detection_summary(analysis_type: str, count: int) -> str:
    """Return e.g. ``"23 ships"`` / ``"1 change"`` / ``"12 detections"``."""
    singular, plural = _DETECTION_NOUN.get(analysis_type, ("detection", "detections"))
    return f"{count} {singular if count == 1 else plural}"


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
        self.set_status(job.status, job.error_code, job.error_message)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(8)

        self.type_label = QLabel(self._job.analysis_type)
        self.type_label.setObjectName("SectionLabel")
        header.addWidget(self.type_label)

        self.status_badge = QLabel("")
        self.status_badge.setObjectName("StatusBadge")
        header.addWidget(self.status_badge)
        header.addStretch()

        outer.addLayout(header)

        date_text = _format_datetime(self._job.submitted_at)
        meta = QLabel(f"{date_text}  ·  {self._job.job_id}")
        meta.setObjectName("HintLabel")
        meta.setWordWrap(True)
        outer.addWidget(meta)

        self.error_label = QLabel("")
        self.error_label.setObjectName("StatusError")
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

    def _refresh_status_badge(self) -> None:
        """Render the status badge, promoting a completed job to its find count."""
        status = self._job.status
        count = self._job.detection_count
        if status == "completed" and count is not None and count > 0:
            text = "✦ " + format_detection_summary(self._job.analysis_type, count)
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


def _format_datetime(iso_ts: str) -> str:
    """Render submitted-at as 'YYYY-MM-DD HH:MM (5m ago)' in local time."""
    if not iso_ts:
        return ""
    try:
        ts = datetime.fromisoformat(iso_ts)
    except ValueError:
        return iso_ts
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    local = ts.astimezone()
    absolute = local.strftime("%Y-%m-%d %H:%M")
    relative = _format_relative(datetime.now(timezone.utc) - ts)
    return f"{absolute} ({relative})"


def _format_relative(delta) -> str:
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"
