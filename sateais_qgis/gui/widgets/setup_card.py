"""The setup checklist: detection type, dates, area — in that order.

A direct port of the MCP map widget's setup card. The point is that the whole
remaining path is visible from the start: instead of pointing out one missing
field at a time after the user acts, the three steps are listed up front and
each row is also the control that fills it in.

Sizes follow the widget (``map.html`` ``.step`` / ``.stepbody``): a 19px
numbered circle, 13px row text, and the expanded body indented to clear the
circle.
"""

from __future__ import annotations

from typing import Any

from qgis.PyQt.QtCore import QCoreApplication, QDate, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core import job_summary
from ..icons import kind_icon, step_icon

ORBIT_OPTIONS: list[tuple[str, Any]] = [
    ("Any orbit", None),
    ("Ascending", "ascending"),
    ("Descending", "descending"),
]
DATE_DIRECTION_OPTIONS: list[tuple[str, Any]] = [
    ("Nearest", None),
    ("Before only", "before"),
    ("After only", "after"),
]

# 検出種別。並びも呼び名も MCP ウィジェットのメニューと同じ
ANALYSIS_TYPES = ["ship", "oilslick", "newbuilding", "disappearbuilding", "timeseries"]

# 期間を要求する検出。MCP の open_map が渡す `requires` と同じ割り方
PERIOD_TYPES = frozenset({"newbuilding", "disappearbuilding", "timeseries"})


def needs_period(analysis_type: str | None) -> bool:
    """True when the type compares two dates rather than picking one scene."""
    return analysis_type in PERIOD_TYPES


