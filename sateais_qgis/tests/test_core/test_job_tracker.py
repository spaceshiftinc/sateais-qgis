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
