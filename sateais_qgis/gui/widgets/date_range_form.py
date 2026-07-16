"""Form for analysis types that require polygon + date_start + date_end.

Used by newbuilding, disappearbuilding, and timeseries detections.
"""

from __future__ import annotations

from typing import Any

from qgis.PyQt.QtCore import QCoreApplication, QDate, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

ORBIT_OPTIONS = [("Any", None), ("Ascending", "ascending"), ("Descending", "descending")]


class DateRangeForm(QWidget):
    """Form with required polygon + date_start + date_end + optional orbit."""

    polygon_picker_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        polygon_row = QHBoxLayout()
        polygon_row.setSpacing(8)
        polygon_row.addWidget(self._section_label(self.tr("Polygon (EPSG:4326)")), 1)
        self.pick_button = QPushButton(self.tr("Pick on Map"))
        self.pick_button.clicked.connect(self.polygon_picker_requested.emit)
        polygon_row.addWidget(self.pick_button)
        layout.addLayout(polygon_row)

        self.polygon_edit = QLineEdit()
        self.polygon_edit.setPlaceholderText("POLYGON((lon lat, ...))")
        layout.addWidget(self.polygon_edit)

        self.area_label = QLabel(self.tr("Area: -- km²"))
        self.area_label.setObjectName("HintLabel")
        layout.addWidget(self.area_label)

        # Date range
        layout.addWidget(self._section_label(self.tr("Date Range")))
        date_row = QHBoxLayout()
        date_row.setSpacing(8)

        self.date_start_edit = QDateEdit()
        self.date_start_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_start_edit.setCalendarPopup(True)
        self.date_start_edit.setDate(QDate.currentDate().addMonths(-6))
        date_row.addWidget(QLabel(self.tr("Start:")))
        date_row.addWidget(self.date_start_edit, 1)

        self.date_end_edit = QDateEdit()
        self.date_end_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_end_edit.setCalendarPopup(True)
        self.date_end_edit.setDate(QDate.currentDate())
        date_row.addWidget(QLabel(self.tr("End:")))
        date_row.addWidget(self.date_end_edit, 1)

        layout.addLayout(date_row)

        # Optional orbit direction
        layout.addWidget(self._section_label(self.tr("Optional")))
        opt_row = QHBoxLayout()
        opt_row.setSpacing(8)
        opt_row.addWidget(QLabel(self.tr("Orbit:")))
        self.orbit_combo = QComboBox()
        for label, value in ORBIT_OPTIONS:
            self.orbit_combo.addItem(label, value)
        opt_row.addWidget(self.orbit_combo, 1)
        layout.addLayout(opt_row)

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionLabel")
        return label

    # --- public API ----------------------------------------------------------

    def set_polygon(self, wkt: str, area_km2: float) -> None:
        self.polygon_edit.setText(wkt)
        self.area_label.setText(self.tr(f"Area: {area_km2:.2f} km²"))

    def build_kwargs(self) -> dict[str, Any] | None:
        polygon = self.polygon_edit.text().strip()
        if not polygon:
            return None
        kwargs: dict[str, Any] = {
            "polygon": polygon,
            "date_start": self.date_start_edit.date().toString("yyyy-MM-dd"),
            "date_end": self.date_end_edit.date().toString("yyyy-MM-dd"),
        }
        orbit = self.orbit_combo.currentData()
        if orbit:
            kwargs["orbit_direction"] = orbit
        return kwargs

    def clear(self) -> None:
        self.polygon_edit.clear()
        self.area_label.setText(self.tr("Area: -- km²"))
        self.date_start_edit.setDate(QDate.currentDate().addMonths(-6))
        self.date_end_edit.setDate(QDate.currentDate())
        self.orbit_combo.setCurrentIndex(0)

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("DateRangeForm", message)
