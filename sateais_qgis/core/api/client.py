"""SateAIs API client facade."""

from __future__ import annotations

import time
from typing import Any, Callable

from .errors import JobFailedError, JobTimeoutError
from .http import DEFAULT_API_BASE_URL, ApiClient, UrllibApiClient
from .types import AnalysisRequest, AnalysisType, Job

PollCallback = Callable[[Job], None]


class Client:
    """SateAIs API client.

    Example:
        >>> client = Client(api_key="sk_live_...")
        >>> job = client.analyze.ship(scene_id="S1A_IW_GRDH_...")
        >>> result = client.jobs.wait(job.job_id)
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_API_BASE_URL,
        timeout: float = 30.0,
        api: ApiClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        if api is None:
            self._api: ApiClient = UrllibApiClient(
                api_key=api_key, base_url=base_url, timeout=timeout
            )
            self._owns_api = True
        else:
            self._api = api
            self._owns_api = False

        self.analyze = Analyze(self._api)
        self.jobs = Jobs(self._api)

    def me(self) -> dict[str, Any]:
        """Return the authenticated user's profile and credit balance."""
        return self._api.get_me()

    def close(self) -> None:
        if self._owns_api:
            self._api.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


class Analyze:
    """Facade for submitting detection jobs."""

    def __init__(self, api: ApiClient) -> None:
        self._api = api

    def ship(
        self,
        scene_id: str | None = None,
        polygon: str | None = None,
        date: str | None = None,
        date_direction: str | None = None,
        orbit_direction: str | None = None,
        satellite_id: str = "sentinel-1",
    ) -> Job:
        """Submit a ship detection job. Specify scene_id or polygon+date."""
        return self._submit(
            AnalysisRequest(
                analysis_type=AnalysisType.SHIP,
                scene_id=scene_id,
                polygon=polygon,
                date=date,
                date_direction=date_direction,
                orbit_direction=orbit_direction,
                satellite_id=satellite_id,
            )
        )

    def oilslick(
        self,
        scene_id: str | None = None,
        polygon: str | None = None,
        date: str | None = None,
        date_direction: str | None = None,
        orbit_direction: str | None = None,
        satellite_id: str = "sentinel-1",
    ) -> Job:
        """Submit an oil slick detection job. Specify scene_id or polygon+date."""
        return self._submit(
            AnalysisRequest(
                analysis_type=AnalysisType.OILSLICK,
                scene_id=scene_id,
                polygon=polygon,
                date=date,
                date_direction=date_direction,
                orbit_direction=orbit_direction,
                satellite_id=satellite_id,
            )
        )

    def newbuilding(
        self,
        polygon: str,
        date_start: str,
        date_end: str,
        orbit_direction: str | None = None,
        satellite_id: str = "sentinel-1",
    ) -> Job:
        """Submit a new-building detection job."""
        return self._submit(
            AnalysisRequest(
                analysis_type=AnalysisType.NEWBUILDING,
                polygon=polygon,
                date_start=date_start,
                date_end=date_end,
                orbit_direction=orbit_direction,
                satellite_id=satellite_id,
            )
        )

    def disappearbuilding(
        self,
        polygon: str,
        date_start: str,
        date_end: str,
        orbit_direction: str | None = None,
        satellite_id: str = "sentinel-1",
    ) -> Job:
        """Submit a disappear-building detection job."""
        return self._submit(
            AnalysisRequest(
                analysis_type=AnalysisType.DISAPPEARBUILDING,
                polygon=polygon,
                date_start=date_start,
                date_end=date_end,
                orbit_direction=orbit_direction,
                satellite_id=satellite_id,
            )
        )

    def timeseries(
        self,
        polygon: str,
        date_start: str,
        date_end: str,
        orbit_direction: str | None = None,
        satellite_id: str = "sentinel-1",
    ) -> Job:
        """Submit a time-series change-detection job."""
        return self._submit(
            AnalysisRequest(
                analysis_type=AnalysisType.TIMESERIES,
                polygon=polygon,
                date_start=date_start,
                date_end=date_end,
                orbit_direction=orbit_direction,
                satellite_id=satellite_id,
            )
        )

    def _submit(self, request: AnalysisRequest) -> Job:
        request.validate()
        return self._api.submit_analysis(request)


class Jobs:
    """Facade for inspecting and waiting on jobs."""

    def __init__(self, api: ApiClient) -> None:
        self._api = api

    def status(self, job_id: str) -> Job:
        """Return the current status of a job."""
        return self._api.get_job(job_id)

    def list(
        self,
        statuses: list[str] | None = None,
        endpoint_ids: list[str] | None = None,
        limit: int | None = None,
    ) -> list[Job]:
        """Return the caller's most recent jobs (server caps at 30).

        Optional filters mirror the API: ``statuses`` / ``endpoint_ids`` are
        joined into comma-separated query params.
        """
        return self._api.list_jobs(statuses=statuses, endpoint_ids=endpoint_ids, limit=limit)

    def result(self, job_id: str) -> dict[str, Any]:
        """Return the GeoJSON result of a completed job."""
        return self._api.get_job_result(job_id)

    def wait(
        self,
        job_id: str,
        poll_interval: float = 10.0,
        timeout: float | None = None,
        on_poll: PollCallback | None = None,
    ) -> dict[str, Any]:
        """Poll until the job completes and return the GeoJSON result.

        Args:
            job_id: ID of the job to wait for.
            poll_interval: Seconds between status checks.
            timeout: Maximum seconds to wait. None for no limit.
            on_poll: Optional callback invoked after each poll with the Job.

        Raises:
            JobFailedError: If the job ends in the failed state.
            JobTimeoutError: If the job does not complete within `timeout`.
        """
        start = time.monotonic()
        while True:
            job = self._api.get_job(job_id)
            if on_poll is not None:
                on_poll(job)

            if job.is_completed:
                return self._api.get_job_result(job_id)
            if job.is_failed:
                raise JobFailedError(job)

            if timeout is not None and time.monotonic() - start > timeout:
                raise JobTimeoutError(
                    f"Job {job_id} did not complete within {timeout}s "
                    f"(last status={job.status.value})"
                )

            time.sleep(poll_interval)


__all__ = ["Client", "Analyze", "Jobs"]
