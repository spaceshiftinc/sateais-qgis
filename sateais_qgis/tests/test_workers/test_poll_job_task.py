"""Unit tests for workers.poll_job_task (requires PyQGIS for QgsTask base)."""

from __future__ import annotations

import pytest

pyqgis_available = True
try:
    from qgis.core import QgsTask  # noqa: F401
except ImportError:
    pyqgis_available = False

pytestmark = pytest.mark.skipif(
    not pyqgis_available, reason="QGIS (QgsTask) not available in this environment"
)

if pyqgis_available:
    from sateais_qgis.core.api.errors import AuthenticationError, NotFoundError
    from sateais_qgis.core.api.types import Job, JobStatus
    from sateais_qgis.core.client_factory import AuthNotConfiguredError
    from sateais_qgis.workers import poll_job_task
    from sateais_qgis.workers.poll_job_task import PollJobsTask


class FakeJobs:
    """Returns successive Job snapshots per job id from a script."""

    def __init__(self, script: dict[str, list[Job]]) -> None:
        # script: job_id -> [Job, Job, ...] consumed left to right
        self._script = {k: list(v) for k, v in script.items()}
        self.exceptions: dict[str, Exception] = {}

    def status(self, job_id: str) -> Job:
        if job_id in self.exceptions:
            raise self.exceptions[job_id]
        queue = self._script.get(job_id) or []
        if not queue:
            return Job(job_id=job_id, status=JobStatus.PENDING)
        return queue.pop(0) if len(queue) > 1 else queue[0]


class FakeClient:
    def __init__(self, jobs: FakeJobs) -> None:
        self.jobs = jobs
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def silence_sleep(monkeypatch):
    monkeypatch.setattr(poll_job_task.time, "sleep", lambda _: None)


def _install_build_client(monkeypatch, value):
    def fake():
        if isinstance(value, Exception):
            raise value
        return value

    import sateais_qgis.core.client_factory as cf

    monkeypatch.setattr(cf, "build_client", fake)


