"""Unit tests for workers.preview_task (same harness as test_submit_task)."""

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
    from sateais_qgis.core.api.errors import (
        PayloadTooLargeError,
        RateLimitError,
        ServerError,
        ValidationError,
    )
    from sateais_qgis.core.api.types import Preview, PreviewCredits
    from sateais_qgis.core.client_factory import AuthNotConfiguredError
    from sateais_qgis.workers import preview_task
    from sateais_qgis.workers.preview_task import PreviewWorker
    from sateais_qgis.workers.submit_task import (
        ERROR_AUTH_NOT_CONFIGURED,
        ERROR_PAYLOAD_TOO_LARGE,
        ERROR_RATE_LIMITED,
        ERROR_SERVER_ERROR,
        ERROR_VALIDATION_FAILED,
    )


class FakeAnalyze:
    def __init__(self, raise_exc: Exception | None = None, preview: object | None = None) -> None:
        self._raise = raise_exc
        self._preview = preview
        self.calls: list[tuple[str, dict]] = []

    def preview(self, analysis_type, **kwargs):
        self.calls.append((analysis_type, kwargs))
        if self._raise:
            raise self._raise
        return self._preview


class FakeClient:
    def __init__(self, raise_exc: Exception | None = None, preview: object | None = None) -> None:
        self.analyze = FakeAnalyze(raise_exc=raise_exc, preview=preview)
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _install_build_client(monkeypatch, client):
    def fake_build_client():
        if isinstance(client, Exception):
            raise client
        return client

    monkeypatch.setattr(preview_task, "build_client", fake_build_client, raising=False)
    import sateais_qgis.core.client_factory as cf

    monkeypatch.setattr(cf, "build_client", fake_build_client)


def _run_and_capture(worker: PreviewWorker):
    captured = []
    worker.finished_signal.connect(lambda ok, payload: captured.append((ok, payload)))
    worker.run()
    assert captured, "finished_signal was not emitted"
    return captured[0]


class TestPreviewWorker:
    def test_success_emits_preview_object(self, monkeypatch):
        preview = Preview(credits=PreviewCredits(estimated=0.38, balance=120.5, sufficient=True))
        client = FakeClient(preview=preview)
        _install_build_client(monkeypatch, client)

        worker = PreviewWorker("newbuilding", {"polygon": "POLYGON(...)"})
        ok, payload = _run_and_capture(worker)

        assert ok is True
        assert payload is preview
        assert client.analyze.calls == [("newbuilding", {"polygon": "POLYGON(...)"})]
        assert client.closed is True

    def test_auth_not_configured(self, monkeypatch):
        _install_build_client(monkeypatch, AuthNotConfiguredError("no key"))
        ok, payload = _run_and_capture(PreviewWorker("ship", {}))
        assert ok is False
        assert payload == ERROR_AUTH_NOT_CONFIGURED

    def test_server_error_maps_to_code(self, monkeypatch):
        client = FakeClient(raise_exc=ServerError(500, "SERVER_ERROR", "boom"))
        _install_build_client(monkeypatch, client)
        ok, payload = _run_and_capture(PreviewWorker("ship", {}))
        assert ok is False
        assert payload == ERROR_SERVER_ERROR
        assert client.closed is True

    def test_rate_limit_maps_to_code(self, monkeypatch):
        client = FakeClient(raise_exc=RateLimitError(429, "RATE_LIMITED", "slow down"))
        _install_build_client(monkeypatch, client)
        ok, payload = _run_and_capture(PreviewWorker("ship", {}))
        assert ok is False
        assert payload == ERROR_RATE_LIMITED

    def test_payload_too_large_is_not_a_server_error(self, monkeypatch):
        # 巨大なポリゴンで起きる。SERVER_ERROR に丸めると、利用者は
        # 範囲を狭めればよいことに気付けない
        client = FakeClient(raise_exc=PayloadTooLargeError(413, "PAYLOAD_TOO_LARGE", "big"))
        _install_build_client(monkeypatch, client)
        ok, payload = _run_and_capture(PreviewWorker("newbuilding", {}))
        assert ok is False
        assert payload == ERROR_PAYLOAD_TOO_LARGE


class TestRejectsInputs:
    def test_the_area_limit_reaches_the_panel_as_a_rejection(self, monkeypatch):
        message = "Polygon area (52.6 km²) exceeds 50 km² limit for endpoint 'timeseries'"
        client = FakeClient(raise_exc=ValidationError(400, "VALIDATION_ERROR", message))
        _install_build_client(monkeypatch, client)
        ok, payload = _run_and_capture(PreviewWorker("timeseries", {}))
        assert ok is False
        assert payload != ERROR_VALIDATION_FAILED  # the sentence with both numbers
        assert preview_task.rejects_inputs(payload)

    def test_any_other_validation_failure_is_a_rejection(self, monkeypatch):
        client = FakeClient(raise_exc=ValidationError(400, "VALIDATION_ERROR", "bad period"))
        _install_build_client(monkeypatch, client)
        ok, payload = _run_and_capture(PreviewWorker("newbuilding", {}))
        assert payload == ERROR_VALIDATION_FAILED
        assert preview_task.rejects_inputs(payload)

    # Factories, not instances: the names only exist when PyQt does, and parameters are
    # built at collection time, even for skipped tests
    @pytest.mark.parametrize(
        "make_exc",
        [
            pytest.param(lambda: ServerError(503, "SERVICE_UNAVAILABLE", "down"), id="server"),
            pytest.param(lambda: RateLimitError(429, "RATE_LIMITED", "slow down"), id="rate"),
            pytest.param(lambda: PayloadTooLargeError(413, "PAYLOAD_TOO_LARGE", "big"), id="size"),
        ],
    )
    def test_server_side_failures_are_not(self, monkeypatch, make_exc):
        _install_build_client(monkeypatch, FakeClient(raise_exc=make_exc()))
        ok, payload = _run_and_capture(PreviewWorker("newbuilding", {}))
        assert ok is False
        assert not preview_task.rejects_inputs(payload)

    def test_a_preview_object_is_not(self):
        assert not preview_task.rejects_inputs(Preview())
