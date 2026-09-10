"""Unit tests for core.job_tracker (QSettings backed via monkeypatched _settings)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

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
    from sateais_qgis.core import job_tracker, settings


class FakeSettings:
    """In-memory drop-in for QSettings used by core.settings._settings()."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def value(self, key, default=None, type=None):
        return self._store.get(key, default)

    def setValue(self, key, value) -> None:
        self._store[key] = value

    def remove(self, key) -> None:
        self._store.pop(key, None)


@pytest.fixture
def fake_store(monkeypatch):
    store = FakeSettings()
    monkeypatch.setattr(settings, "_settings", lambda: store)
    # job_tracker binds ``_settings`` at import time (``from .settings import
    # _settings``), so its reference must be patched too — patching only the
    # settings module leaks every write into the user's real QSettings.
    monkeypatch.setattr(job_tracker, "_settings", lambda: store)
    return store


class TestAddAndList:
    def test_add_inserts_at_head(self, fake_store):
        job_tracker.add("ship", "id-1")
        job_tracker.add("oilslick", "id-2")

        jobs = job_tracker.list_all()
        assert [j.job_id for j in jobs] == ["id-2", "id-1"]
        assert jobs[0].analysis_type == "oilslick"
        assert jobs[0].status == "pending"
        assert jobs[0].submitted_at  # non-empty ISO string

    def test_add_is_idempotent(self, fake_store):
        first = job_tracker.add("ship", "dup")
        second = job_tracker.add("ship", "dup")
        assert first.job_id == second.job_id
        assert len(job_tracker.list_all()) == 1

    def test_add_persists_polygon(self, fake_store):
        wkt = "POLYGON((0 0,1 0,1 1,0 1,0 0))"
        job_tracker.add("newbuilding", "p-1", polygon=wkt)
        assert job_tracker.list_all()[0].polygon == wkt

    def test_add_without_polygon_defaults_to_none(self, fake_store):
        job_tracker.add("ship", "s-1")
        assert job_tracker.list_all()[0].polygon is None

    def test_legacy_entry_without_polygon_loads_as_none(self, fake_store):
        # Simulates jobs persisted before the polygon field existed.
        fake_store.setValue(
            "jobs_v1",
            json.dumps(
                [
                    {
                        "job_id": "old",
                        "analysis_type": "ship",
                        "submitted_at": "2026-01-01T00:00:00+00:00",
                    }
                ]
            ),
        )
        assert job_tracker.list_all()[0].polygon is None

    def test_legacy_entry_without_request_context_loads_with_defaults(self, fake_store):
        # Same contract for the request fields: entries written by earlier
        # versions must load unchanged, which is why no migration is needed.
        fake_store.setValue(
            "jobs_v1",
            json.dumps(
                [
                    {
                        "job_id": "old",
                        "analysis_type": "timeseries",
                        "submitted_at": "2026-01-01T00:00:00+00:00",
                    }
                ]
            ),
        )
        job = job_tracker.list_all()[0]
        assert job.scene_id is None
        assert job.date is None
        assert job.date_start is None
        assert job.date_end is None
        assert job.request_source == ""

    def test_add_stores_allowlisted_request_parameters(self, fake_store):
        job_tracker.add(
            "timeseries",
            "r-1",
            request={
                "polygon": "POLYGON((0 0,1 0,1 1,0 1,0 0))",
                "date_start": "2026-01-03",
                "date_end": "2026-07-03",
                # Constant for every job, so not worth storing.
                "satellite_id": "sentinel-1",
                # Not submittable from QGIS; must not leak into the stored blob.
                "polygon_id": "abc",
            },
            request_source="local",
        )

        job = job_tracker.list_all()[0]
        assert job.date_start == "2026-01-03"
        assert job.date_end == "2026-07-03"
        assert job.polygon == "POLYGON((0 0,1 0,1 1,0 1,0 0))"
        assert job.request_source == "local"
        assert "satellite_id" not in job.to_dict()
        assert "polygon_id" not in job.to_dict()

    def test_add_tolerates_a_missing_or_malformed_request(self, fake_store):
        job_tracker.add("ship", "r-2", request=None)
        job_tracker.add("ship", "r-3", request="not a dict")
        for job_id in ("r-2", "r-3"):
            job = next(j for j in job_tracker.list_all() if j.job_id == job_id)
            assert job.scene_id is None
            assert job.date is None


