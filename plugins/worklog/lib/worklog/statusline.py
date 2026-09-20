"""The status line: what this session costs to keep going, and when a fresh one repays itself.

Claude Code pipes the session payload in as JSON. Anything that cannot be worked out is left
out of the line rather than guessed at, and any failure prints nothing: a status line must
never become the loudest thing on screen.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import cost, transcript

YELLOW_FROM = 60
RED_FROM = 85

RATE_LIMIT_WINDOWS = (("five_hour", "5h"), ("seven_day", "7d"))

GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"


def tokens(count: int) -> str:
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count // 1_000}k"
    return str(count)


def share_colour(percent: int, yellow_from: int = YELLOW_FROM, red_from: int = RED_FROM) -> str:
    """The colour for a gauge that is `percent` full. A gauge can pass its own two marks."""
    if percent >= red_from:
        return RED
    return YELLOW if percent >= yellow_from else GREEN


def session_rows(path: str | None):
    """The transcript's rows, or None when there is nothing billed to read."""
    if not path or not Path(path).exists():
        return None
    rows = list(transcript.read_rows(path))
    return rows if any(True for _ in cost.billed_calls(rows)) else None


def handover_label(ratio: float) -> str:
    """How far the session is from the point a fresh one pays for itself.

    Once the threshold is past the figure keeps climbing, so it says how far past.
    """
    percent = round(ratio * 100)
    if ratio >= 1.0:
        return f"{RED}handover due · {percent}%{RESET}"
    colour = share_colour(percent)
    return f"{colour}handover {percent}%{RESET}"


def context_of(window: dict) -> int:
    total = window.get("total_input_tokens")
    if isinstance(total, int) and total > 0:
        return total
    usage = window.get("current_usage")
    return cost.context_tokens(usage) if isinstance(usage, dict) else 0


def context_label(context: int, share: float | None) -> str:
    """How full the window is, coloured by how little room is left.

    The colour follows the percentage as printed, so the number and its colour agree.
    """
    if share is None:
        return f"context {tokens(context)}"
    percent = round(share)
    colour = share_colour(percent)
    return f"{colour}context {percent}% ({tokens(context)}){RESET}"


def rate_limit_labels(rate_limits: object) -> list[str]:
    """One segment per usage window the API reported: the five-hour first, then the week.

    Both blocks are optional, so a missing or unreadable one is dropped rather than costing
    the other its place on the line.
    """
    if not isinstance(rate_limits, dict):
        return []
    labels = []
    for key, name in RATE_LIMIT_WINDOWS:
        window = rate_limits.get(key)
        share = window.get("used_percentage") if isinstance(window, dict) else None
        if isinstance(share, bool) or not isinstance(share, (int, float)):
            continue
        percent = round(share)
        colour = share_colour(percent)
        labels.append(f"{colour}{name} {percent}%{RESET}")
    return labels


def build_line(payload: dict) -> str:
    window = payload.get("context_window") or {}
    model = (payload.get("model") or {}).get("id")
    context = context_of(window)
    parts = []

    if context:
        share = window.get("used_percentage")
        size = window.get("context_window_size")
        if not isinstance(share, (int, float)) and isinstance(size, int) and size > 0:
            share = context * 100 / size
        parts.append(context_label(context, share if isinstance(share, (int, float)) else None))

    parts.extend(rate_limit_labels(payload.get("rate_limits")))

    per_call = cost.read_cost_per_call(context, model) if context else None
    if per_call is not None:
        parts.append(f"${per_call:,.2f}/call")

    spent = (payload.get("cost") or {}).get("total_cost_usd")
    if isinstance(spent, (int, float)):
        parts.append(f"${spent:,.2f}")

    rows = session_rows(payload.get("transcript_path")) if cost.read_multiple(model) else None
    ratio = cost.handover_ratio(rows, context) if rows is not None and context else None
    if ratio is not None:
        parts.append(handover_label(ratio))

    return " · ".join(parts)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        line = build_line(payload)
    except Exception:
        return 0
    if line:
        print(line)
    return 0
