"""COSMIC design system stylesheet, shared by all SateAIs widgets.

Palette: SateAIs brand colours (docs.spcsft.com / sateais.com):
  bg #05080F (navy) / accent #00A0E9 (SateAIs blue) / bright #5BC2F2

Apply via ``widget.setStyleSheet(COSMIC_STYLESHEET)`` on the top-level
container (the dialog or dock widget). Qt scopes the rules to that subtree,
so the bare selectors below do not leak into surrounding QGIS widgets.
"""

from __future__ import annotations

COSMIC_STYLESHEET = """
QWidget {
    color: #E6EAF5;
    background-color: #05080F;
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", "Noto Sans JP", "Hiragino Sans", "Noto Sans", "Liberation Sans", Arial, sans-serif;
}

QLabel {
    color: #E6EAF5;
    background: transparent;
}

QLabel#TitleLabel {
    color: #E6EAF5;
    font-size: 18px;
    font-weight: 600;
    padding-bottom: 4px;
    letter-spacing: 0.02em;
}

QLabel#SubtitleLabel {
    color: #A8B0C4;
    font-size: 12px;
}

QLabel#SectionLabel {
    color: #E6EAF5;
    font-size: 13px;
    font-weight: 500;
    padding-top: 8px;
}

QLabel#HintLabel {
    color: #6E768C;
    font-size: 11px;
}

QLabel#StatusOk {
    color: #3ad17a;
    font-size: 12px;
    font-weight: 500;
}

QLabel#StatusError {
    color: #ff6b6b;
    font-size: 12px;
    font-weight: 500;
}

QFrame#EstimateCard {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 6px;
}

QLabel#EstimateCredits {
    color: #E6EAF5;
    font-size: 15px;
    font-weight: 600;
}

QLabel#EmptyTitle {
    color: #E6EAF5;
    font-size: 16px;
    font-weight: 600;
    background: transparent;
}

QLabel#EmptySubtitle {
    color: #A8B0C4;
    font-size: 12px;
    background: transparent;
}

QLineEdit, QDateEdit, QComboBox {
    background-color: #0D1326;
    color: #E6EAF5;
    border: 1px solid rgba(180, 200, 240, 0.10);
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    selection-background-color: #00A0E9;
    selection-color: #05080F;
}

QLineEdit:focus, QDateEdit:focus, QComboBox:focus {
    border: 1px solid #00A0E9;
    background-color: #131A33;
}

QPlainTextEdit, QTextEdit {
    background-color: #0D1326;
    color: #E6EAF5;
    border: 1px solid rgba(180, 200, 240, 0.10);
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 12px;
    selection-background-color: #00A0E9;
    selection-color: #05080F;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox::down-arrow {
    width: 10px;
    height: 10px;
}

QComboBox QAbstractItemView {
    background-color: #0D1326;
    color: #E6EAF5;
    border: 1px solid rgba(180, 200, 240, 0.20);
    selection-background-color: #131A33;
}

QPushButton {
    background-color: rgba(255, 255, 255, 0.03);
    color: #E6EAF5;
    border: 1px solid rgba(180, 200, 240, 0.20);
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: rgba(255, 255, 255, 0.06);
    border-color: rgba(0, 160, 233, 0.45);
}

QPushButton:pressed {
    background-color: rgba(0, 160, 233, 0.16);
}

QPushButton:disabled {
    color: #6E768C;
    border-color: rgba(180, 200, 240, 0.06);
    background-color: rgba(255, 255, 255, 0.02);
}

QPushButton#PrimaryButton {
    background-color: #00A0E9;
    color: #ffffff;
    border: 1px solid #00A0E9;
    font-weight: 600;
}

QPushButton#PrimaryButton:hover {
    background-color: #1AB1F0;
    border-color: #1AB1F0;
}

QPushButton#PrimaryButton:pressed {
    background-color: #0089CC;
}

QPushButton#PrimaryButton:disabled {
    background-color: rgba(0, 160, 233, 0.20);
    color: rgba(255, 255, 255, 0.45);
    border-color: rgba(0, 160, 233, 0.20);
}

QPushButton#GhostButton {
    background-color: transparent;
    border: none;
    color: #A8B0C4;
    padding: 4px 8px;
}

QPushButton#GhostButton:hover {
    color: #5BC2F2;
}

QCheckBox, QRadioButton {
    color: #A8B0C4;
    font-size: 12px;
    background: transparent;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid rgba(180, 200, 240, 0.20);
    background-color: #0D1326;
}

QCheckBox::indicator {
    border-radius: 3px;
}

QRadioButton::indicator {
    border-radius: 7px;
}

QCheckBox::indicator:checked,
QRadioButton::indicator:checked {
    background-color: #00A0E9;
    border-color: #00A0E9;
}

QFrame#Divider {
    background-color: rgba(180, 200, 240, 0.10);
    max-height: 1px;
    min-height: 1px;
}

QProgressBar {
    background-color: rgba(180, 200, 240, 0.08);
    border: none;
    border-radius: 2px;
    max-height: 4px;
}

QProgressBar::chunk {
    background-color: #00A0E9;
    border-radius: 2px;
}

QTabWidget::pane {
    border: none;
    background: transparent;
}

QTabBar::tab {
    background-color: transparent;
    color: #6E768C;
    padding: 8px 16px;
    border: none;
    font-size: 13px;
}

QTabBar::tab:hover {
    color: #E6EAF5;
}

QTabBar::tab:selected {
    color: #5BC2F2;
    border-bottom: 2px solid #00A0E9;
}

QScrollArea {
    background: transparent;
    border: none;
}

QFrame#JobCard {
    background-color: #0D1326;
    border: 1px solid rgba(180, 200, 240, 0.10);
    border-radius: 8px;
}

QFrame#JobCard:hover {
    background-color: #131A33;
    border-color: rgba(0, 160, 233, 0.45);
}

/* Brief glow applied when a job flips to completed (reverts after ~650ms). */
QFrame#JobCardPulse {
    background-color: #16223f;
    border: 1px solid rgba(0, 160, 233, 0.85);
    border-radius: 8px;
}

QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background-color: rgba(180, 200, 240, 0.15);
    border-radius: 4px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background-color: rgba(180, 200, 240, 0.25);
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}
"""
