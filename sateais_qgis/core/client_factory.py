"""Client factory and authentication helpers for the QGIS plugin.

API key resolution order:
    1. QSettings (SpaceShiftInc/SateAIs/api_key) -- the GUI's primary store
    2. environment variable SATEAIS_API_KEY
    3. ~/.sateais/credentials -- shared with the sateais-py CLI
"""

from __future__ import annotations

import os
from pathlib import Path

from . import settings
from .api import (
    APIError,
    AuthenticationError,
    Client,
    NotFoundError,
    PermissionDeniedError,
)

CREDENTIALS_FILE = Path.home() / ".sateais" / "credentials"


class AuthNotConfiguredError(Exception):
    """Raised when no API key can be resolved."""


def _warn_if_credentials_file_world_readable() -> None:
    """Surface a one-line warning when the credentials file is too permissive.

    POSIX-only; Windows reports a limited mode and is skipped. The plugin
    keeps using the file either way — refusing it could break users who
    have a working credential setup.
    """
    if not hasattr(os, "geteuid"):
        return
    try:
        mode = CREDENTIALS_FILE.stat().st_mode & 0o777
    except OSError:
        return
    if mode & 0o077 == 0:
        return
    try:
        from qgis.core import Qgis, QgsMessageLog

        QgsMessageLog.logMessage(
            f"Credentials file {CREDENTIALS_FILE} is group/other readable "
            f"(mode={mode:o}); recommend `chmod 600` to protect your API key.",
            "SateAIs",
            Qgis.Warning,
        )
    except Exception:  # noqa: BLE001
        # QGIS not available (e.g. tests, CLI inspection) — silently skip.
        pass


def _read_credentials_file() -> str | None:
    """Read the API key from ~/.sateais/credentials.

    Supports the JSON format written by `sateais login` (``{"api_key": "..."}``)
    and a legacy plain-text format where the whole file is the API key.

    On POSIX systems we log a warning when the file is group/other readable
    (recommended mode is 0600) but still return the key, so a user-friendly
    plugin doesn't lock them out of a slightly-misconfigured environment.
    """
    if not CREDENTIALS_FILE.exists():
        return None
    try:
        _warn_if_credentials_file_world_readable()
        text = CREDENTIALS_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    if text.startswith("{"):
        import json

        try:
            data = json.loads(text)
            if isinstance(data, dict):
                key = data.get("api_key")
                if isinstance(key, str) and key:
                    return key
        except json.JSONDecodeError:
            pass
    return text


def _resolve_api_key(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    from_settings = settings.get_api_key()
    if from_settings:
        return from_settings
    from_env = os.environ.get("SATEAIS_API_KEY")
    if from_env:
        return from_env
    return _read_credentials_file()


def has_api_key() -> bool:
    """Return True if an API key can be resolved from any source."""
    return _resolve_api_key(None) is not None


def build_client(api_key: str | None = None) -> Client:
    """Build a Client, resolving the API key if not given.

    Raises:
        AuthNotConfiguredError: If no API key can be resolved.
    """
    resolved = _resolve_api_key(api_key)
    if not resolved:
        raise AuthNotConfiguredError(
            "No API key configured. Please register one via the Settings dialog."
        )
    return Client(api_key=resolved)


def test_connection(api_key: str | None = None) -> tuple[bool, str]:
    """Verify the API key with a `GET /me` request.

    Returns:
        ``(success, message)``. The message is meant for direct display to the
        user; internal endpoint names, HTTP codes and server logs are never
        exposed.
    """
    resolved_key = api_key or settings.get_api_key()

    if not resolved_key:
        return False, "Please enter an API key."

    client = Client(api_key=resolved_key)
    try:
        me = client.me()
        email = me.get("email")
        credits = me.get("credits") or {}
        balance = credits.get("balance")
        if email and balance is not None:
            return True, f"Connected as {email} ({balance:,.0f} credits remaining)."
        if email:
            return True, f"Connected as {email}."
        return True, "Connected."
    except AuthenticationError:
        return False, "Invalid API key. Please check the key issued in the console."
    except PermissionDeniedError:
        return False, (
            "Your account does not have access to this endpoint. Please contact support."
        )
    except NotFoundError:
        return False, "Could not reach the server. Please try again shortly."
    except APIError:
        return False, "The server is not responding. Please try again in a moment."
    except Exception:  # noqa: BLE001
        return False, "No network connection. Please check your internet connection."
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass
