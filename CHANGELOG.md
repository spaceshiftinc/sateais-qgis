# Changelog

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
