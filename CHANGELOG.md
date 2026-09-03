# Changelog

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-09-03

### Added
- **The cost and the analysed area are shown before you submit.** A job cannot be
  cancelled once it runs, so an estimate afterwards is useless. Drawing an area now
  fetches the credit estimate and the coverage the satellites actually provide, and
  the map shows three things at once: the area you requested, the part that will be
  analysed, and the part with no satellite data. Without the third, "nothing was
  detected here" and "this was never looked at" looked identical.
- The Analysis tab is a three-step checklist (detection type, dates, area), so the
  whole remaining path is visible from the start rather than one missing field at a
  time. Your credit balance, and what the run would leave, sit below the button.
- **Jobs search is back**, matching a fragment of the job id as you type as well as
  the detection type, scene id and dates. Filtering stays instant as the list grows.
- Job cards state the outcome in words ("138 new buildings found" / "No ships
  found") and name every figure, so a timestamp, an area, a cost and a runtime are
  no longer four unlabelled numbers in a row.

### Fixed
- **A plugin-wide change to Python's default URL opener has been removed.** It was
  installed at import time and intercepted requests made by *other* plugins in the
  same QGIS session, silently overriding any proxy or authentication handler they
  had set up.
- **Changing the area while an estimate was in flight could crash QGIS** with
  `RuntimeError: wrapped C/C++ object ... has been deleted` (reported on 3.40).
- **Clearing the drawn area now clears the map.** The same polygon was drawn onto
  two overlays and only one of them was removed.
- Results that are not map layers are named as such instead of failing with a
  parser error, and nothing is downloaded once the format is known.
- Jobs that the server does not know about are removed from the list instead of
  being retried five times and warning on every refresh.
- An area over the per-analysis limit now states both numbers and what to do,
  rather than "the server rejected the request".
- Corrected messages that misdescribed the concurrent-job limit as a request-rate
  limit, and an upload-size limit as the area being too large.
- Submitting no longer overwrites your clipboard or prints a 36-character id.
- An error message pointed at a button that no longer exists.
- A write error while saving a result could surface as `Bad file descriptor`,
  hiding what actually went wrong.

## [0.3.0] - 2026-08-14

### Fixed
- **Getting an API key now leads to the sign-up page.** Both the welcome page and the
  Settings dialog opened the console root, which redirects to the login screen when you
  are not signed in — so anyone told to "create an account" landed on a login form
  instead. They now open the registration page directly.
- The welcome page leads with **Create a free account**; opening Settings is the
  secondary action. Opening Settings does nothing useful before you have a key.

## [0.2.0] - 2026-08-03

### Added
- Jobs cards now show **what was requested** — the analysed period, or the scene for
  scene-id submissions — so a job is identifiable without loading its result. The
  detection type is spelled out ("Time Series" rather than `timeseries`), and the
  card tooltip carries the full job id, scene id and submission time.
- **Sync** now also imports each job's request parameters, which is the only way to
  learn them for jobs submitted from the console, CLI or MCP (the single-job status
  endpoint does not return them). A one-line hint points at Sync while any card is
  still missing its details, and disappears once they are all resolved.
- Search now matches the scene id, the dates and the spelled-out detection type as
  well as the job id.

### Changed
- **Time-series results are drawn by change magnitude and direction** instead of one
  flat colour: a diverging red/blue ramp keyed on `deviation`, matching the colours
  the server and the web viewer use. Unchanged cells become a faint outline rather
  than a fill — they are ~99% of the grid, and filling them buried the findings.
  Each class is a legend entry in the layer panel, so "no significant change" can be
  switched off in one click. Changed cells also carry a constant-size marker, which
  keeps them visible when zoomed out to the whole AOI (a cell is ~50 m across).
- **Time-series detection counts now count changed cells, not grid cells.** The card
  badge, the layer name and the success message previously reported every cell in the
  AOI — two orders of magnitude more than the actual number of changes.
- Time-series results load faster: the per-cell chart series (`upper_chart` /
  `lower_chart`) are dropped before the GeoJSON is handed to QGIS, which cannot render
  them and turned them into unusable attribute-table columns. They were ~88% of the
  payload, and remain available from the API and the web viewer.
- Job cards show a shortened job id; the full id is still one **Copy ID** click (or one
  hover) away.

### Fixed
- Timestamps from the jobs list endpoint (`…Z`) are parsed on Python 3.9, which both
  QGIS LTR 3.34 and 3.40 ship. Synced jobs previously showed a raw ISO string instead
  of a date, and were never dropped by the 30-day retention.
- The background job poll is now cancelled when the panel is torn down (plugin
  unload / QGIS close). It used to keep running into QGIS's own shutdown, where a
  task thread finishing after the auth manager has been destroyed can trip a
  use-after-free inside QGIS itself. That defect is upstream — this only stops the
  plugin from keeping the thread pool alive long enough to hit it.
- Jobs imported by **Sync** now support AOI preview and the AOI outline layer. Their
  area was never stored, so clicking a console/CLI/MCP-submitted job did nothing.
- A job submitted while the analysis-type selector was then changed was recorded under
  the newly selected type, which mislabelled it and styled its result wrongly.
- Server-supplied text (error messages, scene ids) is now rendered as plain text, so
  markup in it can no longer be interpreted by the card labels.

## [0.1.3] - 2026-07-28

### Changed
- Support QGIS 4.x: raised `qgisMaximumVersion` to 4.99 so the plugin appears in
  the QGIS 4 Plugin Manager. The code itself has been Qt6-ready since 0.1.1
  (scoped enums, `exec()`), so no code changes were needed.

## [0.1.2] - 2026-07-22

### Changed
- Plugin contact email is now `osgeo@spcsft.com` (repository correspondence and
  author contact consolidated on one monitored address).

## [0.1.1] - 2026-07-22

### Changed
- Resolve the plugin repository's automated security-scanner findings: intentional
  best-effort cleanups now use `contextlib.suppress`, HTTP requests go through the
  auth-stripping opener directly, and the decorative starfield no longer uses the
  `random` module. No behavioural changes.
- Qt6-ready scoped-enum syntax (and `exec()`) across the UI — forward-compatible
  with QGIS 4, identical behaviour on QGIS 3.34+.

## [0.1.0] - 2026-07-16

First public release.

### Added
- Run five SAR detections from QGIS — **ship, oil slick, new building, disappeared building, time series** — through the SateAIs API.
- Draw an AOI on the map canvas or paste WKT (EPSG:4326). The submitted AOI is added as a **toggleable outline layer** next to the result, so it can be hidden when it overlaps detections.
- Results load as **styled QGIS vector layers**, one style per detection type, zoomed to the features.
- **Jobs tab**: background status polling that recovers gracefully (a job is marked *Unknown* and can be re-armed with **Refresh** after repeated poll failures or 24 h), **Sync** to import recent server-side jobs (`GET /api/v1/jobs`), and search.
- **Welcome page** with guided API-key setup when no key is configured (key from <https://console.spcsft.com>).
- **Settings dialog** with Test Connection, run off the UI thread.
- **Zero third-party dependencies** — runs on the `urllib` stdlib bundled with QGIS. Python 3.9+ for QGIS LTR 3.34 / 3.40.

### Security
- API paths percent-encode `job_id` and analysis-type segments.
- `Authorization` / `Cookie` headers are stripped when following a 302 redirect to a different host (results are fetched via S3 presigned URLs).
- Only `http(s)` API base URLs are accepted.
- Malformed API and persisted-job payloads are rejected defensively instead of raising raw errors.
- Polygon WKT is never logged verbatim (length only), keeping large geometries out of the QGIS log.
