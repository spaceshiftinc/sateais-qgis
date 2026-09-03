"""SPACESHIFT wordmark, shared with the MCP map widget.

Path data is copied verbatim from the widget (sateais-mcp-aws:
``src/widgets/core/brand.ts``). Text is ``currentColor`` so it reads on either
theme; only the spark in the middle keeps the brand blue.
"""

from __future__ import annotations

from qgis.PyQt.QtCore import QByteArray, QRectF, Qt
from qgis.PyQt.QtGui import QPainter, QPixmap
from qgis.PyQt.QtSvg import QSvgRenderer

LOGO_VIEWBOX = "0 0 600 96"
LOGO_PATHS = '<g> <path fill="currentColor" d="M479.1,7.3V89h-12.3V7.3H479.1z"/> <path fill="currentColor" d="M524.1,18.9h-23.4v19.6h19.7l-3.6,11.6h-16.1V89h-12.3V7.3h40.8L524.1,18.9z"/> <path fill="currentColor" d="M564,18.9V89h-12.3V18.9h-18.8V7.3h49.9l-5.1,11.6H564z"/> <path fill="currentColor" d="M112.9,55.8V89h-12.3V7.3h14c6.8,0,12,0.5,15.5,1.4c3.5,1,6.6,2.8,9.3,5.4c4.7,4.6,7,10.4,7,17.4 c0,7.5-2.5,13.4-7.5,17.8c-5,4.4-11.8,6.6-20.3,6.6H112.9z M112.9,44.4h4.6c11.3,0,17-4.4,17-13.1c0-8.4-5.8-12.7-17.5-12.7h-4.1 V44.4z"/> <path fill="currentColor" d="M293.7,18.9h-27.7v19.6H292l-5.1,11.6h-20.8v27.3h32.8L293.7,89h-40V7.3h45.1L293.7,18.9z"/> <path fill="currentColor" d="M246,78.8c-7.3-0.5-13.6-3.4-18.8-8.7c-5.8-5.9-8.7-13.1-8.7-21.7c0-8.7,2.9-16,8.7-22 c5.2-5.5,11.5-8.4,18.8-8.9V5.8c-12,0.8-21.9,5.7-29.6,14.9c-6.9,8.2-10.3,17.4-10.3,27.8c0,11.6,4.1,21.5,12.3,29.8 c7.7,7.6,16.9,11.6,27.6,12.1V78.8z"/> <path fill="currentColor" d="M371.3,40.4l-8.2-3.3c-5.9-2.4-8.9-5.7-8.9-9.6c0-2.9,1.1-5.3,3.4-7.2c2.3-1.9,5.1-2.9,8.5-2.9 c1,0,1.9,0.1,2.7,0.2V5.8c-0.8-0.1-1.7-0.1-2.6-0.1c-7,0-12.8,2.1-17.5,6.2c-4.7,4.1-7,9.3-7,15.4c0,9.1,5.6,16,16.8,20.7l7.9,3.3 c2,0.9,3.8,1.8,5.3,2.8c1.5,1,2.7,2,3.6,3.1c0.9,1.1,1.6,2.3,2.1,3.6c0.4,1.3,0.7,2.8,0.7,4.4c0,3.9-1.3,7.2-3.8,9.8 s-5.7,3.9-9.6,3.9c-4.9,0-8.6-1.8-11.1-5.3c-1.1-1.5-2-3.9-2.6-7.2h-12.9c1.1,7.6,4,13.5,8.5,17.8c4.6,4.2,10.5,6.3,17.6,6.3 c7.5,0,13.7-2.5,18.8-7.4c5-4.9,7.5-11.1,7.5-18.6c0-5.6-1.5-10.4-4.6-14.2C382.8,46.4,378,43.1,371.3,40.4z"/> <path fill="currentColor" d="M75.4,40.4l-8.2-3.3c-5.9-2.4-8.9-5.7-8.9-9.6c0-2.9,1.1-5.3,3.4-7.2c2.3-1.9,5.1-2.9,8.5-2.9 c1,0,1.9,0.1,2.7,0.2V5.8c-0.8-0.1-1.7-0.1-2.6-0.1c-7,0-12.8,2.1-17.5,6.2c-4.7,4.1-7,9.3-7,15.4c0,9.1,5.6,16,16.8,20.7l7.9,3.3 c2,0.9,3.8,1.8,5.3,2.8c1.5,1,2.7,2,3.6,3.1c0.9,1.1,1.6,2.3,2.1,3.6c0.4,1.3,0.7,2.8,0.7,4.4c0,3.9-1.3,7.2-3.8,9.8 c-2.5,2.6-5.7,3.9-9.6,3.9c-4.9,0-8.6-1.8-11.1-5.3c-1.1-1.5-2-3.9-2.6-7.2H42.2c1.1,7.6,4,13.5,8.5,17.8 c4.6,4.2,10.5,6.3,17.6,6.3c7.5,0,13.7-2.5,18.8-7.4c5-4.9,7.5-11.1,7.5-18.6c0-5.6-1.5-10.4-4.6-14.2C86.9,46.4,82,43.1,75.4,40.4 z"/> <g> <polygon fill="#009FE8" points="173.9,55.9 169.4,55.9 171.6,52 "/> <polygon fill="#009FE8" points="173.9,71.6 169.4,71.6 171.6,75.5 "/> <polygon fill="#009FE8" points="171,55.6 166.9,57.1 167.6,52.7 "/> <polygon fill="#009FE8" points="176.4,70.4 172.2,71.9 175.7,74.8 "/> <polygon fill="#009FE8" points="168.3,56.3 164.9,59.1 164.1,54.7 "/> <polygon fill="#009FE8" points="178.4,68.3 175,71.2 179.2,72.7 "/> <polygon fill="#009FE8" points="165.9,57.9 163.7,61.7 161.5,57.9 "/> <polygon fill="#009FE8" points="179.6,65.7 177.3,69.6 181.8,69.6 "/> <polygon fill="#009FE8" points="164.3,60.2 163.5,64.6 160.1,61.7 "/> <polygon fill="#009FE8" points="179.8,62.9 179,67.3 183.2,65.8 "/> <polygon fill="#009FE8" points="163.5,62.9 164.3,67.3 160.1,65.8 "/> <polygon fill="#009FE8" points="179,60.2 179.8,64.6 183.2,61.7 "/> <polygon fill="#009FE8" points="163.7,65.7 165.9,69.6 161.5,69.6 "/> <polygon fill="#009FE8" points="177.3,57.9 179.6,61.7 181.8,57.9 "/> <polygon fill="#009FE8" points="164.9,68.3 168.3,71.2 164.1,72.7 "/> <polygon fill="#009FE8" points="175,56.3 178.4,59.1 179.2,54.7 "/> <polygon fill="#009FE8" points="166.9,70.4 171,71.9 167.6,74.8 "/> <polygon fill="#009FE8" points="172.2,55.6 176.4,57.1 175.7,52.7 "/> <path fill="#009FE8" d="M180,63.6c0-4.6-3.7-8.4-8.4-8.4c-4.6,0-8.4,3.7-8.4,8.4c0,4.6,3.7,8.4,8.4,8.4C176.3,72,180,68.2,180,63.6z" /> <path fill="#009FE8" d="M178.7,63.7c0-3.9-3.2-7.1-7.1-7.1c-3.9,0-7.1,3.2-7.1,7.1c0,3.9,3.2,7.1,7.1,7.1 C175.5,70.8,178.7,67.6,178.7,63.7z"/> </g> <polygon fill="currentColor" points="445.7,7.3 445.7,39.2 445.7,39.2 445.7,51.1 445.7,51.1 445.7,89 458,89 458,7.3 "/> <polygon fill="currentColor" points="440.4,39.3 410.4,39.3 410.4,7.3 398.1,7.3 398.1,89 410.4,89 410.4,50.9 435.5,50.9 "/> <polygon fill="currentColor" points="194.9,7.3 188.2,7.3 181.1,7.3 113,89 128.8,89 188.2,18.1 188.2,89 200.5,89 200.5,7.3 "/> </g>'

