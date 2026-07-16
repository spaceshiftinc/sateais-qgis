# Contributing

## Development setup

1. Clone the repo and symlink `sateais_qgis/` into your QGIS plugin directory
   (see the [README](../README.md#installation-development-build) for
   per-platform commands).
2. Enable **SateAIs API for QGIS** in *Plugins → Manage and Install Plugins*.
3. Install the **Plugin Reloader** plugin — after editing code, reload
   `sateais_qgis` from its toolbar instead of restarting QGIS.

No build step and no third-party runtime dependencies: the plugin runs on the
Python stdlib bundled with QGIS. Keep it that way — QGIS plugins cannot
`pip install`, so any new `import` outside the stdlib / PyQGIS must be
vendored, and we deliberately vendor nothing.

## Running the tests

```bash
# Full suite (workers/core tests are skipped automatically without PyQGIS)
uv run --no-project --with pytest pytest sateais_qgis/tests/

# API-client tests against Python 3.9 (oldest interpreter shipped with QGIS LTR)
uv run --no-project --with pytest --python 3.9 pytest sateais_qgis/tests/test_api/
```

Tests under `test_workers/` and `test_core/` need PyQGIS; run them from a
Python that can `import qgis` (e.g. the interpreter of a QGIS install) to get
full coverage locally.

## Lint / format

Run both before every push — CI-equivalent checks:

```bash
uv run --no-project --with ruff ruff format sateais_qgis/
uv run --no-project --with ruff ruff check sateais_qgis/
```

## Branches and pull requests

- Default branch: `develop`. All changes go through a feature branch + PR,
  including small fixes.
- PR titles follow the conventional prefixes used in the log:
  `feat: …` / `fix: …` / `chore: …` / `docs: …`.
- Update the **Unreleased** section of [CHANGELOG.md](../CHANGELOG.md) in the
  same PR as the change it describes.

## Coding notes

- **User-facing text is production quality**: never surface raw server
  messages, HTTP codes, or internal endpoint names. Map API errors to the
  message tables in `gui/widgets/analysis_panel.py` / `jobs_panel.py`.
- **Threading**: follow the worker lifecycle pattern in
  [ARCHITECTURE.md](ARCHITECTURE.md#threading-model). Never destroy a running
  `QThread`; never touch widgets from a worker thread — communicate through
  signals only.
- **Numbers drift**: area limits, inference times and prices live in the API
  docs (docs.spcsft.com), not in this codebase. Link, don't copy.

## Release

1. Bump `version=` in `sateais_qgis/metadata.txt`.
2. Move the CHANGELOG *Unreleased* entries under the new version heading.
3. Zip the `sateais_qgis/` directory and upload to the QGIS Plugin Repository.
