"""SateAIs QGIS plugin entry point and lifecycle handlers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qgis.core import Qgis
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

PLUGIN_NAME = "SateAIs API for QGIS"
MENU_NAME = "SateAIs API for QGIS"

# metadata.txt の `icon=resources/icons/sateais.png` はプラグイン一覧 (Plugin Manager) 用。
# 本ファイル内では QAction / QMenu に渡してツールバー / メニューに表示するのでパスも保持する。
_ICON_DIR = Path(__file__).parent / "resources" / "icons"
_BRAND_ICON_PATH = str(_ICON_DIR / "sateais.png")
_PANEL_ICON_PATH = str(_ICON_DIR / "panel.png")
_SETTINGS_ICON_PATH = str(_ICON_DIR / "settings.png")


class SateAIsPlugin:
    """Plugin lifecycle controller invoked by QGIS."""

    def __init__(self, iface: Any) -> None:
        self.iface = iface
        self.actions: list[QAction] = []
        self._dock = None
        # Plugins メニューに独自 submenu (ブランドアイコン付き) を作るので、
        # unload() で `iface.pluginMenu()` から removeAction するために保持する。
        self._submenu = None
        self._toolbar_action = None

    def initGui(self) -> None:
        from .core import job_tracker
        from .gui.dock_widget import SateAIsDockWidget

        # Drop tracked jobs older than the server-side retention window.
        try:
            job_tracker.cleanup_expired()
        except Exception:  # noqa: BLE001
            # Never block plugin startup on persistence errors.
            pass

        self._dock = SateAIsDockWidget(self.iface, parent=self.iface.mainWindow())
        self._dock.settings_requested.connect(self._on_settings_clicked)
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self._dock)
        self._dock.hide()

        brand_icon = QIcon(_BRAND_ICON_PATH)
        panel_icon = QIcon(_PANEL_ICON_PATH)
        settings_icon = QIcon(_SETTINGS_ICON_PATH)

        # Plugins メニューに `MENU_NAME` の submenu をブランドアイコン付きで作成する。
        # `iface.addPluginToMenu` は submenu 側にアイコンを付けられないので独自に addMenu する。
        plugin_menu = self.iface.pluginMenu()
        self._submenu = plugin_menu.addMenu(brand_icon, MENU_NAME)

        main_action = QAction(
            panel_icon,
            self.tr("Analyze"),
            self.iface.mainWindow(),
        )
        main_action.setObjectName("sateais_open_panel_action")
        main_action.triggered.connect(self._on_open_panel_clicked)
        # ツールバーにはブランドアイコンを出すため別 QAction を使う (ホバーで PLUGIN_NAME 表示)。
        toolbar_action = QAction(
            brand_icon,
            PLUGIN_NAME,
            self.iface.mainWindow(),
        )
        toolbar_action.setObjectName("sateais_toolbar_action")
        toolbar_action.triggered.connect(self._on_open_panel_clicked)
        self.iface.addToolBarIcon(toolbar_action)
        self._toolbar_action = toolbar_action

        self._submenu.addAction(main_action)
        self.actions.append(main_action)

        settings_action = QAction(
            settings_icon,
            self.tr("Settings…"),
            self.iface.mainWindow(),
        )
        settings_action.setObjectName("sateais_settings_action")
        settings_action.triggered.connect(self._on_settings_clicked)
        self._submenu.addAction(settings_action)
        self.actions.append(settings_action)

    def unload(self) -> None:
        # Plugins メニューから独自 submenu を撤去。
        if self._submenu is not None:
            self.iface.pluginMenu().removeAction(self._submenu.menuAction())
            self._submenu = None
        self.actions.clear()

        if self._toolbar_action is not None:
            try:
                self.iface.removeToolBarIcon(self._toolbar_action)
            except Exception:  # noqa: BLE001
                # 既に外されていれば無視。
                pass
            self._toolbar_action = None

        if self._dock is not None:
            self._dock.teardown()
            self.iface.removeDockWidget(self._dock)
            self._dock.deleteLater()
            self._dock = None

    def _on_open_panel_clicked(self) -> None:
        # No API-key gate here: without a key the Analysis tab shows a welcome
        # page that explains the plugin and links to Settings.
        if self._dock is not None:
            self._dock.refresh_auth_state()
            self._dock.show()
            self._dock.raise_()

    def _on_settings_clicked(self) -> None:
        from .gui.auth_dialog import AuthDialog

        dialog = AuthDialog(parent=self.iface.mainWindow())
        if dialog.exec_():
            self.iface.messageBar().pushMessage(
                PLUGIN_NAME,
                self.tr("Credentials saved."),
                level=Qgis.Success,
                duration=4,
            )
        if self._dock is not None:
            # The key may have been added or removed — swap the Analysis tab
            # between the welcome page and the submit form accordingly.
            self._dock.refresh_auth_state()

    def tr(self, message: str) -> str:
        return QCoreApplication.translate(PLUGIN_NAME, message)
