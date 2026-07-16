# Architecture

How the SateAIs QGIS plugin is put together, and why.

## Overview

The plugin is a thin client for the SateAIs REST API. Analyses run
server-side and take minutes to hours, so everything is built around an
asynchronous job model:

```
Analysis tab                 Jobs tab
    │ submit                     │
    ▼                            ▼
POST /api/v1/analyze/{type}  GET /api/v1/jobs/{id}   (poll every 30 s)
    │                            │
    │ job_id                     │ status: pending → processing → completed/failed
    ▼                            ▼
job_tracker (QSettings)      GET /api/v1/jobs/{id}/result.geojson
                                 │ (302 → S3 presigned URL)
                                 ▼
                             QGIS vector layer (styled per detection type)
```

## Layers

```
sateais_qgis/
├── core/          # QGIS-free where possible; unit-testable in plain Python
│   ├── api/       #   urllib-based HTTP client, typed errors, request/response types
│   ├── client_factory.py  # API-key resolution + Client construction
│   ├── settings.py        # persistent settings (auth manager / QSettings)
│   ├── job_tracker.py     # submitted-job persistence (QSettings JSON)
│   ├── layer_loader.py    # GeoJSON → styled QgsVectorLayer
│   └── geometry_adapter.py# canvas CRS → EPSG:4326 WKT + geodesic area
├── workers/       # background execution (see "Threading model")
└── gui/           # PyQt widgets: dock, tabs, dialogs, cards
```

Dependency direction is strictly `gui → workers → core`. Nothing in `core`
imports from `gui` or `workers`.

## HTTP client (`core/api/`)

- **Zero third-party dependencies**: QGIS plugins cannot `pip install`, so the
  client uses only `urllib` from the stdlib bundled with QGIS.
- **Typed errors**: HTTP statuses map to an exception hierarchy
  (`AuthenticationError`, `InsufficientCreditsError`, `ServerError`, …) in
  `core/api/errors.py`; the UI maps those to user-facing messages and never
  shows raw server text.
- **Timeouts**: `urllib` wraps socket timeouts in `URLError`, so the client
  inspects `URLError.reason` to classify timeouts separately from connection
  errors.
- **Redirect safety**: result endpoints 302-redirect to S3 presigned URLs.
  A custom redirect handler strips the `Authorization` header on cross-origin
  redirects (S3 rejects requests carrying two auth mechanisms).

## Authentication

API keys are resolved in this order (`core/client_factory.py`):

1. QSettings (`SpaceShiftInc/SateAIs/api_key`) — the GUI's store
   (`core/settings.py`). Deliberately **not** the QGIS Authentication
   Manager: reading from it triggers the master-password dialog at QGIS
   startup (job tracking resumes in the background), which is unacceptable
   first-run UX. Tried and reverted before 0.1.0.
2. Environment variable `SATEAIS_API_KEY`.
3. `~/.sateais/credentials` — shared with the `sateais-py` CLI.

When no key resolves, the Analysis tab shows a welcome page that links to the
console and the Settings dialog instead of the submit form.

## Threading model

Two mechanisms, chosen by lifetime:

| Work | Mechanism | Why |
|---|---|---|
| Job polling (minutes–hours, shared) | `QgsTask` (`workers/poll_job_task.py`) | Long-lived, cancellable through the QGIS task manager, visible to QGIS |
| Submit / result fetch / connection test (one-shot) | `QThread` workers | Short blocking HTTP calls that just need to stay off the UI thread |

### Polling escape hatches

`PollJobsTask` never polls forever: a job is abandoned (status → `unknown`,
user notified, Refresh re-arms tracking) after `MAX_CONSECUTIVE_POLL_ERRORS`
failed polls in a row or `MAX_TRACKING_SECONDS` (24 h) of tracking. Successful
polls reset the error budget.

### One-shot worker lifecycle (`workers/lifecycle.py`)

Destroying a running `QThread` aborts the whole QGIS process, so every
one-shot worker follows the same pattern:

1. created per request with the owning widget as Qt parent;
2. the owner's slot is **disconnected as soon as the completion signal fires**
   (a finished worker can never re-enter a handler);
3. `finished → deleteLater` collects the thread object;
4. if the owner is torn down while the worker still runs, `detach_worker()`
   re-parents it to a module-level registry and lets it wind down on its own.

## Job persistence

`core/job_tracker.py` stores submitted jobs as JSON in QSettings so the Jobs
tab survives QGIS restarts. Entries older than the server-side retention
window (30 days) are dropped at plugin start.

## Testing

- `sateais_qgis/tests/test_api/` — pure-Python tests with `urllib.request.urlopen`
  mocked; run anywhere.
- `sateais_qgis/tests/test_workers/`, `test_core/` — require PyQGIS and are
  skipped automatically (`pytest.mark.skipif`) when `qgis` is not importable.

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to run them.
