"""Authentication dialog (API key entry + Test Connection)."""

from __future__ import annotations

from qgis.PyQt.QtCore import QCoreApplication, Qt, QThread, QUrl, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core import client_factory, settings
from ..workers.lifecycle import detach_worker
from .styles import COSMIC_STYLESHEET

CONSOLE_URL = "https://console.spcsft.com"


class _TestConnectionWorker(QThread):
    """Run a connection check off the UI thread."""

    finished_signal = pyqtSignal(bool, str)

    def __init__(self, api_key: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api_key = api_key

    def run(self) -> None:
        ok, msg = client_factory.test_connection(api_key=self._api_key)
        self.finished_signal.emit(ok, msg)


class AuthDialog(QDialog):
    """Modal dialog for entering the API key."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SateAIsAuthDialog")
        self.setWindowTitle(self.tr("SateAIs Settings"))
        self.setStyleSheet(COSMIC_STYLESHEET)
        self.setMinimumWidth(440)
        self.setMinimumHeight(300)

        self._worker: _TestConnectionWorker | None = None
        self._build_ui()
        self._load_existing()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 20)
        outer.setSpacing(14)

        title = QLabel(self.tr("SateAIs Settings"))
        title.setObjectName("TitleLabel")
        subtitle = QLabel(self.tr("Configure your API key to connect to the SateAIs API."))
        subtitle.setObjectName("SubtitleLabel")
        subtitle.setWordWrap(True)
        outer.addWidget(title)
        outer.addWidget(subtitle)

        outer.addWidget(self._section_label(self.tr("API Key")))

        key_row = QHBoxLayout()
        key_row.setSpacing(6)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("sk_live_...")
        self.api_key_edit.textChanged.connect(self._on_input_changed)
        key_row.addWidget(self.api_key_edit, 1)

        self.show_key_check = QCheckBox(self.tr("Show"))
        self.show_key_check.toggled.connect(self._on_show_key_toggled)
        key_row.addWidget(self.show_key_check)
        outer.addLayout(key_row)

        get_key = QPushButton(self.tr("Get an API key at console.spcsft.com →"))
        get_key.setObjectName("GhostButton")
        get_key.setCursor(Qt.PointingHandCursor)
        get_key.setFlat(True)
        get_key.clicked.connect(self._on_open_console)
        outer.addWidget(get_key)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.HLine)
        outer.addWidget(divider)

        test_row = QHBoxLayout()
        test_row.setSpacing(10)
        self.test_button = QPushButton(self.tr("Test Connection"))
        self.test_button.clicked.connect(self._on_test_clicked)
        test_row.addWidget(self.test_button)
        self.test_status = QLabel("")
        self.test_status.setObjectName("HintLabel")
        test_row.addWidget(self.test_status, 1)
        outer.addLayout(test_row)

        self.test_progress = QProgressBar()
        self.test_progress.setRange(0, 0)  # indeterminate
        self.test_progress.setVisible(False)
        outer.addWidget(self.test_progress)

        outer.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton(self.tr("Cancel"))
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        self.save_button = QPushButton(self.tr("Save & Close"))
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self._on_save_clicked)
        btn_row.addWidget(self.save_button)
        outer.addLayout(btn_row)

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionLabel")
        return label

    def _load_existing(self) -> None:
        existing_key = settings.get_api_key() or ""
        self.api_key_edit.setText(existing_key)

    def _on_input_changed(self) -> None:
        self.test_status.setText("")
        self.test_status.setObjectName("HintLabel")
        self.test_status.style().unpolish(self.test_status)
        self.test_status.style().polish(self.test_status)

    def _on_show_key_toggled(self, checked: bool) -> None:
        self.api_key_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)

    def _on_open_console(self) -> None:
        QDesktopServices.openUrl(QUrl(CONSOLE_URL))

    def _on_test_clicked(self) -> None:
        # Buttons are disabled while a check runs, but guard anyway so two
        # workers can never race each other's completion handler.
        if self._worker is not None:
            return

        api_key = self.api_key_edit.text().strip()
        if not api_key:
            self._show_status(False, self.tr("Please enter an API key."))
            return

        self.test_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.test_progress.setVisible(True)
        self.test_status.setText(self.tr("Testing connection…"))
        self.test_status.setObjectName("HintLabel")
        self.test_status.style().unpolish(self.test_status)
        self.test_status.style().polish(self.test_status)

        worker = _TestConnectionWorker(api_key, self)
        worker.finished_signal.connect(self._on_test_finished)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def _on_test_finished(self, ok: bool, msg: str) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            try:
                worker.finished_signal.disconnect(self._on_test_finished)
            except (TypeError, RuntimeError):
                pass

        self.test_progress.setVisible(False)
        self.test_button.setEnabled(True)
        self.save_button.setEnabled(True)
        if ok:
            self._show_status(True, f"✓ {msg}")
        else:
            self._show_status(False, f"✕ {msg}")

    def done(self, result: int) -> None:  # type: ignore[override]
        """Detach an in-flight test worker before the dialog is destroyed.

        Closing the dialog (Cancel / Save / window close) while the connection
        check is still running would otherwise destroy a running QThread when
        the dialog is garbage-collected, which aborts the whole QGIS process.
        """
        worker = self._worker
        self._worker = None
        if worker is not None and worker.isRunning():
            try:
                worker.finished_signal.disconnect(self._on_test_finished)
            except (TypeError, RuntimeError):
                pass
            detach_worker(worker)
        super().done(result)

    def _show_status(self, ok: bool, msg: str) -> None:
        self.test_status.setText(msg)
        self.test_status.setObjectName("StatusOk" if ok else "StatusError")
        self.test_status.style().unpolish(self.test_status)
        self.test_status.style().polish(self.test_status)

    def _on_save_clicked(self) -> None:
        api_key = self.api_key_edit.text().strip()
        if not api_key:
            self._show_status(False, self.tr("Please enter an API key."))
            return

        settings.set_api_key(api_key)
        self.accept()

    def tr(self, message: str) -> str:
        return QCoreApplication.translate("SateAIsAuthDialog", message)
