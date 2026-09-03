"""見積もりワーカーの寿命。

QGIS 3.40 で実際に出た障害:

    RuntimeError: wrapped C/C++ object of type PreviewWorker has been deleted
      analysis_panel._detach_preview_worker → worker.isRunning()

範囲を描き直すたびに新しい問い合わせを投げる作りにしたとき、古い応答を
「seq が違うから無視する」際に ``_preview_worker`` の参照まで残していた。
``finished → deleteLater`` で Qt が C++ 側を壊した後もその殻を掴み続けるため、
次に触れた瞬間に落ちる。**終わったワーカーは seq に関係なく手放す**のが正しい。
"""

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
    from qgis.PyQt.QtCore import QObject, pyqtSignal

    from sateais_qgis.core.api.types import Preview, PreviewCredits


class _FakeWorker(QObject if pyqt_available else object):
    """Stands in for PreviewWorker; records whether it was let go."""

    if pyqt_available:
        finished_signal = pyqtSignal(bool, object)
        finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.detached = False

    def isRunning(self):  # noqa: N802 - Qt API name
        return False

    def deleteLater(self):  # noqa: N802 - Qt API name
        self.detached = True


class _PanelStub:
    """Just the ownership rule from AnalysisPanel, without any Qt widgets."""

    def __init__(self):
        self._preview_worker = None
        self._preview_seq = 0

    on_finished = None  # bound in the test


class TestStaleResponseReleasesWorker:
    def test_finished_worker_is_released_even_when_the_response_is_stale(self):
        from sateais_qgis.gui.widgets.analysis_panel import AnalysisPanel

        panel = AnalysisPanel.__new__(AnalysisPanel)  # UI を作らずに規則だけ確かめる
        worker = _FakeWorker()
        panel._preview_worker = worker
        panel._preview_seq = 5
        panel._preview_retried = False

        # seq=1 は 4 回前の問い合わせ。表示はしないが、参照は必ず解放する
        AnalysisPanel._on_preview_finished(
            panel, True, Preview(credits=PreviewCredits(estimated=1.0)), 1, worker
        )
        assert panel._preview_worker is None

    def test_a_newer_worker_is_not_released_by_an_older_response(self):
        from sateais_qgis.gui.widgets.analysis_panel import AnalysisPanel

        panel = AnalysisPanel.__new__(AnalysisPanel)
        old_worker, new_worker = _FakeWorker(), _FakeWorker()
        panel._preview_worker = new_worker
        panel._preview_seq = 5
        panel._preview_retried = False

        AnalysisPanel._on_preview_finished(
            panel, True, Preview(credits=PreviewCredits(estimated=1.0)), 1, old_worker
        )
        # 誰を消すかは seq ではなく同一性で決まる
        assert panel._preview_worker is new_worker