class _LinkLabel(QLabel):
    """A small inline action inside a step row.

    Its own click must not also reach the row: the row starts the map tool, so
    a bubbling "Clear" would delete the polygon and immediately start drawing.
    """

    clicked = pyqtSignal()

    def __init__(
        self,
        text: str,
        object_name: str = "StepAction",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName(object_name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # 押せる語が「Redra」と切れては押しようがない。狭い dock では
        # 先に畳むのは行の見出しのほうで、操作は常に読める幅を保つ
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

    def mouseReleaseEvent(self, event):  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _Segmented(QWidget):
    """A row of mutually exclusive choices in one bordered strip.

    The stacked "PICK THE SCENE" / "ORBIT" captions above their own combo boxes
    read like a generated form. MCP puts these as a single segmented strip
    (``.seg``) where the options are the label — shorter, and the current
    choice is visible without reading a caption.
    """

    changed = pyqtSignal()

    def __init__(self, options: list[tuple[str, Any]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Segmented")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self._buttons: list[QPushButton] = []
        for index, (label, value) in enumerate(options):
            button = QPushButton(label)
            button.setObjectName("SegButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setProperty("value", value)
            button.setProperty("first", index == 0)
            button.setProperty("last", index == len(options) - 1)
            button.setChecked(index == 0)
            button.clicked.connect(lambda _c=False, b=button: self._select(b))
            row.addWidget(button)
            self._buttons.append(button)
        row.addStretch()

    def _select(self, chosen: QPushButton) -> None:
        for button in self._buttons:
            button.setChecked(button is chosen)
        self.changed.emit()

    def value(self) -> Any:
        for button in self._buttons:
            if button.isChecked():
                return button.property("value")
        return None

    def reset(self) -> None:
        self._select(self._buttons[0])


class _StepRow(QFrame):
    """One checklist row: numbered circle, label, and the value once filled.

    A QFrame rather than a QPushButton: a button does not take its size from a
    child layout, so the rows collapsed and the expanded body drew over them.
    """

    clicked = pyqtSignal()

    def __init__(self, number: str, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StepRow")
        self._enabled = True
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(4, 6, 4, 6)
        row.setSpacing(8)

        self._number = number
        self.badge = QLabel(number)
        self.badge.setObjectName("StepBadge")
        self.badge.setFixedSize(19, 19)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.badge)

        # アイコンの有無で行がずれないよう、枠は常に同じ幅で確保する
        # （検出種別だけ絵が入るので、隠すとラベルの開始位置が食い違う）
        self.icon = QLabel()
        self.icon.setFixedSize(16, 16)
        row.addWidget(self.icon)

        self.label = QLabel(label)
        self.label.setObjectName("StepLabel")
        row.addWidget(self.label)
        row.addStretch()

        self.value = QLabel("")
        self.value.setObjectName("StepValue")
        row.addWidget(self.value)

        # 済んだ段をもう一度触れる操作。やり直しと取り消しは対なので横に並べる。
        # 区切り記号は置かない: 青と灰で既に別物と読め、dock の狭い幅では
        # その 1 文字が「Redraw」を切る側に回る
        self.actions = QWidget()
        actions = QHBoxLayout(self.actions)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(10)
        self.action = _LinkLabel(self.tr("Redraw"))
        actions.addWidget(self.action)
        # 消す操作は青くしない。並んだ二つのうち、戻れないほうを目立たせない
        self.action2 = _LinkLabel(self.tr("Clear"), object_name="StepActionMuted")
        actions.addWidget(self.action2)
        # 縮むのは見出しの側。押す語が切れると押しようがなくなる
        self.actions.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.actions.setVisible(False)
        row.addWidget(self.actions)

    def set_done(self, done: bool) -> None:
        self.badge.setText("✓" if done else self._number)
        self.badge.setProperty("done", done)
        for widget in (self.badge, self):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def set_reachable(self, reachable: bool) -> None:
        self._enabled = reachable
        self.setProperty("dim", not reachable)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if reachable else Qt.CursorShape.ArrowCursor
        )
        for widget in (self, self.label, self.value):
            widget.setProperty("dim", not reachable)
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def mouseReleaseEvent(self, event):  # type: ignore[override]
        if self._enabled and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class SetupCard(QFrame):
    """Detection type, dates and area, laid out as the three steps to complete."""

    polygon_picker_requested = pyqtSignal()
    inputs_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SetupCard")
        self._analysis_type: str | None = None
        # 地図で描いた範囲か、打ち込まれた範囲か。前者は画面を動かさない
        self._polygon_from_map = False
        self._open_step: str | None = "kind"
        self._build_ui()
        self._refresh()

    # --- construction --------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 14)
        outer.setSpacing(0)

        self.title = QLabel(self.tr("Set up the analysis"))
        self.title.setObjectName("SetupTitle")
        outer.addWidget(self.title)
        outer.addSpacing(6)

        # ① 検出種別
        self.kind_row = _StepRow("1", self.tr("Detection type"))
        self.kind_row.clicked.connect(lambda: self._toggle("kind"))
        outer.addWidget(self.kind_row)

        self.kind_body = QWidget()
        kind_body = QVBoxLayout(self.kind_body)
        kind_body.setContentsMargins(33, 2, 4, 10)
        kind_body.setSpacing(2)
        self._kind_buttons: dict[str, QPushButton] = {}
        for analysis_type in ANALYSIS_TYPES:
            option = QPushButton(job_summary.ANALYSIS_LABELS.get(analysis_type, analysis_type))
            option.setObjectName("StepOption")
            option.setFlat(True)
            option.setCursor(Qt.CursorShape.PointingHandCursor)
            option.setIcon(kind_icon(analysis_type, 16))
            option.clicked.connect(lambda _checked=False, t=analysis_type: self._choose_type(t))
            kind_body.addWidget(option)
            self._kind_buttons[analysis_type] = option
        outer.addWidget(self.kind_body)

        # ② 期間 / 基準日
        self.when_row = _StepRow("2", self.tr("Period"))
        self.when_row.clicked.connect(lambda: self._toggle("when"))
        outer.addWidget(self.when_row)

        self.when_body = QWidget()
        when_body = QVBoxLayout(self.when_body)
        when_body.setContentsMargins(33, 2, 4, 10)
        when_body.setSpacing(8)

        self.period_row = QWidget()
        period = QHBoxLayout(self.period_row)
        period.setContentsMargins(0, 0, 0, 0)
        period.setSpacing(6)
        self.date_start_edit = self._date_edit(QDate.currentDate().addMonths(-6))
        period.addWidget(self.date_start_edit)
        arrow = QLabel("→")
        arrow.setObjectName("HintLabel")
        period.addWidget(arrow)
        self.date_end_edit = self._date_edit(QDate.currentDate())
        period.addWidget(self.date_end_edit)
        period.addStretch()
        when_body.addWidget(self.period_row)

        # よく使う期間を一押しで。日付を 2 回選ばせない
        presets = QHBoxLayout()
        presets.setSpacing(5)
        for label, months in (("12 months", 12), ("2 years", 24), ("5 years", 60)):
            preset = QPushButton(label)
            preset.setObjectName("Preset")
            preset.setCursor(Qt.CursorShape.PointingHandCursor)
            preset.clicked.connect(lambda _c=False, m=months: self._apply_preset(m))
            presets.addWidget(preset)
        presets.addStretch()
        self.preset_row = QWidget()
        self.preset_row.setLayout(presets)
        when_body.addWidget(self.preset_row)

        self.single_row = QWidget()
        single = QVBoxLayout(self.single_row)
        single.setContentsMargins(0, 0, 0, 0)
        single.setSpacing(6)
        date_line = QHBoxLayout()
        date_line.setSpacing(6)
        self.date_edit = self._date_edit(QDate.currentDate())
        date_line.addWidget(self.date_edit)
        date_line.addStretch()
        single.addLayout(date_line)
        # なぜ選ぶのかが分からないと選べない。読ませるのは一行だけにして、
        # 詳しい違いはホバーの補足に逃がす
        single.addWidget(self._hint(self.tr("No scene on that exact date? Pick a side.")))
        self.scene_seg = _Segmented(DATE_DIRECTION_OPTIONS)
        self.scene_seg.setToolTip(
            self.tr(
                "Satellites revisit every few days, so an exact-date scene is rare.\n"
                "Nearest: closest either way · Before / After: only that side."
            )
        )
        self.scene_seg.changed.connect(self._on_input_edited)
        single.addWidget(self.scene_seg)
        when_body.addWidget(self.single_row)

        when_body.addWidget(self._hint(self.tr("Pass direction — leave as Any unless you know.")))
        self.orbit_seg = _Segmented(ORBIT_OPTIONS)
        self.orbit_seg.setToolTip(
            self.tr(
                "Which way the satellite was travelling.\n"
                "Ascending flies south to north, descending north to south;\n"
                "the viewing angle differs, so fixing one keeps a series consistent."
            )
        )
        self.orbit_seg.changed.connect(self._on_input_edited)
        when_body.addWidget(self.orbit_seg)
        outer.addWidget(self.when_body)

        # ③ 範囲
        self.area_row = _StepRow("3", self.tr("Draw an area on the map"))
        self.area_row.clicked.connect(lambda: self._toggle("area"))
        self.area_row.action.clicked.connect(self._redraw)
        self.area_row.action2.clicked.connect(self._clear_polygon)
        outer.addWidget(self.area_row)

        self.area_body = QWidget()
        area_body = QVBoxLayout(self.area_body)
        area_body.setContentsMargins(33, 2, 4, 6)
        area_body.setSpacing(6)
        # 座標を直接貼る利用者もいるので欄は残す。等幅・控えめにして、
        # 読ませる文章ではなくデータとして置く
        self.polygon_edit = QLineEdit()
        self.polygon_edit.setObjectName("PolygonEdit")
        self.polygon_edit.setPlaceholderText("POLYGON((lon lat, ...))")
        area_body.addWidget(self.polygon_edit)
        outer.addWidget(self.area_body)

        for signal in (
            self.polygon_edit.textChanged,
            self.date_edit.dateChanged,
            self.date_start_edit.dateChanged,
            self.date_end_edit.dateChanged,
        ):
            signal.connect(self._on_input_edited)

    @staticmethod
    def _hint(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("StepHint")
        label.setWordWrap(True)
        return label

    @staticmethod
    def _date_edit(initial: QDate) -> QDateEdit:
        edit = QDateEdit()
        edit.setObjectName("Chip")
        edit.setDisplayFormat("yyyy-MM-dd")
        edit.setCalendarPopup(True)
        edit.setDate(initial)
        return edit

    @staticmethod
    def _combo(options: list[tuple[str, Any]]) -> QComboBox:
        combo = QComboBox()
        combo.setObjectName("Chip")
        for label, value in options:
            combo.addItem(label, value)
        return combo

    # --- state ---------------------------------------------------------------

    def _choose_type(self, analysis_type: str) -> None:
        self._analysis_type = analysis_type
        # 選んだら次の一手へ送る。押すたびに自分で畳ませない
        self._open_step = "when"
        self._refresh()
        self.inputs_changed.emit()

    def _redraw(self) -> None:
        self._open_step = "area"
        self._refresh()
        self.polygon_picker_requested.emit()

    def _clear_polygon(self) -> None:
        """Drop the drawn area. The estimate and the canvas overlay follow."""
        self.polygon_edit.clear()
        self.area_row.value.setText("")
        self._open_step = "area"
        self._refresh()
        self.inputs_changed.emit()

    def _toggle(self, step: str) -> None:
        if step == "area":
            # まだ描いていなければ、押した意図は「描く」。描いた後は中身を開く
            self._open_step = "area"
            self._refresh()
            if not self.polygon_edit.text().strip():
                self.polygon_picker_requested.emit()
            return
        self._open_step = None if self._open_step == step else step
        self._refresh()

    def _apply_preset(self, months: int) -> None:
        """Set the period to the last N months, ending today."""
        end = QDate.currentDate()
        self.date_end_edit.setDate(end)
        self.date_start_edit.setDate(end.addMonths(-months))

    def _on_input_edited(self, *_: Any) -> None:
        self._refresh()
        self.inputs_changed.emit()

    def _refresh(self) -> None:
        kind_done = self._analysis_type is not None
        area_done = bool(self.polygon_edit.text().strip())
        # 日付は型が決まって初めて意味を持つ。既定値は常に入っているので、
        # 型さえ決まればこの段は満たされている
        when_done = kind_done

        self.kind_row.set_done(kind_done)
        self.kind_row.value.setText(
            job_summary.ANALYSIS_LABELS.get(self._analysis_type, "") if kind_done else ""
        )
        # 3 行すべてに絵を置く。1 行目だけ絵があると不揃いに見える
        self.kind_row.icon.setPixmap(
            kind_icon(self._analysis_type, 16).pixmap(16, 16)
            if kind_done
            else step_icon("target", 16).pixmap(16, 16)
        )
        self.when_row.icon.setPixmap(step_icon("calendar", 16).pixmap(16, 16))
        self.area_row.icon.setPixmap(step_icon("draw", 16).pixmap(16, 16))

        period = needs_period(self._analysis_type)
        self.when_row.label.setText(
            self.tr("Period") if period or not kind_done else self.tr("Reference date")
        )
        self.when_row.set_reachable(kind_done)
        self.when_row.set_done(when_done)
        self.when_row.value.setText(self._when_summary() if when_done else "")
        self.period_row.setVisible(period)
        self.preset_row.setVisible(period)
        self.single_row.setVisible(not period)

        self.area_row.set_done(area_done)
        self.area_row.label.setText(
            self.tr("Area drawn") if area_done else self.tr("Draw an area on the map")
        )
        # 描き終えた後こそ「押せば描き直せる」ことが見えている必要がある。
        # 済んだ段を畳んで隠すと、次にどこを押すのか分からなくなる
        # 描いた後だけ、やり直しと取り消しを行の中に並べる
        self.area_row.actions.setVisible(area_done)

        self.kind_body.setVisible(self._open_step == "kind")
        self.when_body.setVisible(self._open_step == "when" and kind_done)
        self.area_body.setVisible(self._open_step == "area")

        for analysis_type, button in self._kind_buttons.items():
            button.setProperty("chosen", analysis_type == self._analysis_type)
            button.style().unpolish(button)
            button.style().polish(button)

    def _when_summary(self) -> str:
        if needs_period(self._analysis_type):
            return (
                f"{self.date_start_edit.date().toString('yyyy-MM-dd')} → "
                f"{self.date_end_edit.date().toString('yyyy-MM-dd')}"
            )
        direction = self.scene_seg.value() or "nearest"
        return f"{self.date_edit.date().toString('yyyy-MM-dd')} · {direction}"

    # --- public API ----------------------------------------------------------

    @property
    def analysis_type(self) -> str | None:
        return self._analysis_type

    def set_analysis_type(self, analysis_type: str) -> None:
        self._analysis_type = analysis_type
        self._refresh()

    def set_polygon(self, wkt: str, area_km2: float) -> None:
        """Fill in an area picked on the map.

        The flag is what lets the panel tell this apart from a pasted WKT.
        ``setText`` emits ``inputs_changed`` synchronously, so it is read while
        still set — hence the try/finally rather than clearing it afterwards.
        """
        self._polygon_from_map = True
        try:
            self.polygon_edit.setText(wkt)
            self.area_row.value.setText(f"{area_km2:,.2f} km²")
            self._open_step = None
            self._refresh()
        finally:
            self._polygon_from_map = False

    @property
    def polygon_from_map(self) -> bool:
        """True while handling an area that came from the map tool."""
        return self._polygon_from_map

    def is_complete(self) -> bool:
        return self._analysis_type is not None and bool(self.polygon_edit.text().strip())

    def build_kwargs(self) -> dict[str, Any] | None:
        """Return kwargs for ``client.analyze.<type>(**kwargs)`` or None if incomplete."""
        polygon = self.polygon_edit.text().strip()
        if not polygon or self._analysis_type is None:
            return None
        kwargs: dict[str, Any] = {"polygon": polygon}
        if needs_period(self._analysis_type):
            kwargs["date_start"] = self.date_start_edit.date().toString("yyyy-MM-dd")
            kwargs["date_end"] = self.date_end_edit.date().toString("yyyy-MM-dd")
        else:
            kwargs["date"] = self.date_edit.date().toString("yyyy-MM-dd")
            direction = self.scene_seg.value()
            if direction:
                kwargs["date_direction"] = direction
        orbit = self.orbit_seg.value()
        if orbit:
            kwargs["orbit_direction"] = orbit
        return kwargs

    def clear(self) -> None:
        self.polygon_edit.clear()
        self.area_row.value.setText("")
        self.date_edit.setDate(QDate.currentDate())
        self.date_start_edit.setDate(QDate.currentDate().addMonths(-6))
        self.date_end_edit.setDate(QDate.currentDate())
        self.scene_seg.reset()
        self.orbit_seg.reset()
        self._open_step = "area"
        self._refresh()

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("SetupCard", message)
