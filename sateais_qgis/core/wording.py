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
import re
from typing import Any

from . import job_summary


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


# 地図の3色の呼び名。全体（Requested）が2つ（Covered / Not covered）に分かれる、
# という構造が語だけで読める組を選ぶ。カード上部の文が既に "97% covered" なので、
# 同じ語が文と凡例の両方で効く。「なぜ covered でないか」は凡例では言わない
LEGEND_REQUESTED = "Requested"
LEGEND_COVERED = "Covered"
LEGEND_NOT_COVERED = "Not covered"

# Fixed sentences, verbatim from the widget (format.ts / map.html).
CHECKING = "Checking coverage and cost…"
# format.ts の failureLabel(SCENE_NOT_FOUND) と同じ次の一手
SCENES_UNAVAILABLE_HINT = "Try a nearby date, a longer period, or a wider area."
COVERAGE_UNCHECKED = (
    "The analysed area could not be checked this time. The cost assumes the full area."
)
ESTIMATE_FAILED = "The estimate could not be loaded this time. Edit the area to try again."
SETUP_TITLE = "Set up the analysis"


# 面積上限は endpoint ごとに違い、値を返す API も無い。プラグインに数値を
# 書き写すとサーバの変更で黙って嘘になるので、超過したときにサーバが返す文
# (docs/API.md: "Polygon area (52.6 km²) exceeds 50 km² limit for endpoint …")
# から数値だけを取り出して、こちらの言葉に組み直す
_AREA_LIMIT_RE = re.compile(
    r"area\s*\(([\d.,]+)\s*km\S*\)\s*exceeds\s*([\d.,]+)\s*km",
    re.IGNORECASE,
)


def area_limit_reason(message: str | None) -> str:
    """Rewrite the server's area-limit rejection, or "" when it is not one.

    The raw sentence names an internal endpoint id, and "the server rejected the
    request" alone does not say what to change. Both numbers are what make it
    actionable: how big the area is, and how big it may be.
    """
    if not message:
        return ""
    match = _AREA_LIMIT_RE.search(message)
    if not match:
        return ""
    actual, limit = match.group(1), match.group(2)
    return (
        f"This area is {actual} km², over the {limit} km² limit for this analysis. "
        "Draw a smaller area, or split it into several runs."
    )


def failure_label(code: str | None, message: str | None) -> str:
    """Why a job failed, in the user's terms. Mirrors format.ts ``failureLabel``.

    **The server's own message is never shown.** What comes back looks like
    ``Invalid ASF scene_id format (path traversal guard): 'S1A_IW_SLC__…'`` —
    the guard is our implementation detail, and the user merely passed an SLC
    scene id. Say what went wrong and what to do next, nothing else.
    """
    raw = message or ""
    # 結果は 30 日で消える。実行自体は成功しているので「失敗」とは書かない
    if code == "GONE" or re.search(r"\bGONE\b|retention period", raw, re.IGNORECASE):
        return (
            "This result was deleted after the 30-day retention period. "
            "Run the analysis again to get it back."
        )
    over_limit = area_limit_reason(raw)
    if over_limit:
        return over_limit
    if re.search(r"scene_id format", raw, re.IGNORECASE):
        if re.search(r"_IW_SLC_", raw, re.IGNORECASE):
            return (
                "That scene is an SLC product. Ship detection needs a GRD scene — "
                "its name contains _IW_GRDH_."
            )
        return (
            "That scene name is not a Sentinel-1 GRD granule. "
            "Look it up on ASF Search with File Type set to GRD."
        )
    if code == "SCENE_NOT_FOUND":
        return "No satellite scene was found for that area and date. " + SCENES_UNAVAILABLE_HINT
    if code == "INSUFFICIENT_SCENES":
        return "There were not enough scenes to compare. " + SCENES_UNAVAILABLE_HINT
    if code == "INSUFFICIENT_CREDITS":
        return "There were not enough credits to run this."
    if code == "VALIDATION_ERROR":
        return "This request could not be run as written."
    return "This run did not finish. Nothing was charged."


def area_km2_label(km2: float) -> str:
    """Area in km². Mirrors format.ts ``areaKm2Label``."""
    digits = 0 if km2 >= 100 else 2
    return f"{_fmt(km2, digits)} km²"


def took_label(submitted_at: str | None, completed_at: str | None) -> str:
    """How long the run took. Mirrors format.ts ``tookLabel``."""
    if not submitted_at or not completed_at:
        return ""
    # 日時の読み方は job_summary に 1 箇所だけ。ここで独自に fromisoformat を
    # 呼んでいたため、小数 5 桁の記録では所要時間がまるごと空になっていた
    start = job_summary.parse_iso8601(submitted_at)
    end = job_summary.parse_iso8601(completed_at)
    if start is None or end is None:
        return ""
    seconds = round((end - start).total_seconds())
    if seconds < 0:
        return ""
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m {seconds % 60}s"
    return f"{minutes // 60}h {minutes % 60}m"


def format_credits(value: float) -> str:
    """A credit figure on its own, at the rounding used everywhere else."""
    return _fmt(value)


def job_meta_fields(
    submitted_display: str,
    area_sqkm: float | None,
    credits_used: float | None,
    took: str,
) -> list[tuple[str, str]]:
    """Captioned figures for a job row: ``[("Submitted", "2026-09-03 03:00"), …]``.

    A unit is not a caption. ``196 km²`` says what it measures, but ``3m 31s``
    beside a timestamp could be a queue wait or a run time, and ``1.96`` could be
    spent or remaining — so each value is named. Unknown values are dropped
    rather than shown as a caption with a blank or a zero beside it.
    """
    fields: list[tuple[str, str]] = []
    if submitted_display:
        fields.append(("Submitted", submitted_display))
    if _known(area_sqkm):
        fields.append(("Area", area_km2_label(area_sqkm)))
    if _known(credits_used):
        fields.append(("Cost", "free" if credits_used == 0 else f"{_fmt(credits_used)} credits"))
    if took:
        fields.append(("Took", took))
    return fields


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
    "took_label",
    "format_credits",
    "job_meta_fields",
    "area_limit_reason",
    "failure_label",
    "warning_messages",
    "scenes_unavailable",
    "SCENES_UNAVAILABLE_CODES",
    "SCENES_UNAVAILABLE_HINT",
    "LEGEND_REQUESTED",
    "LEGEND_COVERED",
    "LEGEND_NOT_COVERED",
    "CHECKING",
    "COVERAGE_UNCHECKED",
    "ESTIMATE_FAILED",
    "SETUP_TITLE",
]
