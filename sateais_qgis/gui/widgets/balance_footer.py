"""What the account holds, and what this run would leave.

"up to 1.44 credits" is only half a decision — the other half is how many you
have. The preview response already carries ``credits.balance``, so the footer
costs no extra request; it stays hidden until a preview has actually returned
one rather than showing a placeholder.

It sits at the bottom of the Analysis tab, where the panel would otherwise end
in empty space.
"""

from __future__ import annotations

import math

from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ...core import wording


class BalanceFooter(QFrame):
    """Credits held, and the projected remainder after the pending run."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("BalanceFooter")
        self._build_ui()
        self.clear()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        caption = QLabel(self.tr("Credits"))
        caption.setObjectName("SectionLabel")
        layout.addWidget(caption)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.balance_label = QLabel("")
        self.balance_label.setObjectName("BalanceValue")
        self.balance_label.setTextFormat(Qt.TextFormat.RichText)
        row.addWidget(self.balance_label)
        row.addStretch()
        self.after_label = QLabel("")
        self.after_label.setObjectName("HintLabel")
        self.after_label.setTextFormat(Qt.TextFormat.RichText)
        row.addWidget(self.after_label)
        layout.addLayout(row)

    def clear(self) -> None:
        self.setVisible(False)

    def set_balance(self, balance: float | None, estimated: float | None) -> None:
        """Show the balance, and the remainder when the run's cost is known."""
        # NaN / Infinity は残高ではない（json.loads はどちらも受け取る）
        if balance is None or not math.isfinite(balance):
            self.clear()
            return
        self.setVisible(True)
        self.balance_label.setText(
            f"{wording.format_credits(balance)}"
            '<span style="font-size:11.5px;color:#8695A2"> available</span>'
        )
        # 見積もりが確定しない入力では引き算をしない。0 を引いた数を「残り」と
        # 出すと、かからないという意味に読める。「確定しない」の判定は
        # core.wording が持つ一箇所を使う（同じ規則を二重に書かない）
        if wording.credits_unknown(estimated):
            self.after_label.setText("")
            self.after_label.setVisible(False)
            return
        remaining = balance - estimated
        colour = "#E3AB63" if remaining < 0 else "#8695A2"
        self.after_label.setText(
            '<span style="color:#67757F">after this run </span>'
            f'<span style="color:{colour}">{wording.format_credits(remaining)}</span>'
        )
        self.after_label.setVisible(True)

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("BalanceFooter", message)


__all__ = ["BalanceFooter"]
