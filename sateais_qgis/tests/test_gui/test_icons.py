"""Unit tests for gui.icons (pure SVG assembly; QIcon rendering is visual-only)."""

from __future__ import annotations

import pytest

pyqt_available = True
try:
    from qgis.PyQt.QtCore import QCoreApplication  # noqa: F401
except ImportError:
    pyqt_available = False

pytestmark = pytest.mark.skipif(
    not pyqt_available, reason="PyQt5 / qgis not available in this environment"
)

if pyqt_available:
    from qgis.PyQt.QtGui import QGuiApplication

    from sateais_qgis.core.layer_loader import _STYLE_BY_TYPE, type_color
    from sateais_qgis.gui.icons import KIND_SVG_PATHS, kind_icon, kind_svg


class TestKindSvg:
    def test_every_plugin_type_has_an_icon(self):
        # プラグインが扱う型 (= _STYLE_BY_TYPE) とアイコンがずれない
        assert set(KIND_SVG_PATHS) == set(_STYLE_BY_TYPE)

    def test_stroke_uses_the_single_colour_source(self):
        for analysis_type in KIND_SVG_PATHS:
            svg = kind_svg(analysis_type)
            assert f'stroke="{type_color(analysis_type)}"' in svg
            # currentColor は widget (CSS 世界) の書き方。Qt 側に持ち込まない
            assert "currentColor" not in svg

    def test_unknown_type_yields_empty(self):
        assert kind_svg("unknown_kind") == ""


@pytest.fixture(scope="module")
def qt_app():
    """QPixmap needs a QGuiApplication; reuse QGIS's when running inside it."""
    app = QGuiApplication.instance() or QGuiApplication([])
    return app


class TestKindIconRendering:
    """SVG 文字列が正しくても、描画されなければアイコンは空のまま出る。
    パスの綴り間違いを「見た目が出ない」ではなくテストで捕まえる。"""

    def test_every_icon_paints_something(self, qt_app):
        for analysis_type in KIND_SVG_PATHS:
            icon = kind_icon(analysis_type, 16)
            assert not icon.isNull(), analysis_type
            image = icon.pixmap(16, 16).toImage()
            painted = sum(
                1
                for x in range(image.width())
                for y in range(image.height())
                if image.pixelColor(x, y).alpha() > 0
            )
            assert painted > 20, f"{analysis_type}: painted only {painted}px"

    def test_unknown_type_is_empty_not_a_crash(self, qt_app):
        assert kind_icon("unknown_kind", 16).isNull()