class TestSetRequestContext:
    def test_fills_in_dates_and_marks_the_source(self, fake_store):
        job_tracker.add("timeseries", "s-1")
        result = job_tracker.set_request_context(
            "s-1", {"date_start": "2026-01-03", "date_end": "2026-07-03"}, "server"
        )

        assert result is not None
        assert result.date_start == "2026-01-03"
        assert result.request_source == "server"
        assert job_tracker.list_all()[0].date_end == "2026-07-03"

    def test_none_values_do_not_erase_what_is_stored(self, fake_store):
        job_tracker.add("ship", "s-2", request={"scene_id": "S1A_X"}, request_source="local")
        job_tracker.set_request_context("s-2", {"date": "2026-01-01"}, "server")

        job = job_tracker.list_all()[0]
        assert job.scene_id == "S1A_X"
        assert job.date == "2026-01-01"

    def test_backfills_a_missing_polygon(self, fake_store):
        # This is what makes AOI preview work for console / CLI / MCP jobs.
        job_tracker.add("timeseries", "s-3")
        job_tracker.set_request_context("s-3", {"polygon": "POLYGON((0 0,1 0,1 1,0 0))"}, "server")
        assert job_tracker.list_all()[0].polygon == "POLYGON((0 0,1 0,1 1,0 0))"

    def test_never_overwrites_the_polygon_the_user_drew(self, fake_store):
        drawn = "POLYGON((0 0,1 0,1 1,0 1,0 0))"
        job_tracker.add("timeseries", "s-4", polygon=drawn)
        job_tracker.set_request_context("s-4", {"polygon": "POLYGON((9 9,8 8,7 7,9 9))"}, "server")
        assert job_tracker.list_all()[0].polygon == drawn

    def test_non_string_values_are_ignored(self, fake_store):
        job_tracker.add("timeseries", "s-5")
        job_tracker.set_request_context("s-5", {"date_start": 20260103, "date_end": True}, "server")

        job = job_tracker.list_all()[0]
        assert job.date_start is None
        assert job.date_end is None

    def test_unavailable_never_demotes_a_locally_captured_request(self, fake_store):
        # A Sync that returns no request_params for a job we submitted ourselves
        # must not erase the fact that we captured it at submit time.
        job_tracker.add("ship", "s-8", request={"scene_id": "S1A_X"}, request_source="local")
        job_tracker.set_request_context("s-8", None, "unavailable")

        job = job_tracker.list_all()[0]
        assert job.request_source == "local"
        assert job.scene_id == "S1A_X"

    def test_unavailable_still_marks_a_job_that_never_had_a_request(self, fake_store):
        job_tracker.add("ship", "s-9")
        job_tracker.set_request_context("s-9", None, "unavailable")
        assert job_tracker.list_all()[0].request_source == "unavailable"

    def test_empty_source_leaves_the_marker_alone(self, fake_store):
        job_tracker.add("ship", "s-6", request={"scene_id": "S1A_X"}, request_source="local")
        job_tracker.set_request_context("s-6", {"date": "2026-01-01"}, "")
        assert job_tracker.list_all()[0].request_source == "local"

    def test_unknown_job_returns_none(self, fake_store):
        assert job_tracker.set_request_context("nope", {"date": "2026-01-01"}, "server") is None

    def test_survives_a_json_round_trip(self, fake_store):
        job_tracker.add(
            "ship",
            "s-7",
            request={"scene_id": "S1A_IW_GRDH", "date": "2026-01-01"},
            request_source="local",
        )
        stored = json.loads(fake_store.value("jobs_v1"))
        assert stored[0]["scene_id"] == "S1A_IW_GRDH"
        assert stored[0]["date"] == "2026-01-01"
        assert stored[0]["request_source"] == "local"


class TestUpdateStatus:
    def test_update_existing(self, fake_store):
        job_tracker.add("ship", "x")
        result = job_tracker.update_status("x", "completed")
        assert result is not None
        assert result.status == "completed"
        assert job_tracker.list_all()[0].status == "completed"

    def test_update_with_error_info(self, fake_store):
        job_tracker.add("ship", "x")
        job_tracker.update_status(
            "x", "failed", error_code="VALIDATION_ERROR", error_message="bad polygon"
        )
        job = job_tracker.list_all()[0]
        assert job.status == "failed"
        assert job.error_code == "VALIDATION_ERROR"
        assert job.error_message == "bad polygon"

    def test_update_unknown_status_normalised(self, fake_store):
        job_tracker.add("ship", "x")
        job_tracker.update_status("x", "weird")
        assert job_tracker.list_all()[0].status == "unknown"

    def test_update_missing_returns_none(self, fake_store):
        assert job_tracker.update_status("nope", "completed") is None


class TestRemove:
    def test_remove_existing(self, fake_store):
        job_tracker.add("ship", "a")
        job_tracker.add("ship", "b")
        assert job_tracker.remove("a") is True
        assert [j.job_id for j in job_tracker.list_all()] == ["b"]

    def test_remove_missing(self, fake_store):
        assert job_tracker.remove("nope") is False


class TestCleanupExpired:
    def test_drops_old_entries(self, fake_store):
        old_iso = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        recent_iso = datetime.now(timezone.utc).isoformat()
        fake_store.setValue(
            "jobs_v1",
            json.dumps(
                [
                    {"job_id": "old", "analysis_type": "ship", "submitted_at": old_iso},
                    {"job_id": "new", "analysis_type": "ship", "submitted_at": recent_iso},
                ]
            ),
        )

        removed = job_tracker.cleanup_expired(retention_days=30)
        assert removed == 1
        assert [j.job_id for j in job_tracker.list_all()] == ["new"]

    def test_keeps_entries_with_invalid_timestamp(self, fake_store):
        fake_store.setValue(
            "jobs_v1",
            json.dumps(
                [{"job_id": "broken", "analysis_type": "ship", "submitted_at": "not-a-date"}]
            ),
        )
        removed = job_tracker.cleanup_expired(retention_days=1)
        assert removed == 0
        assert len(job_tracker.list_all()) == 1

    def test_no_op_when_retention_zero(self, fake_store):
        old_iso = (datetime.now(timezone.utc) - timedelta(days=999)).isoformat()
        fake_store.setValue(
            "jobs_v1",
            json.dumps([{"job_id": "old", "analysis_type": "ship", "submitted_at": old_iso}]),
        )
        assert job_tracker.cleanup_expired(retention_days=0) == 0
        assert len(job_tracker.list_all()) == 1


