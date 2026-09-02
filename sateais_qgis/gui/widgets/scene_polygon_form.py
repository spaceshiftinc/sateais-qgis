"""Form for analysis types that accept scene_id XOR polygon+date (ship, oilslick)."""

from __future__ import annotations

from typing import Any

from qgis.PyQt.QtCore import QCoreApplication, QDate, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

ORBIT_OPTIONS = [("Any", None), ("Ascending", "ascending"), ("Descending", "descending")]
DATE_DIRECTION_OPTIONS = [
    ("Nearest", None),
    ("Before only", "before"),
    ("After only", "after"),
]


class ScenePolygonForm(QWidget):
    """Form with two mutually exclusive input modes: Scene ID or Polygon + Date."""

    polygon_picker_requested = pyqtSignal()
    # 入力が変われば見積もりも変わる。パネルがこれを受けて preview を投げ直す
    inputs_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Mode selector
        mode_row = QHBoxLayout()
        mode_row.setSpacing(16)
        self.scene_radio = QRadioButton(self.tr("Scene ID"))
        self.area_radio = QRadioButton(self.tr("Area"))
        # 地図から AOI を切り出すユーザーが大半なので Area を初期選択。
        # Scene ID は分かっている場合のみ切り替える運用。
        self.area_radio.setChecked(True)
        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self.scene_radio, 0)
        self._mode_group.addButton(self.area_radio, 1)
        self._mode_group.idToggled.connect(self._on_mode_changed)
        mode_row.addWidget(QLabel(self.tr("Input:")))
        mode_row.addWidget(self.scene_radio)
        mode_row.addWidget(self.area_radio)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        # Stacked: Scene ID form / Polygon + Date form
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_scene_widget())
        self._stack.addWidget(self._build_area_widget())
        layout.addWidget(self._stack)
        # ``area_radio.setChecked(True)`` above ran before this stack existed and
        # before ``idToggled`` was connected, so no toggle fired to reveal the
        # Area page (which holds the Pick on Map button). Sync the stack to the
        # initially-checked radio explicitly so it matches from the first paint.
        self._stack.setCurrentIndex(self._mode_group.checkedId())

        # Optional settings (common to both modes)
        layout.addWidget(self._section_label(self.tr("Optional")))
        opt_row = QHBoxLayout()
        opt_row.setSpacing(8)
        opt_row.addWidget(QLabel(self.tr("Orbit:")))
        self.orbit_combo = self._enum_combo(ORBIT_OPTIONS)
        opt_row.addWidget(self.orbit_combo, 1)
        opt_row.addWidget(QLabel(self.tr("Date pick:")))
        self.date_dir_combo = self._enum_combo(DATE_DIRECTION_OPTIONS)
        opt_row.addWidget(self.date_dir_combo, 1)
        layout.addLayout(opt_row)

        for signal in (
            self.scene_id_edit.textChanged,
            self.polygon_edit.textChanged,
            self.date_edit.dateChanged,
            self.orbit_combo.currentIndexChanged,
            self.date_dir_combo.currentIndexChanged,
            self._mode_group.idToggled,
        ):
            signal.connect(lambda *_: self.inputs_changed.emit())

    def _build_scene_widget(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        v.addWidget(self._section_label(self.tr("Scene ID")))
        self.scene_id_edit = QLineEdit()
        self.scene_id_edit.setPlaceholderText("S1A_IW_GRDH_...")
        v.addWidget(self.scene_id_edit)
        return w

    def _build_area_widget(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        polygon_row = QHBoxLayout()
        polygon_row.setSpacing(8)
        polygon_row.addWidget(self._section_label(self.tr("Polygon (EPSG:4326)")), 1)
        self.pick_button = QPushButton(self.tr("Pick on Map"))
        self.pick_button.clicked.connect(self.polygon_picker_requested.emit)
        polygon_row.addWidget(self.pick_button)
        v.addLayout(polygon_row)

        self.polygon_edit = QLineEdit()
        self.polygon_edit.setPlaceholderText("POLYGON((lon lat, ...))")
        v.addWidget(self.polygon_edit)

        self.area_label = QLabel(self.tr("Area: -- km²"))
        self.area_label.setObjectName("HintLabel")
        v.addWidget(self.area_label)

        v.addWidget(self._section_label(self.tr("Date")))
        self.date_edit = QDateEdit()
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        v.addWidget(self.date_edit)

        return w

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionLabel")
        return label

    def _enum_combo(self, options: list[tuple[str, Any]]) -> QComboBox:
        combo = QComboBox()
        for label, value in options:
            combo.addItem(label, value)
        return combo

    def _on_mode_changed(self, button_id: int, checked: bool) -> None:
        if checked:
            self._stack.setCurrentIndex(button_id)

    # --- public API ----------------------------------------------------------

    def set_polygon(self, wkt: str, area_km2: float) -> None:
        """Populate the polygon field from the map picker and switch to Area mode."""
        self.area_radio.setChecked(True)
        self.polygon_edit.setText(wkt)
        self.area_label.setText(self.tr(f"Area: {area_km2:.2f} km²"))

    def build_kwargs(self) -> dict[str, Any] | None:
        """Return kwargs for ``client.analyze.<type>(**kwargs)`` or None if invalid."""
        kwargs: dict[str, Any] = {}
        if self.scene_radio.isChecked():
            scene_id = self.scene_id_edit.text().strip()
            if not scene_id:
                return None
            kwargs["scene_id"] = scene_id
        else:
            polygon = self.polygon_edit.text().strip()
            if not polygon:
                return None
            kwargs["polygon"] = polygon
            kwargs["date"] = self.date_edit.date().toString("yyyy-MM-dd")

        orbit = self.orbit_combo.currentData()
        if orbit:
            kwargs["orbit_direction"] = orbit
        date_dir = self.date_dir_combo.currentData()
        if date_dir:
            kwargs["date_direction"] = date_dir
        return kwargs

    def clear(self) -> None:
        self.scene_id_edit.clear()
        self.polygon_edit.clear()
        self.area_label.setText(self.tr("Area: -- km²"))
        self.date_edit.setDate(QDate.currentDate())
        self.orbit_combo.setCurrentIndex(0)
        self.date_dir_combo.setCurrentIndex(0)
        # 初期選択と揃える (Area).
        self.area_radio.setChecked(True)

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("ScenePolygonForm", message)
