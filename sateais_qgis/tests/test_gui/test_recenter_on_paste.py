"""貼り付けた範囲へ画面を寄せる／描いた範囲では寄せない。

地図で描いた直後は利用者が既にそこを見ているので、画面を動かすと視点を奪う
ことになる。一方、WKT を打ち込んだ場合はいま見ている場所と無関係なことが
ほとんどで、寄せないと「入れたのに何も出ない」と受け取られる。同じ
``coverage_changed`` を通るため、どちらから来たかを区別できることが要点。
"""

from __future__ import annotations

import pytest

pyqgis_available = True
try:
    from qgis.core import QgsCoordinateReferenceSystem, QgsRectangle
    from qgis.gui import QgsMapCanvas
except ImportError:
    pyqgis_available = False

pytestmark = pytest.mark.skipif(
    not pyqgis_available, reason="PyQGIS not available in this environment"
)

if pyqgis_available:
    from sateais_qgis.gui.widgets.coverage_band import CoverageBand
    from sateais_qgis.gui.widgets.setup_card import SetupCard

# 東京湾。初期表示から遠く離れた場所を選ぶ
TOKYO = "POLYGON((139.6 35.6, 139.8 35.6, 139.8 35.8, 139.6 35.8, 139.6 35.6))"
# 初期表示にする範囲（南米沖）。TOKYO とは重ならない。
# 値だけを持ち、QgsRectangle は fixture で組む — モジュール直下で PyQGIS の型を
# 作ると、PyQGIS の無い CI では skip 以前に取り込みで落ちる
ELSEWHERE = (-60.0, -20.0, -59.0, -19.0)


@pytest.fixture
def canvas(qgis_app):
    canvas = QgsMapCanvas()
    canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    canvas.setExtent(QgsRectangle(*ELSEWHERE))
    return canvas


def test_recenter_moves_the_view_onto_the_polygon(canvas):
    band = CoverageBand(canvas)
    band.show_requested(TOKYO, recenter=True)

    extent = canvas.extent()
    assert extent.contains(QgsRectangle(139.6, 35.6, 139.8, 35.8)), extent.toString()


def test_without_recenter_the_view_is_left_alone(canvas):
    band = CoverageBand(canvas)
    before = canvas.extent()

    band.show_requested(TOKYO)

    assert canvas.extent().toString() == before.toString()


def test_invalid_wkt_does_not_move_the_view(canvas):
    """描けなかったときに画面だけ動くと、何が起きたのか分からなくなる。"""
    band = CoverageBand(canvas)
    before = canvas.extent()

    assert band.show_requested("not wkt at all", recenter=True) is False

    assert canvas.extent().toString() == before.toString()


class TestPolygonSource:
    """パネルが「地図で描いた」と「打ち込まれた」を見分けられること。"""

    def test_a_picked_area_is_flagged_while_it_is_applied(self, qgis_app):
        card = SetupCard()
        card.set_analysis_type("newbuilding")
        seen: list[bool] = []
        # setText は inputs_changed を同期で出す。パネルが読むのはその最中
        card.inputs_changed.connect(lambda: seen.append(card.polygon_from_map))

        card.set_polygon(TOKYO, 38.29)

        assert seen and all(seen), "picked areas must be recognisable as such"
        # 通り過ぎたら戻る。後続の打ち込みまで地図由来に見えてはいけない
        assert card.polygon_from_map is False

    def test_typed_text_is_not_flagged(self, qgis_app):
        card = SetupCard()
        card.set_analysis_type("newbuilding")
        seen: list[bool] = []
        card.inputs_changed.connect(lambda: seen.append(card.polygon_from_map))

        card.polygon_edit.setText(TOKYO)

        assert seen and not any(seen)
