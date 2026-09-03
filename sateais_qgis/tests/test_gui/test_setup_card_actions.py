"""③「範囲」の行に並ぶ二つの操作。

描いた後の行には Redraw と Clear が並ぶ。似た見た目で隣り合うので、取り違え
が起きると「描き直そうとして消えた」「消そうとして描画が始まった」になる。
行そのものも押せる（未描画なら描画に入る）ため、三つの入口の役割が混ざらない
ことを固定する。

**押下はシグナルを直接 emit せず、実際のマウスイベントで再現する。** QLabel の
既定の ``mousePressEvent`` はイベントを ignore するため、press は親の行へ伝播
し、Qt は親をマウスグラバにする。すると release も親にしか届かず、子の
``mouseReleaseEvent`` は一度も呼ばれない — Clear を押しても何も起きなかった実
際の障害がこれで、``clicked.emit()`` を叩くテストでは素通りしていた。
"""

from __future__ import annotations

import pytest

pyqgis_available = True
try:
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtTest import QTest
except ImportError:
    pyqgis_available = False

pytestmark = pytest.mark.skipif(
    not pyqgis_available, reason="PyQGIS not available in this environment"
)

if pyqgis_available:
    from sateais_qgis.gui.widgets.setup_card import SetupCard

WKT = "POLYGON((139.6 35.6, 139.8 35.6, 139.8 35.8, 139.6 35.8, 139.6 35.6))"


@pytest.fixture
def card(qgis_app):
    widget = SetupCard()
    widget.set_analysis_type("newbuilding")
    return widget


def _record(signal) -> list[int]:
    calls: list[int] = []
    signal.connect(lambda *_: calls.append(1))
    return calls


def _click(widget) -> None:
    """Press and release on the widget itself, as a user would."""
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)


def test_actions_hidden_until_an_area_is_drawn(card):
    assert not card.area_row.actions.isVisible()
    card.set_polygon(WKT, 38.29)
    assert card.area_row.actions.isVisibleTo(card)


def test_clear_empties_the_polygon_and_asks_for_a_new_estimate(card):
    card.set_polygon(WKT, 38.29)
    changed = _record(card.inputs_changed)
    picker = _record(card.polygon_picker_requested)

    _click(card.area_row.action2)

    assert card.polygon_edit.text() == ""
    assert card.area_row.value.text() == ""
    # 消した直後に描画が始まってはいけない。次に何をするかは利用者が決める
    assert picker == []
    # これが地図から破線と塗りを消す唯一の合図（パネルが coverage_changed に変える）
    assert changed, "clearing must invalidate the estimate"
    assert not card.is_complete()


def test_redraw_starts_the_picker_and_keeps_the_current_area(card):
    card.set_polygon(WKT, 38.29)
    picker = _record(card.polygon_picker_requested)

    _click(card.area_row.action)

    assert picker, "Redraw must start the map tool"
    # 描き直しを始めただけ。取り消すまでは今の範囲が見積もりの対象のまま
    assert card.polygon_edit.text() == WKT


def test_clear_does_not_also_trigger_the_row(card):
    """子の押下が親へ抜けると、消した直後に描画ツールが起動してしまう。"""
    card.set_polygon(WKT, 38.29)
    row_clicks = _record(card.area_row.clicked)

    _click(card.area_row.action2)

    assert row_clicks == []


def test_row_click_draws_only_while_the_area_is_empty(card):
    picker = _record(card.polygon_picker_requested)

    _click(card.area_row)
    assert len(picker) == 1, "an empty area row is the invitation to draw"

    card.set_polygon(WKT, 38.29)
    _click(card.area_row)
    # 描いた後の行押しは中身を開くだけ。描き直しは Redraw が受け持つ
    assert len(picker) == 1
