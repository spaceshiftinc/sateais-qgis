"""Unit tests for workers.submit_task.

PyQt5 / qgis is required by SubmitAnalysisWorker (it inherits QThread).
We skip when those imports fail.
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
    from sateais_qgis.core.api.errors import (
        APIError,
        AuthenticationError,
        ConflictError,
        InsufficientCreditsError,
        InvalidAnalysisRequestError,
        NotFoundError,
        PayloadTooLargeError,
        PermissionDeniedError,
        RateLimitError,
        ServerError,
        ValidationError,
    )
    from sateais_qgis.core.api.types import Job, JobStatus
    from sateais_qgis.core.client_factory import AuthNotConfiguredError
    from sateais_qgis.workers import submit_task
    from sateais_qgis.workers.submit_task import SubmitAnalysisWorker


class FakeAnalyze:
    def __init__(self, raise_exc: Exception | None = None, job: Job | None = None) -> None:
        self._raise = raise_exc
        self._job = job or Job(job_id="job-fake-123", status=JobStatus.PENDING)
        self.calls: list[tuple[str, dict]] = []

    def ship(self, **kwargs):
        self.calls.append(("ship", kwargs))
        if self._raise:
            raise self._raise
        return self._job

    def newbuilding(self, **kwargs):
        self.calls.append(("newbuilding", kwargs))
        if self._raise:
            raise self._raise
        return self._job


class FakeClient:
    def __init__(self, raise_exc: Exception | None = None, job: Job | None = None) -> None:
        self.analyze = FakeAnalyze(raise_exc=raise_exc, job=job)
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _install_build_client(monkeypatch, client: FakeClient | Exception):
    def fake_build_client():
        if isinstance(client, Exception):
            raise client
        return client

    monkeypatch.setattr(submit_task, "build_client", fake_build_client, raising=False)
    # build_client is imported lazily inside run(); patch the symbol on the module
    # the worker imports from.
    import sateais_qgis.core.client_factory as cf

    monkeypatch.setattr(cf, "build_client", fake_build_client)


def _run_and_capture(worker: SubmitAnalysisWorker) -> tuple[bool, str]:
    captured: list[tuple[bool, str]] = []
    worker.finished_signal.connect(lambda ok, msg: captured.append((ok, msg)))
    worker.run()
    assert captured, "finished_signal was not emitted"
    return captured[0]


class TestSubmitAnalysisWorker:
    def test_success_emits_job_id(self, monkeypatch):
        client = FakeClient(job=Job(job_id="abc-123", status=JobStatus.PENDING))
        _install_build_client(monkeypatch, client)

        worker = SubmitAnalysisWorker("ship", {"scene_id": "S1A_test"})
        ok, payload = _run_and_capture(worker)

        assert ok is True
        assert payload == "abc-123"
        assert client.analyze.calls == [("ship", {"scene_id": "S1A_test"})]
        assert client.closed is True

    def test_auth_not_configured(self, monkeypatch):
        _install_build_client(monkeypatch, AuthNotConfiguredError("no key"))

        worker = SubmitAnalysisWorker("ship", {"scene_id": "x"})
        ok, payload = _run_and_capture(worker)

        assert ok is False
        assert payload == submit_task.ERROR_AUTH_NOT_CONFIGURED

    def test_authentication_error(self, monkeypatch):
        client = FakeClient(raise_exc=AuthenticationError(401, "UNAUTHORIZED", "bad key"))
        _install_build_client(monkeypatch, client)

        worker = SubmitAnalysisWorker("ship", {"scene_id": "x"})
        ok, payload = _run_and_capture(worker)

        assert ok is False
        assert payload == submit_task.ERROR_AUTH_FAILED
        assert client.closed is True

    def test_insufficient_credits(self, monkeypatch):
        client = FakeClient(raise_exc=InsufficientCreditsError(402, "INSUFFICIENT_CREDITS", "x"))
        _install_build_client(monkeypatch, client)

        worker = SubmitAnalysisWorker("ship", {"scene_id": "x"})
        ok, payload = _run_and_capture(worker)

        assert ok is False
        assert payload == submit_task.ERROR_INSUFFICIENT_CREDITS

    def test_invalid_input(self, monkeypatch):
        client = FakeClient(raise_exc=InvalidAnalysisRequestError("missing polygon"))
        _install_build_client(monkeypatch, client)

        worker = SubmitAnalysisWorker("ship", {})
        ok, payload = _run_and_capture(worker)

        assert ok is False
        assert payload == submit_task.ERROR_INVALID_INPUT

    def test_validation_error(self, monkeypatch):
        client = FakeClient(raise_exc=ValidationError(400, "VALIDATION_ERROR", "bad polygon"))
        _install_build_client(monkeypatch, client)

        worker = SubmitAnalysisWorker("ship", {"scene_id": "x"})
        ok, payload = _run_and_capture(worker)

        assert ok is False
        assert payload == submit_task.ERROR_VALIDATION_FAILED

    def test_rate_limit_error(self, monkeypatch):
        client = FakeClient(raise_exc=RateLimitError(429, "RATE_LIMIT_EXCEEDED", "x"))
        _install_build_client(monkeypatch, client)

        worker = SubmitAnalysisWorker("ship", {"scene_id": "x"})
        ok, payload = _run_and_capture(worker)

        assert ok is False
        assert payload == submit_task.ERROR_RATE_LIMITED

    def test_permission_denied(self, monkeypatch):
        client = FakeClient(
            raise_exc=PermissionDeniedError(403, "FORBIDDEN", "No permission for ship")
        )
        _install_build_client(monkeypatch, client)

        worker = SubmitAnalysisWorker("ship", {"scene_id": "x"})
        ok, payload = _run_and_capture(worker)

        assert ok is False
        assert payload == submit_task.ERROR_PERMISSION_DENIED

    def test_not_found(self, monkeypatch):
        client = FakeClient(raise_exc=NotFoundError(404, "SCENE_NOT_FOUND", "no scene"))
        _install_build_client(monkeypatch, client)

        worker = SubmitAnalysisWorker("ship", {"scene_id": "x"})
        ok, payload = _run_and_capture(worker)

        assert ok is False
        assert payload == submit_task.ERROR_NOT_FOUND

    def test_conflict(self, monkeypatch):
        client = FakeClient(raise_exc=ConflictError(409, "POLYGON_NOT_READY", "still processing"))
        _install_build_client(monkeypatch, client)

        worker = SubmitAnalysisWorker("ship", {"scene_id": "x"})
        ok, payload = _run_and_capture(worker)

        assert ok is False
        assert payload == submit_task.ERROR_CONFLICT

    def test_payload_too_large(self, monkeypatch):
        client = FakeClient(raise_exc=PayloadTooLargeError(413, "PAYLOAD_TOO_LARGE", "too big"))
        _install_build_client(monkeypatch, client)

        worker = SubmitAnalysisWorker("ship", {"scene_id": "x"})
        ok, payload = _run_and_capture(worker)

        assert ok is False
        assert payload == submit_task.ERROR_PAYLOAD_TOO_LARGE

    def test_server_error(self, monkeypatch):
        client = FakeClient(raise_exc=ServerError(500, "INTERNAL_ERROR", "boom"))
        _install_build_client(monkeypatch, client)

        worker = SubmitAnalysisWorker("ship", {"scene_id": "x"})
        ok, payload = _run_and_capture(worker)

        assert ok is False
        assert payload == submit_task.ERROR_SERVER_ERROR

    def test_generic_api_error_fallback(self, monkeypatch):
        # An unmapped APIError (e.g. status 418) still resolves to SERVER_ERROR.
        client = FakeClient(raise_exc=APIError(418, None, "I'm a teapot"))
        _install_build_client(monkeypatch, client)

        worker = SubmitAnalysisWorker("ship", {"scene_id": "x"})
        ok, payload = _run_and_capture(worker)

        assert ok is False
        assert payload == submit_task.ERROR_SERVER_ERROR

    def test_unexpected_exception_is_network(self, monkeypatch):
        client = FakeClient(raise_exc=RuntimeError("dns failure"))
        _install_build_client(monkeypatch, client)

        worker = SubmitAnalysisWorker("ship", {"scene_id": "x"})
        ok, payload = _run_and_capture(worker)

        assert ok is False
        assert payload == submit_task.ERROR_NETWORK_ERROR

    def test_dispatches_to_correct_detect_method(self, monkeypatch):
        client = FakeClient()
        _install_build_client(monkeypatch, client)

        worker = SubmitAnalysisWorker(
            "newbuilding",
            {
                "polygon": "POLYGON((0 0,1 0,1 1,0 1,0 0))",
                "date_start": "2024-01-01",
                "date_end": "2024-12-01",
            },
        )
        ok, payload = _run_and_capture(worker)

        assert ok is True
        assert client.analyze.calls[0][0] == "newbuilding"
        assert client.analyze.calls[0][1]["date_start"] == "2024-01-01"