# ワードマーク中央の閃光だけを切り出したもの。件数の前に置く印として使う。
# 汎用のアイコンより、自社のマークの一部であるほうが画面全体で由来が揃う
SPARK_VIEWBOX = "160 52 24 24"
SPARK_PATHS = '<polygon fill="currentColor" points="173.9,55.9 169.4,55.9 171.6,52 "/> <polygon fill="currentColor" points="173.9,71.6 169.4,71.6 171.6,75.5 "/> <polygon fill="currentColor" points="171,55.6 166.9,57.1 167.6,52.7 "/> <polygon fill="currentColor" points="176.4,70.4 172.2,71.9 175.7,74.8 "/> <polygon fill="currentColor" points="168.3,56.3 164.9,59.1 164.1,54.7 "/> <polygon fill="currentColor" points="178.4,68.3 175,71.2 179.2,72.7 "/> <polygon fill="currentColor" points="165.9,57.9 163.7,61.7 161.5,57.9 "/> <polygon fill="currentColor" points="179.6,65.7 177.3,69.6 181.8,69.6 "/> <polygon fill="currentColor" points="164.3,60.2 163.5,64.6 160.1,61.7 "/> <polygon fill="currentColor" points="179.8,62.9 179,67.3 183.2,65.8 "/> <polygon fill="currentColor" points="163.5,62.9 164.3,67.3 160.1,65.8 "/> <polygon fill="currentColor" points="179,60.2 179.8,64.6 183.2,61.7 "/> <polygon fill="currentColor" points="163.7,65.7 165.9,69.6 161.5,69.6 "/> <polygon fill="currentColor" points="177.3,57.9 179.6,61.7 181.8,57.9 "/> <polygon fill="currentColor" points="164.9,68.3 168.3,71.2 164.1,72.7 "/> <polygon fill="currentColor" points="175,56.3 178.4,59.1 179.2,54.7 "/> <polygon fill="currentColor" points="166.9,70.4 171,71.9 167.6,74.8 "/> <polygon fill="currentColor" points="172.2,55.6 176.4,57.1 175.7,52.7 "/> <path fill="currentColor" d="M180,63.6c0-4.6-3.7-8.4-8.4-8.4c-4.6,0-8.4,3.7-8.4,8.4c0,4.6,3.7,8.4,8.4,8.4C176.3,72,180,68.2,180,63.6z" /> <path fill="currentColor" d="M178.7,63.7c0-3.9-3.2-7.1-7.1-7.1c-3.9,0-7.1,3.2-7.1,7.1c0,3.9,3.2,7.1,7.1,7.1 C175.5,70.8,178.7,67.6,178.7,63.7z"/>'


def _render(viewbox: str, paths: str, color: str, height: int) -> QPixmap:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" '
        f'color="{color}" fill="{color}">{paths}</svg>'
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    size = renderer.defaultSize()
    ratio = (size.width() / size.height()) if size.height() else 1.0
    width = max(1, round(height * ratio))
    # 高 DPI で滲まないよう 2 倍で描く
    pixmap = QPixmap(width * 2, height * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        renderer.render(painter, QRectF(0, 0, width, height))
    finally:
        painter.end()
    return pixmap


def wordmark(color: str = "#E6EAF5", height: int = 18) -> QPixmap:
    """SPACESHIFT wordmark at the given cap height."""
    return _render(LOGO_VIEWBOX, LOGO_PATHS, color, height)


def spark(color: str = "#009FE8", height: int = 13) -> QPixmap:
    """The wordmark's spark on its own, for use next to a count."""
    return _render(SPARK_VIEWBOX, SPARK_PATHS, color, height)


__all__ = ["wordmark", "spark", "LOGO_VIEWBOX", "LOGO_PATHS", "SPARK_VIEWBOX", "SPARK_PATHS"]
