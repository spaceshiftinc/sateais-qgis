"""User-facing wording for the pre-run estimate, shared with the MCP map widget.

The MCP widget (sateais-mcp-aws: ``src/widgets/core/format.ts``) is the
reference implementation. Keep the two in lockstep — same sentences, same
rounding rules — so one analysis reads the same in chat and in QGIS.

The rules encoded here all come from real misreadings:

- The estimate is derived from the *requested* area, but billing follows the
  *processed* area. Written as an equality it reads as an overcharge, so a
  number is always shown as an upper bound ("up to ...").
- ``estimated is None`` means "not known before the run", never "free".
- Coverage percentages round *down*: 0.897 shown as "90%" would contradict a
  warning that fires below 90%.
- When the whole area is covered before the run, say nothing — silence is the
  all-clear signal, and a sentence repeated on every run stops being read.
"""

from __future__ import annotations

import math
from typing import Any


def _fmt(value: float, digits: int = 2) -> str:
    return f"{value:,.{digits}f}"


def _known(value: float | None) -> bool:
    """True only for a usable number.

    Mirrors ``Number.isFinite`` in format.ts. NaN and Infinity do reach us:
    ``json.loads`` accepts the ``NaN`` / ``Infinity`` literals by default, and
    a NaN that slips through would otherwise print "up to nan credits" or
    crash the percentage conversion. Unknown is the safe reading — never
    "free", never "fully covered".
    """
    return value is not None and math.isfinite(value)


def credits_label(estimated: float | None) -> str:
    """One-line credit estimate. Mirrors format.ts ``creditsLabel``."""
    if not _known(estimated):
        return "Cost is known only after it runs."
    if estimated == 0:
        return "No credits for this analysis."
    return f"up to {_fmt(estimated)} credits"


def credits_unknown(estimated: float | None) -> bool:
    return not _known(estimated)


def coverage_label(ratio: float | None, past: bool = False) -> str:
    """Coverage sentence. Mirrors format.ts ``coverageLabel``."""
    if not _known(ratio):
        return ""
    if ratio >= 1:
        return "All of your area was analysed" if past else ""
    pct = math.floor(ratio * 100)
    return f"Only {pct}% of your area was analysed" if past else f"{pct}% covered"


def coverage_is_partial(ratio: float | None) -> bool:
    return _known(ratio) and ratio < 1


def balance_note(sufficient: bool | None, balance: float | None) -> str:
    """Show the balance only when it is short — otherwise nobody uses the number."""
    if sufficient is False and _known(balance):
        return f"balance {_fmt(balance)}"
    return ""


# シーンが無い / 前後比較に足りないときにサーバが載せる警告コード
# (orchestrator: shared/scene_lookup.py SCENES_UNAVAILABLE_CODES)。
# 同名のコードで投入後のジョブも失敗するので、事前・事後を 1 つの表で読める。
SCENES_UNAVAILABLE_CODES = frozenset({"SCENE_NOT_FOUND", "INSUFFICIENT_SCENES"})


def scenes_unavailable(warnings: list[dict[str, Any]]) -> bool:
    """True when the server says there is nothing to analyse for these inputs.

    ``coverage`` is absent in this case as well, but for a different reason
    than a catalogue timeout — telling the user "the cost assumes the full
    area" here would be wrong twice over: nothing would be analysed, and the
    fix is the period, not the area.
    """
    return any(w.get("code") in SCENES_UNAVAILABLE_CODES for w in warnings)


# Fixed sentences, verbatim from the widget (format.ts / map.html).
CHECKING = "Checking coverage and cost…"
# format.ts の failureLabel(SCENE_NOT_FOUND) と同じ次の一手
SCENES_UNAVAILABLE_HINT = "Try a nearby date, a longer period, or a wider area."
COVERAGE_UNCHECKED = (
    "The analysed area could not be checked this time. The cost assumes the full area."
)
ESTIMATE_FAILED = "The estimate could not be loaded this time. Edit the area to try again."
SETUP_TITLE = "Set up the analysis"


def area_km2_label(km2: float) -> str:
    """Area in km². Mirrors format.ts ``areaKm2Label``."""
    digits = 0 if km2 >= 100 else 2
    return f"{_fmt(km2, digits)} km²"


def warning_messages(warnings: list[dict[str, Any]]) -> list[str]:
    """Server-provided warning sentences, in order, without the codes."""
    out: list[str] = []
    for w in warnings:
        message = w.get("message")
        if isinstance(message, str) and message:
            out.append(message)
    return out


__all__ = [
    "credits_label",
    "credits_unknown",
    "coverage_label",
    "coverage_is_partial",
    "balance_note",
    "area_km2_label",
    "warning_messages",
    "scenes_unavailable",
    "SCENES_UNAVAILABLE_CODES",
    "SCENES_UNAVAILABLE_HINT",
    "CHECKING",
    "COVERAGE_UNCHECKED",
    "ESTIMATE_FAILED",
    "SETUP_TITLE",
]