class TestPollJobsTask:
    def test_emits_status_changed_and_completed(self, monkeypatch, silence_sleep):
        jobs = FakeJobs(
            {
                "a": [
                    Job(job_id="a", status=JobStatus.PENDING),
                    Job(job_id="a", status=JobStatus.PROCESSING),
                    Job(job_id="a", status=JobStatus.COMPLETED),
                ]
            }
        )
        _install_build_client(monkeypatch, FakeClient(jobs))

        task = PollJobsTask(["a"])
        seen_status: list[tuple[str, str]] = []
        completed: list[str] = []
        task.status_changed.connect(lambda jid, s: seen_status.append((jid, s)))
        task.job_completed.connect(lambda jid: completed.append(jid))

        assert task.run() is True
        assert seen_status == [
            ("a", "pending"),
            ("a", "processing"),
            ("a", "completed"),
        ]
        assert completed == ["a"]

    def test_emits_job_failed_with_error_details(self, monkeypatch, silence_sleep):
        jobs = FakeJobs(
            {
                "x": [
                    Job(
                        job_id="x",
                        status=JobStatus.FAILED,
                        error_code="VALIDATION_ERROR",
                        error_message="bad",
                    )
                ]
            }
        )
        _install_build_client(monkeypatch, FakeClient(jobs))

        task = PollJobsTask(["x"])
        failures: list[tuple[str, str, str]] = []
        task.job_failed.connect(lambda jid, code, msg: failures.append((jid, code, msg)))

        assert task.run() is True
        assert failures == [("x", "VALIDATION_ERROR", "bad")]

    def test_returns_false_when_auth_missing(self, monkeypatch, silence_sleep):
        _install_build_client(monkeypatch, AuthNotConfiguredError("no key"))

        task = PollJobsTask(["a"])
        assert task.run() is False

    def test_transient_api_error_does_not_drop_job(self, monkeypatch, silence_sleep):
        jobs = FakeJobs(
            {
                "a": [Job(job_id="a", status=JobStatus.COMPLETED)],
            }
        )
        jobs.exceptions["a"] = AuthenticationError(401, "UNAUTHORIZED", "boom")
        client = FakeClient(jobs)
        _install_build_client(monkeypatch, client)

        task = PollJobsTask(["a"])
        completed: list[str] = []
        task.job_completed.connect(lambda jid: completed.append(jid))

        # The exception triggers the continue branch; clear it so the next
        # loop iteration would see the completed job.
        def clear_exception_after_first_raise(_):  # noqa: ARG001
            jobs.exceptions.clear()

        monkeypatch.setattr(poll_job_task.time, "sleep", clear_exception_after_first_raise)

        assert task.run() is True
        assert completed == ["a"]

    def test_add_job_extends_pending(self, monkeypatch, silence_sleep):
        jobs = FakeJobs(
            {
                "a": [Job(job_id="a", status=JobStatus.COMPLETED)],
                "b": [Job(job_id="b", status=JobStatus.COMPLETED)],
            }
        )
        _install_build_client(monkeypatch, FakeClient(jobs))

        task = PollJobsTask(["a"])
        task.add_job("b")
        completed: list[str] = []
        task.job_completed.connect(lambda jid: completed.append(jid))

        assert task.run() is True
        assert sorted(completed) == ["a", "b"]

    def test_has_pending(self, monkeypatch):
        task = PollJobsTask(["a"])
        assert task.has_pending() is True
        task._pending.clear()
        assert task.has_pending() is False

    def test_auth_missing_emits_signal(self, monkeypatch, silence_sleep):
        _install_build_client(monkeypatch, AuthNotConfiguredError("no key"))

        task = PollJobsTask(["a"])
        fired: list[bool] = []
        task.auth_missing.connect(lambda: fired.append(True))

        assert task.run() is False
        assert fired == [True]

    def test_consecutive_errors_abandon_job(self, monkeypatch, silence_sleep):
        jobs = FakeJobs({})
        jobs.exceptions["a"] = AuthenticationError(401, "UNAUTHORIZED", "boom")
        _install_build_client(monkeypatch, FakeClient(jobs))

        task = PollJobsTask(["a"])
        abandoned: list[tuple[str, str]] = []
        task.job_poll_abandoned.connect(lambda jid, reason: abandoned.append((jid, reason)))

        # Every poll raises, so after MAX_CONSECUTIVE_POLL_ERRORS rounds the
        # job is dropped and the (now empty) task exits instead of looping.
        assert task.run() is True
        assert abandoned == [("a", poll_job_task.ABANDON_ERRORS)]
        assert task.has_pending() is False

    def test_successful_poll_resets_error_budget(self, monkeypatch, silence_sleep):
        class FlakyJobs:
            """Fail the first N status calls, then report the job completed."""

            def __init__(self, failures: int) -> None:
                self._remaining = failures

            def status(self, job_id: str) -> Job:
                if self._remaining > 0:
                    self._remaining -= 1
                    raise AuthenticationError(401, "UNAUTHORIZED", "boom")
                return Job(job_id=job_id, status=JobStatus.COMPLETED)

        flaky = FakeClient(FakeJobs({}))
        flaky.jobs = FlakyJobs(poll_job_task.MAX_CONSECUTIVE_POLL_ERRORS - 1)
        _install_build_client(monkeypatch, flaky)

        task = PollJobsTask(["a"])
        completed: list[str] = []
        abandoned: list[str] = []
        task.job_completed.connect(lambda jid: completed.append(jid))
        task.job_poll_abandoned.connect(lambda jid, _reason: abandoned.append(jid))

        assert task.run() is True
        assert completed == ["a"]
        assert abandoned == []

    def test_expired_job_is_abandoned(self, monkeypatch, silence_sleep):
        jobs = FakeJobs({"a": [Job(job_id="a", status=JobStatus.PENDING)]})
        _install_build_client(monkeypatch, FakeClient(jobs))
        # Force the 24h budget to be exceeded immediately.
        monkeypatch.setattr(poll_job_task, "MAX_TRACKING_SECONDS", -1)

        task = PollJobsTask(["a"])
        abandoned: list[tuple[str, str]] = []
        task.job_poll_abandoned.connect(lambda jid, reason: abandoned.append((jid, reason)))

        assert task.run() is True
        assert abandoned == [("a", poll_job_task.ABANDON_EXPIRED)]
        assert task.has_pending() is False

    def test_missing_job_is_abandoned_on_the_first_poll(self, monkeypatch, silence_sleep):
        """A job that no longer exists is not a transient blip.

        Results are deleted after the retention period, so ``status`` answers
        404/410 forever. Spending the five-error budget on it — and then telling
        the user to press Refresh — asks them to repeat something that cannot
        succeed. Stop on the first answer, and say the job is gone.
        """

        class CountingJobs:
            def __init__(self) -> None:
                self.calls = 0

            def status(self, job_id: str) -> Job:
                self.calls += 1
                raise NotFoundError(410, "GONE", "result deleted")

        jobs = CountingJobs()
        client = FakeClient(FakeJobs({}))
        client.jobs = jobs
        _install_build_client(monkeypatch, client)

        task = PollJobsTask(["a"])
        abandoned: list[tuple[str, str]] = []
        task.job_poll_abandoned.connect(lambda jid, reason: abandoned.append((jid, reason)))

        assert task.run() is True
        assert abandoned == [("a", poll_job_task.ABANDON_GONE)]
        assert jobs.calls == 1, "a permanent answer must not be retried"
        assert task.has_pending() is False

    def test_one_missing_job_does_not_stop_the_others(self, monkeypatch, silence_sleep):
        """Dropping the gone job must leave the rest of the set polling."""
        jobs = FakeJobs({"b": [Job(job_id="b", status=JobStatus.COMPLETED)]})
        jobs.exceptions["a"] = NotFoundError(404, "NOT_FOUND", "no such job")
        _install_build_client(monkeypatch, FakeClient(jobs))

        task = PollJobsTask(["a", "b"])
        abandoned: list[tuple[str, str]] = []
        completed: list[str] = []
        task.job_poll_abandoned.connect(lambda jid, reason: abandoned.append((jid, reason)))
        task.job_completed.connect(lambda jid: completed.append(jid))

        assert task.run() is True
        assert abandoned == [("a", poll_job_task.ABANDON_GONE)]
        assert completed == ["b"]
