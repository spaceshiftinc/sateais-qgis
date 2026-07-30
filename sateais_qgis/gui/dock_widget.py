"""Right-side dock widget hosting the Analyze and Jobs tabs."""

from __future__ import annotations

import contextlib

from qgis.core import Qgis
from qgis.gui import QgsMessageBarItem
from qgis.PyQt.QtCore import QCoreApplication, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QDockWidget, QTabWidget, QVBoxLayout, QWidget

from .styles import COSMIC_STYLESHEET
from .widgets.analysis_panel import AnalysisPanel
from .widgets.aoi_preview import AoiPreview
from .widgets.jobs_panel import JobsPanel
from .widgets.polygon_picker import PolygonPicker

# `_previewed_job_id` is a job_id string when a Jobs-tab card's AOI is shown.
# Between a Pick-on-Map completion and its Submit, we use this sentinel so the
# overlay is treated as an "in-flight AOI" that survives until the job is
# actually submitted (then transfers to that job_id).
_PENDING_JOB_ID = "__pending__"


class SateAIsDockWidget(QDockWidget):
    """Dock widget exposing the SateAIs detection workflow."""

    settings_requested = pyqtSignal()  # welcome-page CTA → plugin opens the auth dialog

    def __init__(self, iface, parent: QWidget | None = None) -> None:
        super().__init__("SateAIs", parent)
        self.iface = iface
        self.setObjectName("SateAIsDockWidget")
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )

        self._polygon_picker: PolygonPicker | None = None
        self._previous_map_tool = None
        self._pick_message_item: QgsMessageBarItem | None = None
        self._aoi_preview = AoiPreview(iface.mapCanvas())
        # The job id whose AOI is currently rendered, or None.
        self._previewed_job_id: str | None = None

        content = QWidget()
        content.setObjectName("SateAIsDockContent")
        content.setStyleSheet(COSMIC_STYLESHEET)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tabs = QTabWidget(content)
        self.analysis_panel = AnalysisPanel(iface, parent=self.tabs)
        self.jobs_panel = JobsPanel(iface, parent=self.tabs)
        self.tabs.addTab(self.analysis_panel, self.tr("Analysis"))
        self.tabs.addTab(self.jobs_panel, self.tr("Jobs"))
        layout.addWidget(self.tabs)

        self.analysis_panel.polygon_picker_requested.connect(self._start_polygon_pick)
        self.analysis_panel.job_submitted.connect(self._on_job_submitted)
        self.analysis_panel.settings_requested.connect(self.settings_requested)
        self.jobs_panel.aoi_preview_requested.connect(self._on_aoi_preview)
        self.jobs_panel.aoi_preview_unavailable.connect(self._on_aoi_preview_unavailable)
        self.jobs_panel.job_removed.connect(self._on_job_removed)
        self.jobs_panel.result_loaded.connect(self._on_result_loaded)
        self.jobs_panel.start_analysis_requested.connect(self._on_start_analysis)

        self.setWidget(content)

    # --- lifecycle -----------------------------------------------------------

    def teardown(self) -> None:
        """Release map-canvas resources. Called from the plugin's unload()."""
        # Stop any in-flight worker threads first: destroying a panel (and its
        # child QThreads) while one is still running aborts the process.
        self.analysis_panel.teardown()
        self.jobs_panel.teardown()
        self._aoi_preview.dispose()
        self._previewed_job_id = None

    def refresh_auth_state(self) -> None:
        """Re-evaluate the API-key state (welcome page vs submit form)."""
        self.analysis_panel.refresh_auth_state()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.teardown()
        super().closeEvent(event)

    # --- polygon picker integration -----------------------------------------

    def _start_polygon_pick(self) -> None:
        canvas = self.iface.mapCanvas()
        self._previous_map_tool = canvas.mapTool()
        self._polygon_picker = PolygonPicker(canvas)
        self._polygon_picker.polygon_finished.connect(self._on_polygon_finished)
        self._polygon_picker.polygon_cancelled.connect(self._on_polygon_cancelled)
        self._polygon_picker.area_changed.connect(self._on_pick_area_changed)
        canvas.setMapTool(self._polygon_picker)

        self._dismiss_pick_message()
        self._pick_message_item = self.iface.messageBar().createMessage(
            "SateAIs",
            self.tr("Drag a rectangle on the map (press, drag, release). Esc to cancel."),
        )
        self.iface.messageBar().pushWidget(self._pick_message_item, Qgis.MessageLevel.Info)

        self.analysis_panel.set_pick_in_progress(True)

    def _on_pick_area_changed(self, area_km2: float) -> None:
        """Live-update the pick prompt with the box's area as the user drags."""
        if self._pick_message_item is None:
            return
        try:
            self._pick_message_item.setText(
                self.tr(
                    f"Selecting {_format_area_km2(area_km2)} — release to confirm, Esc to cancel."
                )
            )
        except RuntimeError:
            # The message item was dismissed underneath us; ignore.
            self._pick_message_item = None

    def _on_polygon_finished(self, wkt: str, area_km2: float) -> None:
        self.analysis_panel.set_polygon(wkt, area_km2)
        self.analysis_panel.set_pick_in_progress(False)
        self._dismiss_pick_message()
        self._restore_map_tool()
        # Keep the polygon visible on the canvas so users can see what they
        # selected before submitting. Don't zoom — they were already looking at
        # the right place when they drew it.
        if self._aoi_preview.show_polygon(wkt, zoom_to_fit=False):
            self._previewed_job_id = _PENDING_JOB_ID

    def _on_polygon_cancelled(self) -> None:
        self.analysis_panel.set_pick_in_progress(False)
        self._dismiss_pick_message()
        self._restore_map_tool()
        # Drop the in-flight overlay if the user hits Escape.
        if self._previewed_job_id == _PENDING_JOB_ID:
            self._aoi_preview.clear()
            self._previewed_job_id = None

    def _dismiss_pick_message(self) -> None:
        if self._pick_message_item is not None:
            with contextlib.suppress(Exception):
                self.iface.messageBar().popWidget(self._pick_message_item)
            self._pick_message_item = None

    def _restore_map_tool(self) -> None:
        canvas = self.iface.mapCanvas()
        if self._previous_map_tool is not None:
            canvas.setMapTool(self._previous_map_tool)
            self._previous_map_tool = None

    # --- job hand-off --------------------------------------------------------

    def _on_job_submitted(self, job_id: str, analysis_type: str, request) -> None:
        self.jobs_panel.add_job(job_id, analysis_type, request)
        self.tabs.setCurrentWidget(self.jobs_panel)
        # If the just-submitted job owns the currently-shown "pending" AOI,
        # promote it to belong to this job_id so clicking the job card later
        # toggles the same overlay.
        if self._previewed_job_id == _PENDING_JOB_ID:
            self._previewed_job_id = job_id

    def _on_aoi_preview(self, job_id: str, polygon_wkt: str) -> None:
        # Toggle: clicking the same card again hides the AOI.
        if self._previewed_job_id == job_id:
            self._aoi_preview.clear()
            self._previewed_job_id = None
            return

        ok = self._aoi_preview.show_polygon(polygon_wkt)
        if not ok:
            self.iface.messageBar().pushMessage(
                "SateAIs",
                self.tr("Could not preview the AOI for this job."),
                level=Qgis.MessageLevel.Warning,
                duration=4,
            )
            return
        self._previewed_job_id = job_id

    def _on_aoi_preview_unavailable(self, _job_id: str) -> None:
        self.iface.messageBar().pushMessage(
            "SateAIs",
            self.tr("This job was submitted with a scene ID — no AOI to preview."),
            level=Qgis.MessageLevel.Info,
            duration=4,
        )

    def _on_job_removed(self, job_id: str) -> None:
        # Drop the on-map AOI overlay if it belonged to the removed job.
        if self._previewed_job_id == job_id:
            self._aoi_preview.clear()
            self._previewed_job_id = None

    def _on_result_loaded(self, job_id: str) -> None:
        # The result load added the AOI as a real (toggleable) layer; drop the
        # rubber-band preview, which always draws on top and cannot be toggled.
        if self._previewed_job_id == job_id:
            self._aoi_preview.clear()
            self._previewed_job_id = None

    def _on_start_analysis(self) -> None:
        # Empty-state CTA in the Jobs tab: jump the user to the Analysis tab.
        self.tabs.setCurrentWidget(self.analysis_panel)

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("SateAIsDockWidget", message)


def _format_area_km2(area_km2: float) -> str:
    """Human-friendly area string: more precision for tiny boxes."""
    if area_km2 < 1:
        return f"{area_km2:.3f} km²"
    if area_km2 < 100:
        return f"{area_km2:,.1f} km²"
    return f"{area_km2:,.0f} km²"
