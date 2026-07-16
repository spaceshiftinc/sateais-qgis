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
uv run --no-project --with ruff ruff format .
uv run --no-project --with ruff ruff check .
```

## Branches and pull requests

- Default branch: `develop`. All changes go through a feature branch + PR,
  including small fixes.
- `main` is the release branch. It only advances through release PRs from
  `develop` (see [Release](#release)).
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

1. Bump `version=` in `sateais_qgis/metadata.txt` and move the CHANGELOG
   *Unreleased* entries under the new version heading with the release date
   (mirror the summary in the `changelog=` block of `metadata.txt`).
2. Open a release PR from `develop` to `main` and merge it with a **merge
   commit** — never squash or rebase it, so `main` keeps the exact commits of
   `develop` and the branches never diverge.
3. Tag the merge commit on `main` as `vX.Y.Z` and push the tag.
   [release.yml](../.github/workflows/release.yml) builds the plugin ZIP and
   attaches it to the GitHub Release (creating the release if it does not
   exist yet). Release tags are protected: they cannot be moved or deleted.
4. Upload the CI-built ZIP from the GitHub Release to the
   [QGIS Plugin Repository](https://plugins.qgis.org/plugins/).