class TestFromDictTyping:
    def test_drops_entry_with_non_string_job_id(self, fake_store):
        fake_store.setValue(
            "jobs_v1",
            json.dumps(
                [
                    {"job_id": 123, "analysis_type": "ship"},
                    {
                        "job_id": "good",
                        "analysis_type": "ship",
                        "submitted_at": "2026-01-01T00:00:00+00:00",
                    },
                ]
            ),
        )
        jobs = job_tracker.list_all()
        assert [j.job_id for j in jobs] == ["good"]

    def test_drops_entry_missing_job_id(self, fake_store):
        fake_store.setValue(
            "jobs_v1",
            json.dumps([{"analysis_type": "ship"}, {"job_id": "good", "analysis_type": "ship"}]),
        )
        jobs = job_tracker.list_all()
        assert [j.job_id for j in jobs] == ["good"]

    def test_non_string_polygon_loads_as_none(self, fake_store):
        fake_store.setValue(
            "jobs_v1",
            json.dumps([{"job_id": "x", "analysis_type": "ship", "polygon": 123}]),
        )
        assert job_tracker.list_all()[0].polygon is None


class TestPersistenceFormat:
    def test_roundtrip_preserves_fields(self, fake_store):
        job_tracker.add("newbuilding", "abc")
        job_tracker.update_status("abc", "processing")
        raw = fake_store.value("jobs_v1", "[]", type=str)
        decoded = json.loads(raw)
        assert decoded[0]["job_id"] == "abc"
        assert decoded[0]["analysis_type"] == "newbuilding"
        assert decoded[0]["status"] == "processing"

    def test_handles_corrupt_payload(self, fake_store):
        fake_store.setValue("jobs_v1", "not valid json")
        assert job_tracker.list_all() == []
        # Subsequent add() should still work.
        job_tracker.add("ship", "fresh")
        assert [j.job_id for j in job_tracker.list_all()] == ["fresh"]


class TestListAllOrdering:
    """一覧は投入日時の新しい順。**保存順ではない。**

    実際に起きていた不具合: ローカル投入は先頭に積み、Sync は別の順で挿し込む
    ため、保存順は経路によって変わる。利用者の環境（47 件）では
    2026-08-19 の並びの直後に 2026-08-24 が現れていた。並びが崩れると、
    リスト自体が何順なのか読めなくなる。
    """

    def _stored(self, fake_store, stamps):
        fake_store.setValue(
            job_tracker._KEY_JOBS,
            json.dumps(
                [
                    {
                        "job_id": f"job-{i}",
                        "analysis_type": "ship",
                        "submitted_at": stamp,
                        "status": "completed",
                    }
                    for i, stamp in enumerate(stamps)
                ]
            ),
        )

    def test_out_of_order_storage_is_sorted_newest_first(self, fake_store):
        # 実環境で観測した崩れ方をそのまま再現する
        self._stored(
            fake_store,
            [
                "2026-09-03T00:12:12+00:00",
                "2026-08-19T10:02:55+00:00",
                "2026-08-24T07:34:29+00:00",  # 古い位置に紛れた新しい記録
                "2026-07-28T06:54:21+00:00",
            ],
        )
        got = [j.submitted_at[:10] for j in job_tracker.list_all()]
        assert got == ["2026-09-03", "2026-08-24", "2026-08-19", "2026-07-28"]

    def test_mixed_timestamp_formats_still_compare(self, fake_store):
        """Z 付きとオフセット付きが混在する。文字列比較では並ばない。"""
        self._stored(
            fake_store,
            ["2026-08-19T10:02:55Z", "2026-09-03T00:12:12+00:00", "2026-08-24T07:34:29Z"],
        )
        got = [j.submitted_at[:10] for j in job_tracker.list_all()]
        assert got == ["2026-09-03", "2026-08-24", "2026-08-19"]

    def test_unreadable_timestamps_go_last_and_are_not_dropped(self, fake_store):
        """読めない日時でも記録は消さない。並びの末尾に置く。"""
        self._stored(
            fake_store,
            ["not a date", "2026-09-03T00:12:12+00:00", "", "2026-08-19T10:02:55Z"],
        )
        jobs = job_tracker.list_all()
        assert len(jobs) == 4
        assert [j.submitted_at[:10] for j in jobs[:2]] == ["2026-09-03", "2026-08-19"]
        assert {j.submitted_at for j in jobs[2:]} == {"not a date", ""}
