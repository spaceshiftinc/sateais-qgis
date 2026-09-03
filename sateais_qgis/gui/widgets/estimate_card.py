"""Pre-run estimate: what will actually be analysed, and what it costs.

Ported from the MCP map widget, where the value is that the number appears
*before* the job is submitted — a job cannot be cancelled once it runs, so an
estimate afterwards is useless. Wording and rounding come from
``core.wording`` so chat and QGIS read identically, and the reading order is
the widget's: coverage, then cost, then the legend for the shapes on the map.

The card only ever states what the server returned. When coverage or the
credit estimate is missing it says so; it never fills the gap with a guess.
"""

from __future__ import annotations

from qgis.PyQt.QtCore import QCoreApplication, QPointF, QRectF, Qt
from qgis.PyQt.QtGui import QColor, QPainter, QPen, QPixmap
from qgis.PyQt.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from ...core import wording
from ...core.api.types import Preview
from .coverage_band import (
    ANALYSED_COLOR,
    ANALYSED_FILL,
    REQUESTED_COLOR,
    UNCOVERED_COLOR,
    UNCOVERED_FILL,
)
from .loading_indicator import OrbitingSatellite

SWATCH_W = 20
SWATCH_H = 12


def _requested_swatch() -> QPixmap:
    """Dashed line, matching the requested-area band on the canvas."""
    pixmap = QPixmap(SWATCH_W, SWATCH_H)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        pen = QPen(REQUESTED_COLOR)
        pen.setWidth(2)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(QPointF(1, SWATCH_H / 2), QPointF(SWATCH_W - 1, SWATCH_H / 2))
    finally:
        painter.end()
    return pixmap


def _filled_swatch(stroke: QColor, fill: QColor) -> QPixmap:
    """Filled box, matching one of the coverage bands on the canvas."""
    pixmap = QPixmap(SWATCH_W, SWATCH_H)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setPen(QPen(stroke, 1))
        painter.setBrush(fill)
        painter.drawRect(QRectF(1, 1, SWATCH_W - 2, SWATCH_H - 2))
    finally:
        painter.end()
    return pixmap


