"""Pre-run estimate: what will actually be analysed, and what it costs.

Ported from the MCP map widget, where the value is that the number appears
*before* the job is submitted — a job cannot be cancelled once it runs, so an
estimate afterwards is useless. Wording and rounding come from
``core.wording`` so chat and QGIS read identically.

The card only ever states what the server returned. When coverage or the
credit estimate is missing it says so; it never fills the gap with a guess.
"""

from __future__ import annotations

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QFrame, QLabel, QProgressBar, QVBoxLayout, QWidget

from ...core import wording
from ...core.api.types import Preview


class EstimateCard(QFrame):
    """Shows the credit estimate and analysed coverage for the current inputs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("EstimateCard")
        self._build_ui()
        self.reset()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(4)

        self.credits_label = QLabel("")
        self.credits_label.setObjectName("EstimateCredits")
        self.credits_label.setWordWrap(True)
        layout.addWidget(self.credits_label)

        self.detail_label = QLabel("")
        self.detail_label.setObjectName("HintLabel")
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)

        # 待ち時間は数秒。既存の不定プログレスを使い、独自のスピナーは作らない
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(2)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

    # --- states --------------------------------------------------------------

    def reset(self) -> None:
        """No inputs yet (or they changed): show nothing rather than a stale number."""
        self.setVisible(False)
        self.progress.setVisible(False)
        self.credits_label.setText("")
        self.detail_label.setText("")

    def show_busy(self) -> None:
        self.setVisible(True)
        self.progress.setVisible(True)
        self.credits_label.setText(wording.CHECKING)
        self._set_detail("")

    def show_failed(self) -> None:
        """The estimate could not be fetched at all (after one retry)."""
        self.setVisible(True)
        self.progress.setVisible(False)
        self.credits_label.setText(wording.ESTIMATE_FAILED)
        self._set_detail("", warn=True)

    def show_preview(self, preview: Preview) -> None:
        self.setVisible(True)
        self.progress.setVisible(False)

        credits = preview.credits

        # シーンが 1 枚も無い / 前後比較に足りない。ここで金額を主役に出すと
        # 「払えば動く」と読めてしまうので、先に何が足りないかを言う
        if wording.scenes_unavailable(preview.warnings):
            server_says = wording.warning_messages(preview.warnings)
            self.credits_label.setText(
                server_says[0] if server_says else self.tr("No scenes are available.")
            )
            self._set_detail(wording.SCENES_UNAVAILABLE_HINT, warn=True)
            return

        estimated = credits.estimated if credits else None
        self.credits_label.setText(wording.credits_label(estimated))

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
        self._set_detail(" · ".join(parts), warn=warn)

    # --- helpers -------------------------------------------------------------

    def _set_detail(self, text: str, warn: bool = False) -> None:
        self.detail_label.setText(text)
        self.detail_label.setVisible(bool(text))
        self.detail_label.setObjectName("StatusError" if warn else "HintLabel")
        self.detail_label.style().unpolish(self.detail_label)
        self.detail_label.style().polish(self.detail_label)

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("EstimateCard", message)
