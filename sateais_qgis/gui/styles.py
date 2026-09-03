"""COSMIC design system stylesheet, shared by all SateAIs widgets.

Palette: SateAIs brand colours (docs.spcsft.com / sateais.com):
  bg #0B131A (navy) / accent #009FE8 (SateAIs blue) / bright #5BC2F2

Apply via ``widget.setStyleSheet(COSMIC_STYLESHEET)`` on the top-level
container (the dialog or dock widget). Qt scopes the rules to that subtree,
so the bare selectors below do not leak into surrounding QGIS widgets.
"""

from __future__ import annotations

COSMIC_STYLESHEET = """
QWidget {
    color: #E3EBF1;
    background-color: #0B131A;
    font-family: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", "Noto Sans JP", "Hiragino Sans", "Noto Sans", "Liberation Sans", Arial, sans-serif;
    font-size: 13px;
}

QLabel {
    color: #E3EBF1;
    background: transparent;
}

QLabel#TitleLabel {
    color: #E3EBF1;
    font-size: 16px;
    font-weight: 600;
    padding-bottom: 2px;
}

QLabel#SubtitleLabel {
    color: #8695A2;
    font-size: 12.5px;
}

QLabel#SectionLabel {
    color: #8695A2;
    font-size: 10.5px;
    font-weight: 500;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    padding-top: 10px;
}

QLabel#HintLabel {
    color: #8695A2;
    font-size: 11.5px;
}

QLabel#StatusOk {
    color: #6CC39A;
    font-size: 12.5px;
}

QLabel#StatusError {
    color: #E3AB63;
    font-size: 12.5px;
}

QFrame#EstimateCard {
    background: #121A21;
    border: 1px solid #22303A;
    border-radius: 12px;
}

/* 凡例は数値の続きではない。細い罫で段を分ける */
QFrame#LegendBlock {
    background: transparent;
    border: none;
    border-top: 1px solid #22303A;
}

QLabel#EstimateCredits {
    color: #E3EBF1;
    font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 15px;
    letter-spacing: -0.01em;
}

/* ---- setup: 揃うまでの手順を並べるカード（MCP の .step / .stepbody） ---- */
QFrame#SetupCard {
    background: #121A21;
    border: 1px solid #22303A;
    border-radius: 12px;
}

QLabel#SetupTitle {
    color: #8695A2;
    font-size: 12.5px;
}

QFrame#StepRow {
    background: transparent;
    border: none;
    border-radius: 8px;
}

QFrame#StepRow:hover {
    background: rgba(227, 235, 241, 0.05);
}

/* 届いていない段は薄く。押せないことを色で示す */
QLabel#StepLabel[dim="true"], QLabel#StepValue[dim="true"] {
    color: #3C4750;
}

/* 丸にするには「幅・高さ・角丸」を Qt に同時に見せる必要がある。
   固定サイズだけだと QSS 側が矩形のまま描いてしまう */
QLabel#StepBadge {
    min-width: 19px;
    max-width: 19px;
    min-height: 19px;
    max-height: 19px;
    border: 1px solid #62717C;
    border-radius: 9px;
    color: #8695A2;
    font-size: 10px;
    font-weight: 600;
    background: transparent;
}

QLabel#StepBadge[done="true"] {
    border-color: #6CC39A;
    color: #6CC39A;
}

QLabel#StepLabel {
    color: #E3EBF1;
    font-size: 13px;
}

/* 選ぶ理由の一行。読ませるが、読まなくても進める重さに留める */
QLabel#StepHint {
    color: #67757F;
    font-size: 10.5px;
    padding-top: 2px;
}

/* 選択肢そのものがラベルになる帯（MCP の .seg）。見出しを立てずに済む */
QPushButton#SegButton {
    background: transparent;
    border: 1px solid #22303A;
    border-right: none;
    color: #8695A2;
    font-size: 11px;
    padding: 4px 10px;
}

QPushButton#SegButton[first="true"] {
    border-top-left-radius: 8px;
    border-bottom-left-radius: 8px;
}

QPushButton#SegButton[last="true"] {
    border-right: 1px solid #22303A;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
}

QPushButton#SegButton:hover {
    color: #E3EBF1;
}

QPushButton#SegButton:checked {
    background: #009FE8;
    color: #FFFFFF;
    border-color: #009FE8;
}

/* よく使う期間の近道（MCP の .preset） */
QPushButton#Preset {
    background: transparent;
    border: 1px solid #22303A;
    border-radius: 8px;
    color: #8695A2;
    font-size: 11px;
    padding: 3px 8px;
}

QPushButton#Preset:hover {
    color: #E3EBF1;
    border-color: #62717C;
}

QLabel#StepAction {
    color: #009FE8;
    font-size: 11.5px;
}

/* 取り消しは戻れない。並んだ二つのうち手前だけを青くし、
   こちらは触れたときにだけ色で警告する */
QLabel#StepActionMuted {
    color: #8695A2;
    font-size: 11.5px;
}

QLabel#StepActionMuted:hover {
    color: #E08B80;
}

QLabel#StepValue {
    color: #8695A2;
    font-size: 12px;
}

QPushButton#StepOption {
    background: transparent;
    border: none;
    border-radius: 8px;
    color: #E3EBF1;
    font-size: 13px;
    text-align: left;
    padding: 7px 8px;
}

QPushButton#StepOption:hover {
    background: rgba(227, 235, 241, 0.06);
}

QPushButton#StepOption[chosen="true"] {
    color: #009FE8;
    background: rgba(0, 159, 232, 0.08);
}

/* 下端の残高。押す前に「幾ら持っていて、押した後に幾ら残るか」を置く場所。
   カードではなく上の罫線だけで区切り、見積もりカードと競わせない */
QFrame#BalanceFooter {
    background: transparent;
    border: none;
    border-top: 1px solid #1A242C;
}

QLabel#BalanceValue {
    color: #E3EBF1;
    font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 14px;
}

/* ドック上端のブランド行。QGIS の中に置く帯なので、控えめな高さに留める */
QWidget#BrandBar {
    background: #0E161D;
    border-bottom: 1px solid #22303A;
}

QLineEdit#PolygonEdit {
    color: #8695A2;
    font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11px;
}

QLineEdit#PolygonEdit:focus {
    color: #E3EBF1;
}

/* ジョブの状態。MCP の .pill と同じ扱いで、常に同じ位置に同じ形で出る */
/* 角丸は高さの半分でないと丸くならない。padding と min-height を固定して
   半径をそれに合わせる（999px 指定だけでは角が残る） */
/* 実測でピルの自然幅は 110px あり、狭いドックでは 1 行目が入りきらず
   名前のほうが削られていた。読める最小限まで詰める */
QLabel#PillOk, QLabel#PillError, QLabel#PillMuted {
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 0.03em;
    padding: 0px 7px;
    min-height: 17px;
    max-height: 17px;
    border-radius: 8px;
}

QLabel#PillOk {
    color: #6CC39A;
    background: rgba(108, 195, 154, 0.12);
}

QLabel#PillError {
    color: #E08B80;
    background: rgba(224, 139, 128, 0.12);
}

QLabel#PillMuted {
    color: #009FE8;
    background: rgba(0, 159, 232, 0.14);
}

QLabel#JobTitle {
    color: #E3EBF1;
    font-size: 12.5px;
    font-weight: 450;
}

/* 結果の一行。状態（進行）とは別に、何が幾つ見つかったかを言い切る場所 */
QLabel#FindCount {
    color: #6CC39A;
    font-size: 11.5px;
}

/* メタ行の端に置く小さな操作（ID コピーなど） */
QPushButton#IconButton {
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 0px;
}

QPushButton#IconButton:hover {
    background: rgba(227, 235, 241, 0.08);
}

/* 被覆率の帯。部分被覆のときだけ色が変わる */
QProgressBar#CoverageMeter {
    background: #1A242C;
    border: none;
    border-radius: 2px;
}

QProgressBar#CoverageMeter::chunk {
    background: #009FE8;
    border-radius: 2px;
}

QProgressBar#CoverageMeter[partial="true"]::chunk {
    background: #E3AB63;
}

/* ジョブ ID。控えるための値なので、読む数字より一段弱く */
QLabel#JobId {
    color: #4C5964;
    font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 9px;
}

/* 見出しと値が交互に並ぶ行。等幅にすると見出しの語まで数字組みになって
   カード内で浮くので、本文と同じ書体で組む（色分けは job_card 側） */
QLabel#JobMeta {
    color: #8695A2;
    font-size: 11px;
}

QLabel#EmptyTitle {
    color: #E3EBF1;
    font-size: 16px;
    font-weight: 600;
    background: transparent;
}

QLabel#EmptySubtitle {
    color: #8695A2;
    font-size: 12px;
    background: transparent;
}

/* 入力も操作もチップ。MCP ウィジェットの .chip と同じ寸法
   (surface 背景 / 1px の線 / 角丸 8px / 13px / padding 7px 12px)。
   ラベル行を置かずに、チップ自体が何であるかを示す作りに合わせる */
QLineEdit, QDateEdit, QComboBox, QPushButton#Chip {
    background-color: #121A21;
    color: #E3EBF1;
    border: 1px solid #22303A;
    border-radius: 8px;
    padding: 7px 12px;
    font-size: 13px;
    selection-background-color: #009FE8;
    selection-color: #04202E;
}

QLineEdit:hover, QDateEdit:hover, QComboBox:hover, QPushButton#Chip:hover {
    border: 1px solid #62717C;
}

QLineEdit:focus, QDateEdit:focus, QComboBox:focus, QPushButton#Chip:focus {
    border: 1px solid #009FE8;
}

QPushButton#Chip {
    color: #E3EBF1;
}

QPushButton#Chip:disabled {
    color: #3C4750;
    border-color: #1A242C;
}

QPlainTextEdit, QTextEdit {
    background-color: #121A21;
    color: #E3EBF1;
    border: 1px solid #22303A;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 12px;
    selection-background-color: #009FE8;
    selection-color: #0B131A;
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
    background-color: #121A21;
    color: #E3EBF1;
    border: 1px solid #22303A;
    border-radius: 12px;
    padding: 4px;
    outline: none;
    selection-background-color: #14303F;
    selection-color: #009FE8;
}

QComboBox QAbstractItemView::item {
    padding: 7px 8px;
    border-radius: 8px;
}

QPushButton {
    background-color: rgba(255, 255, 255, 0.03);
    color: #E3EBF1;
    border: 1px solid #22303A;
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: rgba(255, 255, 255, 0.06);
    border-color: rgba(0, 159, 232, 0.45);
}

QPushButton:pressed {
    background-color: rgba(0, 159, 232, 0.16);
}

QPushButton:disabled {
    color: #67757F;
    border-color: #1A242C;
    background-color: rgba(255, 255, 255, 0.02);
}

QPushButton#PrimaryButton {
    background-color: #009FE8;
    color: #ffffff;
    border: 1px solid #009FE8;
    font-weight: 600;
}

QPushButton#PrimaryButton:hover {
    background-color: #2BB4F0;
    border-color: #2BB4F0;
}

QPushButton#PrimaryButton:pressed {
    background-color: #0079B3;
}

QPushButton#PrimaryButton:disabled {
    background-color: rgba(0, 159, 232, 0.20);
    color: rgba(255, 255, 255, 0.45);
    border-color: rgba(0, 159, 232, 0.20);
}

QPushButton#GhostButton {
    background-color: transparent;
    border: none;
    color: #8695A2;
    padding: 4px 8px;
}

QPushButton#GhostButton:hover {
    color: #5BC2F2;
}

QCheckBox, QRadioButton {
    color: #8695A2;
    font-size: 12px;
    background: transparent;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #22303A;
    background-color: #121A21;
}

QCheckBox::indicator {
    border-radius: 3px;
}

QRadioButton::indicator {
    border-radius: 7px;
}

QCheckBox::indicator:checked,
QRadioButton::indicator:checked {
    background-color: #009FE8;
    border-color: #009FE8;
}

QFrame#Divider {
    background-color: #22303A;
    max-height: 1px;
    min-height: 1px;
}

QProgressBar {
    background-color: #1A242C;
    border: none;
    border-radius: 2px;
    max-height: 4px;
}

QProgressBar::chunk {
    background-color: #009FE8;
    border-radius: 2px;
}

QTabWidget::pane {
    border: none;
    background: transparent;
}

QTabBar::tab {
    background-color: transparent;
    color: #67757F;
    padding: 8px 16px;
    border: none;
    font-size: 13px;
}

QTabBar::tab:hover {
    color: #E3EBF1;
}

QTabBar::tab:selected {
    color: #5BC2F2;
    border-bottom: 2px solid #009FE8;
}

QScrollArea {
    background: transparent;
    border: none;
}

/* 日付ポップアップ。既定のままだと白地のカレンダーが飛び出して浮く */
QCalendarWidget QWidget {
    alternate-background-color: #121A21;
    background-color: #121A21;
    color: #E3EBF1;
}

QCalendarWidget QAbstractItemView:enabled {
    background-color: #121A21;
    color: #E3EBF1;
    selection-background-color: #009FE8;
    selection-color: #04202E;
    outline: none;
}

QCalendarWidget QAbstractItemView:disabled {
    color: #3C4750;
}

QCalendarWidget QWidget#qt_calendar_navigationbar {
    background-color: #0E161D;
    border-bottom: 1px solid #22303A;
}

QCalendarWidget QToolButton {
    background: transparent;
    border: none;
    border-radius: 6px;
    color: #E3EBF1;
    font-size: 12.5px;
    padding: 4px 8px;
}

QCalendarWidget QToolButton:hover {
    background: rgba(227, 235, 241, 0.08);
}

QCalendarWidget QSpinBox {
    background: #121A21;
    color: #E3EBF1;
    border: 1px solid #22303A;
}

/* ジョブは「カード」ではなく連続した行。MCP の .row と同じで、境界は
   下線 1 本、選択中だけ左に 2px のブランド色バーが立つ */
QFrame#JobCard {
    background-color: transparent;
    border: none;
    border-bottom: 1px solid #1A242C;
    border-left: 2px solid transparent;
}

QFrame#JobCard:hover {
    background-color: #0E161D;
}

QFrame#JobCardPulse {
    background-color: rgba(0, 159, 232, 0.10);
    border: none;
    border-bottom: 1px solid #1A242C;
    border-left: 2px solid #009FE8;
}

QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background-color: #2B3945;
    border-radius: 4px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background-color: #3C4750;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}
"""