class EstimateCard(QFrame):
    """Shows the credit estimate and analysed coverage for the current inputs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("EstimateCard")
        self._build_ui()
        self.reset()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(8)

        # 読む順は MCP ウィジェットと同じ: 被覆率 → 消費見込み → 凡例
        self.note_label = QLabel("")
        self.note_label.setObjectName("HintLabel")
        self.note_label.setWordWrap(True)
        layout.addWidget(self.note_label)

        self.credits_label = QLabel("")
        self.credits_label.setObjectName("EstimateCredits")
        self.credits_label.setTextFormat(Qt.TextFormat.RichText)
        self.credits_label.setWordWrap(True)
        layout.addWidget(self.credits_label)

        # 被覆率は数字を読むより帯を見るほうが速い。1 本だけ、細く
        self.meter = QProgressBar()
        self.meter.setObjectName("CoverageMeter")
        self.meter.setRange(0, 100)
        self.meter.setTextVisible(False)
        self.meter.setFixedHeight(4)
        self.meter.setVisible(False)
        layout.addWidget(self.meter)

        # 凡例。地図上のどの色が何なのかは、ここでしか説明されない。
        # 狭いドックでは 3 つが 1 行に入らないので折り返す
        self.legend = QFrame()
        # 数値と凡例は読む目的が違う。細い罫で段を分け、詰めて並べない
        self.legend.setObjectName("LegendBlock")
        legend_row = QGridLayout(self.legend)
        legend_row.setContentsMargins(0, 10, 0, 0)
        legend_row.setHorizontalSpacing(16)
        legend_row.setVerticalSpacing(6)
        _, requested_box = self._legend_item(_requested_swatch(), wording.LEGEND_REQUESTED)
        _, analysed_box = self._legend_item(
            _filled_swatch(ANALYSED_COLOR, ANALYSED_FILL), wording.LEGEND_COVERED
        )
        _, uncovered_box = self._legend_item(
            _filled_swatch(UNCOVERED_COLOR, UNCOVERED_FILL), wording.LEGEND_NOT_COVERED
        )
        self._analysed_box = analysed_box
        self._uncovered_box = uncovered_box
        legend_row.addWidget(requested_box, 0, 0)
        legend_row.addWidget(analysed_box, 0, 1)
        legend_row.addWidget(uncovered_box, 1, 0)
        legend_row.setColumnStretch(2, 1)
        layout.addWidget(self.legend)

        # 待っているのは衛星データの照会。抽象的なバーより、周回する衛星の方が
        # 「何を待っているのか」が伝わる（Jobs の結果取得中と同じ絵）
        self.busy_row = QWidget()
        busy = QHBoxLayout(self.busy_row)
        busy.setContentsMargins(0, 2, 0, 0)
        busy.setSpacing(8)
        self.spinner = OrbitingSatellite(size=20, parent=self.busy_row)
        busy.addWidget(self.spinner)
        self.busy_label = QLabel(wording.CHECKING)
        self.busy_label.setObjectName("HintLabel")
        busy.addWidget(self.busy_label)
        busy.addStretch()
        self.busy_row.setVisible(False)
        layout.addWidget(self.busy_row)

    @staticmethod
    def _legend_item(swatch: QPixmap, text: str) -> tuple[QLabel, QWidget]:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        icon = QLabel()
        icon.setPixmap(swatch)
        caption = QLabel(text)
        caption.setObjectName("HintLabel")
        row.addWidget(icon)
        row.addWidget(caption)
        # 末尾を止めないと、セルに余った幅が見本と語の「あいだ」に配られ、
        # 説明が離れた場所に浮いてしまう
        row.addStretch()
        return caption, box

    # --- states --------------------------------------------------------------

    def reset(self) -> None:
        """No inputs yet (or they changed): show nothing rather than a stale number."""
        self.setVisible(False)
        self._set_busy(False)
        self.meter.setVisible(False)
        self._set_note("")
        self.credits_label.setVisible(False)
        self.legend.setVisible(False)

    def show_busy(self) -> None:
        self.setVisible(True)
        self._set_busy(True)
        self._set_note("")
        self.meter.setVisible(False)
        self.credits_label.setVisible(False)
        self.legend.setVisible(False)

    def show_failed(self, reason: str) -> None:
        """The estimate could not be fetched (after one retry).

        ``reason`` is what the worker resolved the failure to — either a mapped
        message for an ``ERROR_*`` code, or a sentence ``core.wording`` built
        from the server's own answer (the per-endpoint area limit, with both
        numbers). A generic "could not load" would leave the user guessing.
        """
        self.setVisible(True)
        self._set_busy(False)
        self.meter.setVisible(False)
        self._set_note(reason or wording.ESTIMATE_FAILED, warn=True)
        self.credits_label.setVisible(False)
        self.legend.setVisible(False)

    def show_preview(self, preview: Preview) -> None:
        self.setVisible(True)
        self._set_busy(False)

        # シーンが 1 枚も無い / 前後比較に足りない。ここで金額を主役に出すと
        # 「払えば動く」と読めてしまうので、先に何が足りないかを言う
        if wording.scenes_unavailable(preview.warnings):
            server_says = wording.warning_messages(preview.warnings)
            headline = server_says[0] if server_says else self.tr("No scenes are available.")
            self._set_note(f"{headline} {wording.SCENES_UNAVAILABLE_HINT}", warn=True)
            self.credits_label.setVisible(False)
            self.meter.setVisible(False)
            self._show_legend(analysed=False)
            return

        credits = preview.credits
        ratio = preview.coverage.ratio if preview.coverage else None
        parts: list[str] = []
        warn = False

        if preview.coverage is None:
            # カタログ検索が間に合わなかった縮退。黙って通すと、要求範囲全部が
            # 解析される前提でクレジットを読んでしまう
            parts.append(wording.COVERAGE_UNCHECKED)
            warn = True
        else:
            sentence = wording.coverage_label(ratio)
            if sentence:
                parts.append(sentence)
            warn = wording.coverage_is_partial(ratio)

        balance = wording.balance_note(
            credits.sufficient if credits else None,
            credits.balance if credits else None,
        )
        if balance:
            parts.append(balance)
            warn = True
        parts.extend(wording.warning_messages(preview.warnings))

        self._set_note(" · ".join(parts), warn=warn)
        self.credits_label.setText(self._credits_markup(credits.estimated if credits else None))
        self.credits_label.setVisible(True)
        self._set_meter(ratio)
        # 青い枠は coverage.polygon が返ったときだけ地図に描かれる。
        # 描いていないものを凡例に載せない
        analysed_drawn = bool(preview.coverage and preview.coverage.polygon)
        self._show_legend(
            analysed=analysed_drawn,
            uncovered=analysed_drawn and wording.coverage_is_partial(ratio),
        )

    # --- helpers -------------------------------------------------------------

    def _show_legend(self, analysed: bool, uncovered: bool = False) -> None:
        self.legend.setVisible(True)
        self._analysed_box.setVisible(analysed)
        # 落ちる範囲が実際に塗られたときだけ説明する。全面カバーの地図に
        # 「衛星データなし」の凡例だけが残ると、無い問題を探すことになる
        self._uncovered_box.setVisible(uncovered)

    @staticmethod
    def _credits_markup(estimated: float | None) -> str:
        """Numbers big, words small — the figure is what gets compared."""
        text = wording.credits_label(estimated)
        if not text.startswith("up to "):
            return f'<span style="font-size:13px">{text}</span>'
        number = text[len("up to ") : -len(" credits")]
        return (
            '<span style="font-size:11.5px;color:#8695A2">up to </span>'
            f"{number}"
            '<span style="font-size:11.5px;color:#8695A2"> credits</span>'
        )

    def _set_meter(self, ratio: float | None) -> None:
        known = ratio is not None and 0 <= ratio <= 1
        self.meter.setVisible(known)
        if known:
            self.meter.setValue(int(ratio * 100))
            self.meter.setProperty("partial", ratio < 1)
            self.meter.style().unpolish(self.meter)
            self.meter.style().polish(self.meter)

    def _set_busy(self, busy: bool) -> None:
        self.busy_row.setVisible(busy)
        self.spinner.start() if busy else self.spinner.stop()

    def _set_note(self, text: str, warn: bool = False) -> None:
        self.note_label.setText(text)
        self.note_label.setVisible(bool(text))
        self.note_label.setObjectName("StatusError" if warn else "HintLabel")
        self.note_label.style().unpolish(self.note_label)
        self.note_label.style().polish(self.note_label)

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("EstimateCard", message)
