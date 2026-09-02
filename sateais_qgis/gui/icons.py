"""Per-type icons, shared with the MCP map widget.

Path data is copied verbatim from the widget (sateais-mcp-aws:
``src/widgets/core/format.ts`` ``KIND_ICONS``) and stroke colours come from
``layer_loader._STYLE_BY_TYPE`` — the single source of the type colours.
One analysis type must look the same in chat, in QGIS and in the console.
"""

from __future__ import annotations

from qgis.PyQt.QtCore import QByteArray, QRectF, Qt
from qgis.PyQt.QtGui import QIcon, QPainter, QPixmap
from qgis.PyQt.QtSvg import QSvgRenderer

from ..core.layer_loader import type_color

# format.ts KIND_ICONS と同一のパス。編集するときは両方を変える
KIND_SVG_PATHS: dict[str, str] = {
    # 船体と喫水線
    "ship": '<path d="M4 17h16l-2 4H6l-2-4Z"/><path d="M6 17V9h12v8"/><path d="M12 9V4"/>',
    # 水面に落ちる油滴
    "oilslick": (
        '<path d="M12 3c0 0 4.2 5.4 4.2 8.2a4.2 4.2 0 0 1-8.4 0C7.8 8.4 12 3 12 3Z"/>'
        '<path d="M3 19c3-2.6 6 2.6 9 0s6 2.6 9 0"/>'
    ),
    # 建ち上がる棟
    "newbuilding": (
        '<path d="M4 21V10l6-4v15"/><path d="M14 21V13l6-3v11"/>'
        '<path d="M12 3v4"/><path d="M10 5h4"/>'
    ),
    # 失われた棟（破線）
    "disappearbuilding": (
        '<path d="M4 21V10l6-4v15"/><path d="M14 21v-3" stroke-dasharray="3 3"/>'
        '<path d="M14 14v-1" stroke-dasharray="3 3"/><path d="M20 21V10" stroke-dasharray="3 3"/>'
    ),
    # 折れ線
    "timeseries": '<path d="M3 18l5-6 4 3 5-8 4 5"/><path d="M3 21h18"/>',
}

_icon_cache: dict[tuple[str, int], QIcon] = {}


def kind_svg(analysis_type: str, color: str | None = None) -> str:
    """Complete SVG document for the type, or empty string for unknown types."""
    paths = KIND_SVG_PATHS.get(analysis_type)
    if not paths:
        return ""
    stroke = color or type_color(analysis_type)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{stroke}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
        f"{paths}</svg>"
    )


def kind_icon(analysis_type: str, size: int = 16) -> QIcon:
    """Type icon as a QIcon in the type colour. Unknown types get an empty icon."""
    key = (analysis_type, size)
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached

    svg = kind_svg(analysis_type)
    if not svg:
        icon = QIcon()
        _icon_cache[key] = icon
        return icon

    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    # 高 DPI で滲まないよう 2 倍で描いてスケールは QIcon に任せる
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        renderer.render(painter, QRectF(0, 0, size, size))
    finally:
        painter.end()
    icon = QIcon(pixmap)
    _icon_cache[key] = icon
    return icon


__all__ = ["KIND_SVG_PATHS", "kind_svg", "kind_icon"]
