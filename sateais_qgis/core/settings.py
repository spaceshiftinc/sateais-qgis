"""Persistent plugin settings backed by QSettings.

QSettings stores the API key per OS:
    - Windows: registry
    - macOS:   ~/Library/Preferences/com.SpaceShiftInc.SateAIs.plist
    - Linux:   ~/.config/SpaceShiftInc/SateAIs.conf

Deliberate choice: the key is NOT stored in the QGIS Authentication Manager.
Reading from it triggers the master-password dialog — at QGIS startup, because
job tracking resumes in the background — which is unacceptable first-run UX
(tried and reverted before 0.1.0). The key is a revocable API key scoped to
the user's own account; plaintext QSettings matches what most API-backed QGIS
plugins do.

The API base URL is not stored here: the client always talks to the production
endpoint (``DEFAULT_API_BASE_URL`` in the HTTP layer).
"""

from __future__ import annotations

from qgis.PyQt.QtCore import QSettings

ORG_NAME = "SpaceShiftInc"
APP_NAME = "SateAIs"

# Name of the QSettings entry that stores the user's key. The string is the
# entry name itself, not a credential value.
_SETTINGS_ENTRY = "api_key"  # pragma: allowlist secret


def _settings() -> QSettings:
    return QSettings(ORG_NAME, APP_NAME)


def get_api_key() -> str | None:
    """Return the saved API key, or None if not set."""
    value = _settings().value(_SETTINGS_ENTRY, None, type=str)
    return value or None


def set_api_key(api_key: str) -> None:
    _settings().setValue(_SETTINGS_ENTRY, api_key)


def clear_api_key() -> None:
    _settings().remove(_SETTINGS_ENTRY)


def mask_api_key(api_key: str | None) -> str:
    """Mask an API key for display (e.g. ``sk_live_****abcd``)."""
    if not api_key:
        return "(not set)"
    if len(api_key) <= 12:
        return "***"
    return f"{api_key[:8]}****{api_key[-4:]}"
