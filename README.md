# SateAIs for QGIS

Run SAR satellite-image analysis on the [SateAIs](https://docs.spcsft.com)
platform directly from the QGIS map canvas — submit a detection over an area
you draw, track it in the background, and get the result back as a styled map
layer.

<!-- TODO: add a screenshot of the dock (Analysis + Jobs) with a result on the map -->

## What it does

- **Five SAR detections**: ship, oil slick, new building, disappeared building, time-series change.
- **Draw an AOI** on the canvas (or paste WKT); the area you submit is added back as a toggleable outline layer next to the result.
- **Results as map layers**: each result loads as a styled QGIS vector layer, zoomed to its features.
- **Background jobs**: analyses run server-side for minutes to hours — submit, keep working in QGIS, and the Jobs tab polls status for you. Sync recent jobs submitted from the console or CLI.
- **Zero third-party dependencies**: runs on the `urllib` stdlib bundled with QGIS. No `pip install`.

Currently supports Sentinel-1. Requires QGIS 3.34+ (Python 3.9+) and a SateAIs API key.

## Install

**From the QGIS Plugin Repository** (recommended, once published):
*Plugins → Manage and Install Plugins → search "SateAIs"* → Install.

**From a ZIP** (release builds):
Download `sateais_qgis-<version>.zip` from
[Releases](https://github.com/spaceshiftinc/sateais-qgis/releases), then
*Plugins → Manage and Install Plugins → Install from ZIP*.

## Quick start

1. Get an API key from the [SateAIs Console](https://console.spcsft.com).
2. Open the plugin (toolbar icon or *Plugins → SateAIs API for QGIS → Analyze*). On first run a welcome page links to **Settings**, where you paste the key and press **Test Connection**.
3. In **Analysis**, pick a detection type, draw an AOI on the map (or paste WKT), and **Submit**.
4. The **Jobs** tab tracks status automatically. When a job completes, press **Load on Map** to add the result.

## Authentication

The plugin talks only to the production API at `https://api.spcsft.com`. An API
key is required; it is resolved from, in order: the plugin's own setting (entered
in the Settings dialog), the `SATEAIS_API_KEY` environment variable, or
`~/.sateais/credentials` (shared with the `sateais-py` CLI).

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — layers, threading model, HTTP client
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) — dev setup, tests, PR conventions

## Development build

Clone and symlink the plugin folder into your QGIS profile:

```bash
git clone https://github.com/spaceshiftinc/sateais-qgis.git
# macOS
ln -s "$(pwd)/sateais-qgis/sateais_qgis" \
  ~/Library/Application\ Support/QGIS/QGIS3/profiles/default/python/plugins/sateais_qgis
# Linux
# ln -s "$(pwd)/sateais-qgis/sateais_qgis" ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/sateais_qgis
# Windows
# mklink /D %APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\sateais_qgis "%CD%\sateais-qgis\sateais_qgis"
```

Then enable it in *Plugins → Manage and Install Plugins*. See
[docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for tests and lint.

## License

MIT — see [LICENSE](LICENSE).
