"""Unit tests for core.api.client (FakeApiClient is injected, no HTTP calls)."""

from __future__ import annotations

from typing import Any

import pytest

from sateais_qgis.core.api.client import Client
from sateais_qgis.core.api.errors import (
    InvalidAnalysisRequestError,
    JobFailedError,
    JobTimeoutError,
)
from sateais_qgis.core.api.types import AnalysisRequest, Job, JobStatus


class FakeApiClient:
    """In-memory ApiClient used by these tests."""

    def __init__(self) -> None:
        self.submitted: list[AnalysisRequest] = []
        # Pre-queued jobs returned by get_job, so tests can drive status sequences.
        self.status_queue: list[Job] = []
        self.result_payload: dict[str, Any] = {"type": "FeatureCollection", "features": []}
        self.closed = False

    def submit_analysis(self, request: AnalysisRequest) -> Job:
        self.submitted.append(request)
        return Job(job_id="job-fake", status=JobStatus.PENDING)

    def get_job(self, job_id: str) -> Job:
        if not self.status_queue:
            return Job(job_id=job_id, status=JobStatus.COMPLETED)
        return self.status_queue.pop(0)

    def get_job_result(self, job_id: str) -> dict[str, Any]:
        return self.result_payload

    def get_me(self) -> dict[str, Any]:
        return {
            "user_id": "fake-uuid",
            "email": "fake@example.com",
            "plan": "pro",
            "credits": {"balance": 1234.5},
        }

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def client():
    fake = FakeApiClient()
    c = Client(api_key="sk_test", api=fake)
    return c, fake


class TestClientInit:
    def test_uses_injected_api(self):
        fake = FakeApiClient()
        c = Client(api_key="sk_x", api=fake)
        # Injected ApiClients are owned by the caller; close() must not release them.
        c.close()
        assert fake.closed is False

    def test_owns_default_api(self):
        c = Client(api_key="sk_x")
        assert c._owns_api is True
        c.close()

    def test_context_manager(self):
        fake = FakeApiClient()
        with Client(api_key="sk_x", api=fake) as c:
            assert c.api_key == "sk_x"
        assert fake.closed is False


class TestAnalyzeShip:
    def test_with_scene_id_ok(self, client):
        c, fake = client
        c.analyze.ship(scene_id="S1A_x")
        assert len(fake.submitted) == 1
        req = fake.submitted[0]
        assert req.scene_id == "S1A_x"
        assert req.polygon is None

    def test_with_polygon_date_ok(self, client):
        c, fake = client
        c.analyze.ship(polygon="POLYGON((0 0,1 0,1 1,0 1,0 0))", date="2024-01-01")
        req = fake.submitted[0]
        assert req.polygon is not None
        assert req.date == "2024-01-01"

    def test_both_specified_rejected(self, client):
        c, _ = client
        with pytest.raises(InvalidAnalysisRequestError):
            c.analyze.ship(
                scene_id="S1A_x", polygon="POLYGON((0 0,1 0,1 1,0 1,0 0))", date="2024-01-01"
            )

    def test_neither_rejected(self, client):
        c, _ = client
        with pytest.raises(InvalidAnalysisRequestError):
            c.analyze.ship()


class TestAnalyzeNewBuilding:
    def test_full_params_ok(self, client):
        c, fake = client
        c.analyze.newbuilding(
            polygon="POLYGON((0 0,1 0,1 1,0 1,0 0))",
            date_start="2024-01-01",
            date_end="2024-12-01",
        )
        req = fake.submitted[0]
        assert req.date_start == "2024-01-01"
        assert req.date_end == "2024-12-01"

    def test_missing_date_rejected(self, client):
        c, _ = client
        with pytest.raises(InvalidAnalysisRequestError):
            c.analyze.newbuilding(  # type: ignore[call-arg]
                polygon="POLYGON((0 0,1 0,1 1,0 1,0 0))", date_start="2024-01-01", date_end=""
            )


class TestJobsStatus:
    def test_status_returns_job(self, client):
        c, fake = client
        fake.status_queue.append(Job(job_id="x", status=JobStatus.PROCESSING))
        job = c.jobs.status("x")
        assert job.status == JobStatus.PROCESSING

    def test_result_returns_geojson(self, client):
        c, _ = client
        result = c.jobs.result("x")
        assert result["type"] == "FeatureCollection"


class TestJobsWait:
    def test_completes_immediately(self, client):
        c, fake = client
        fake.status_queue.append(Job(job_id="x", status=JobStatus.COMPLETED))
        result = c.jobs.wait("x", poll_interval=0.001)
        assert result["type"] == "FeatureCollection"

    def test_polls_until_completed(self, monkeypatch, client):
        c, fake = client
        fake.status_queue.extend(
            [
                Job(job_id="x", status=JobStatus.PENDING),
                Job(job_id="x", status=JobStatus.PROCESSING),
                Job(job_id="x", status=JobStatus.COMPLETED),
            ]
        )
        import sateais_qgis.core.api.client as client_mod

        monkeypatch.setattr(client_mod.time, "sleep", lambda _: None)

        poll_log = []
        c.jobs.wait("x", poll_interval=0.001, on_poll=lambda j: poll_log.append(j.status))

        assert poll_log == [JobStatus.PENDING, JobStatus.PROCESSING, JobStatus.COMPLETED]

    def test_raises_job_failed(self, monkeypatch, client):
        c, fake = client
        fake.status_queue.append(
            Job(
                job_id="x",
                status=JobStatus.FAILED,
                error_code="VALIDATION_ERROR",
                error_message="bad",
            )
        )

        import sateais_qgis.core.api.client as client_mod

        monkeypatch.setattr(client_mod.time, "sleep", lambda _: None)

        with pytest.raises(JobFailedError) as exc:
            c.jobs.wait("x", poll_interval=0.001)
        assert exc.value.job.error_code == "VALIDATION_ERROR"

    def test_raises_timeout(self, monkeypatch, client):
        c, fake = client
        for _ in range(100):
            fake.status_queue.append(Job(job_id="x", status=JobStatus.PROCESSING))

        import sateais_qgis.core.api.client as client_mod

        # Patch monotonic so the timeout triggers immediately.
        t = iter([0.0, 100.0, 200.0])
        monkeypatch.setattr(client_mod.time, "monotonic", lambda: next(t))
        monkeypatch.setattr(client_mod.time, "sleep", lambda _: None)

        with pytest.raises(JobTimeoutError):
            c.jobs.wait("x", poll_interval=0.001, timeout=50.0)


class TestClientMe:
    def test_me_returns_payload(self, client):
        c, _ = client
        me = c.me()
        assert me["user_id"] == "fake-uuid"
        assert me["email"] == "fake@example.com"
        assert me["plan"] == "pro"
        assert me["credits"]["balance"] == 1234.5
