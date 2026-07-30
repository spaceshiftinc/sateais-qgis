# Changelog

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
