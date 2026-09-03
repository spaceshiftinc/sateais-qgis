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

# 手順の行に添えるアイコン。種別アイコンと同じ描き方（24 の viewBox・
# stroke 1.6・角丸）にして、1 行目だけ絵があって以降が空という不揃いを避ける
STEP_SVG_PATHS: dict[str, str] = {
    # 検出種別が未選択のあいだの当たり（的）
    "target": (
        '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.2"/>'
        '<path d="M12 2v2M12 20v2M2 12h2M20 12h2"/>'
    ),
    # 期間・基準日
    "calendar": (
        '<rect x="3.5" y="5" width="17" height="15" rx="2.5"/>'
        '<path d="M3.5 10h17"/><path d="M8 3v4M16 3v4"/>'
    ),
    # ID をコピー（重なった 2 枚）
    "copy": (
        '<rect x="9" y="9" width="11" height="11" rx="2"/>'
        '<path d="M5 15H4.5A1.5 1.5 0 0 1 3 13.5v-9A1.5 1.5 0 0 1 4.5 3h9A1.5 1.5 0 0 1 15 4.5V5"/>'
    ),
    # 範囲の描画（点線の矩形と角のハンドル）
    "draw": (
        '<path d="M4 8V5.5A1.5 1.5 0 0 1 5.5 4H8"/><path d="M16 4h2.5A1.5 1.5 0 0 1 20 5.5V8"/>'
        '<path d="M20 16v2.5a1.5 1.5 0 0 1-1.5 1.5H16"/><path d="M8 20H5.5A1.5 1.5 0 0 1 4 18.5V16"/>'
        '<path d="M4 12h1.5M10.5 12h3M18.5 12H20M12 4v1.5M12 10.5v3M12 18.5V20"/>'
    ),
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


def step_icon(name: str, size: int = 16, color: str = "#8695A2") -> QIcon:
    """Icon for a setup step (target / calendar / draw)."""
    paths = STEP_SVG_PATHS.get(name)
    if not paths:
        return QIcon()
    return _render_icon(f"step:{name}:{color}", paths, color, size)


def kind_icon(analysis_type: str, size: int = 16) -> QIcon:
    """Type icon as a QIcon in the type colour. Unknown types get an empty icon."""
    paths = KIND_SVG_PATHS.get(analysis_type)
    if not paths:
        return QIcon()
    return _render_icon(f"kind:{analysis_type}", paths, type_color(analysis_type), size)


def _render_icon(key_base: str, paths: str, color: str, size: int) -> QIcon:
    key = (key_base, size)
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
        f"{paths}</svg>"
    )
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


__all__ = ["KIND_SVG_PATHS", "STEP_SVG_PATHS", "kind_svg", "kind_icon", "step_icon"]
