"""What a session costs to run, and when starting a fresh one begins to pay for itself."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Iterator

from . import transcript

MTOK = 1_000_000

PAYBACK_PASSED_MESSAGES = 1.0

CACHE_WRITE_5M = 1.25
CACHE_WRITE_1H = 2.0

_MODEL_SUFFIX = re.compile(r"\[[^\]]*\]$")


@dataclass(frozen=True)
class Prices:
    """Dollars per million tokens."""

    input: float
    output: float
    cache_read: float


PRICES: dict[str, Prices] = {
    "claude-opus-5": Prices(5.0, 25.0, 0.5),
    "claude-opus-4-8": Prices(5.0, 25.0, 0.5),
    "claude-opus-4-7": Prices(5.0, 25.0, 0.5),
    "claude-opus-4-6": Prices(5.0, 25.0, 0.5),
    "claude-sonnet-5": Prices(2.0, 10.0, 0.2),
    "claude-sonnet-4-6": Prices(3.0, 15.0, 0.3),
    "claude-haiku-4-5": Prices(1.0, 5.0, 0.1),
    "claude-fable-5": Prices(10.0, 50.0, 1.0),
    "claude-fable-5-1": Prices(10.0, 50.0, 0.25),
}


def normalise_model(model: str | None) -> str:
    """Model id without the context-window suffix Claude Code appends, e.g. `claude-opus-5[1m]`."""
    return _MODEL_SUFFIX.sub("", (model or "").strip())


def prices_for(model: str | None) -> Prices | None:
    return PRICES.get(normalise_model(model))


def calls_by_message(rows: Iterable[dict[str, Any]]) -> Iterator[tuple[int, str, dict[str, Any]]]:
    """One (messages sent so far, model, usage) triple per API call, in file order.

    A single response is written to the transcript as several rows sharing a `requestId`,
    each repeating the same usage, so counting rows would multiply the spend. Rows without
    a `requestId` were never billed.
    """
    seen: set[str] = set()
    messages = 0
    for row in rows:
        if transcript.is_human_prompt(row):
            messages += 1
            continue
        if row.get("type") != "assistant":
            continue
        request_id = row.get("requestId")
        if not request_id or request_id in seen:
            continue
        message = row.get("message") or {}
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        seen.add(request_id)
        yield messages, normalise_model(message.get("model")), usage


def billed_calls(rows: Iterable[dict[str, Any]]) -> Iterator[tuple[str, dict[str, Any]]]:
    """One (model, usage) pair per API call."""
    for _, model, usage in calls_by_message(rows):
        yield model, usage


def context_tokens(usage: dict[str, Any]) -> int:
    """Everything the model read on this call: the whole conversation as it stood."""
    return (
        int(usage.get("input_tokens") or 0)
        + int(usage.get("cache_creation_input_tokens") or 0)
        + int(usage.get("cache_read_input_tokens") or 0)
    )


def _opening_turn(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows up to the second prompt: everything the session's first turn covered."""
    opening: list[dict[str, Any]] = []
    prompts = 0
    for row in rows:
        if transcript.is_human_prompt(row):
            prompts += 1
            if prompts > 1:
                break
        opening.append(row)
    return opening


def baseline_tokens(rows: Iterable[dict[str, Any]]) -> int:
    """Context a fresh session would start at.

    Normally the first call: system prompt, instructions, skills. A session that picked up a
    handoff starts at the end of that pickup instead, because the document and what it
    references are read before any work begins.
    """
    rows = list(rows)
    calls = list(billed_calls(rows))
    if not calls:
        return 0
    turns = transcript.parse_turns(rows)
    if not turns or not transcript.is_pickup(turns[0].command):
        return context_tokens(calls[0][1])
    opening = list(billed_calls(_opening_turn(rows)))
    return context_tokens(opening[-1][1]) if opening else context_tokens(calls[0][1])


def write_multiplier(usage: dict[str, Any]) -> float | None:
    """Cache-write premium this call paid, or None when it wrote nothing."""
    created = usage.get("cache_creation") or {}
    long_ttl = int(created.get("ephemeral_1h_input_tokens") or 0)
    short_ttl = int(created.get("ephemeral_5m_input_tokens") or 0)
    if not long_ttl and not short_ttl:
        return None
    return CACHE_WRITE_1H if long_ttl >= short_ttl else CACHE_WRITE_5M


def session_write_multiplier(rows: Iterable[dict[str, Any]]) -> float:
    long_ttl = short_ttl = 0
    for _, usage in billed_calls(rows):
        created = usage.get("cache_creation") or {}
        long_ttl += int(created.get("ephemeral_1h_input_tokens") or 0)
        short_ttl += int(created.get("ephemeral_5m_input_tokens") or 0)
    if not long_ttl and not short_ttl:
        return CACHE_WRITE_5M
    return CACHE_WRITE_1H if long_ttl >= short_ttl else CACHE_WRITE_5M


def call_cost(usage: dict[str, Any], model: str | None) -> float | None:
    """Dollars for one API call, or None when the model has no price here."""
    prices = prices_for(model)
    if prices is None:
        return None
    multiplier = write_multiplier(usage) or CACHE_WRITE_5M
    written = int(usage.get("cache_creation_input_tokens") or 0)
    return (
        int(usage.get("input_tokens") or 0) * prices.input
        + int(usage.get("output_tokens") or 0) * prices.output
        + int(usage.get("cache_read_input_tokens") or 0) * prices.cache_read
        + written * prices.input * multiplier
    ) / MTOK


def read_cost_per_call(context: int, model: str | None) -> float | None:
    """What the next turn pays just to re-read the conversation, before it does anything."""
    prices = prices_for(model)
    if prices is None:
        return None
    return context * prices.cache_read / MTOK


def breakeven_calls(current: int, fresh: int, write_mult: float, read_multiple: float) -> float | None:
    """Turns before a fresh session of `fresh` tokens repays the cache it has to rebuild.

    None when it never does, because the fresh session is not smaller.
    """
    if fresh <= 0 or current <= fresh or read_multiple <= 0:
        return None
    return (fresh * write_mult) / ((current - fresh) * read_multiple)


def read_multiple(model: str | None) -> float | None:
    """Cache-read price as a fraction of the input price."""
    prices = prices_for(model)
    if prices is None or not prices.input:
        return None
    return prices.cache_read / prices.input


def message_count(rows: Iterable[dict[str, Any]]) -> int:
    """Prompts the user actually typed. Tool round-trips are not messages."""
    return sum(1 for row in rows if transcript.is_human_prompt(row))


def calls_per_message(rows: Iterable[dict[str, Any]]) -> float | None:
    """How many API calls one message costs in this session.

    Not a constant: tool-heavy work fans a single message out into many more calls than a
    conversation does, so it is measured per session rather than assumed.
    """
    rows = list(rows)
    messages = message_count(rows)
    if not messages:
        return None
    return len(list(billed_calls(rows))) / messages


def breakeven_messages(calls: float | None, per_message: float | None) -> float | None:
    """Break-even expressed in the unit the user thinks in."""
    if calls is None or not per_message:
        return None
    return calls / per_message


def payback_context(fresh: int, write_mult: float, read_multiple: float, per_message: float | None) -> int | None:
    """Context at which a fresh session starts repaying itself inside a single message.

    The break-even formula run backwards: it is the point where `breakeven_messages` falls to
    `PAYBACK_PASSED_MESSAGES`. None when there is nothing to compare against.
    """
    if fresh <= 0 or read_multiple <= 0 or not per_message:
        return None
    gap = (fresh * write_mult) / (PAYBACK_PASSED_MESSAGES * per_message * read_multiple)
    return round(fresh + gap)


def handover_threshold(rows: Iterable[dict[str, Any]]) -> int | None:
    """Context at which a fresh session repays its cache rebuild inside one message."""
    rows = list(rows)
    calls = list(billed_calls(rows))
    if not calls:
        return None
    multiple = read_multiple(calls[-1][0])
    if multiple is None:
        return None
    return payback_context(
        baseline_tokens(rows), session_write_multiplier(rows), multiple, calls_per_message(rows)
    )


def handover_ratio(rows: Iterable[dict[str, Any]], current: int | None = None) -> float | None:
    """How far the session has come toward that threshold; 1.0 means a handover is due.

    Falls when the context does, so a compaction reads as the room it actually buys.
    """
    rows = list(rows)
    threshold = handover_threshold(rows)
    if not threshold:
        return None
    if current is None:
        calls = list(billed_calls(rows))
        current = context_tokens(calls[-1][1]) if calls else 0
    return current / threshold


def messages_since_context(rows: Iterable[dict[str, Any]], context: int | None) -> int | None:
    """Messages sent since the session first grew past `context`, or None if it never has."""
    if context is None:
        return None
    rows = list(rows)
    for at, _, usage in calls_by_message(rows):
        if context_tokens(usage) >= context:
            return max(0, message_count(rows) - at)
    return None


def summarise(rows: Iterable[dict[str, Any]], fresh: int | None = None) -> dict[str, Any]:
    """Current context, what it costs per API call, what the session has cost, and the payback."""
    rows = list(rows)
    calls = list(billed_calls(rows))
    total = 0.0
    priced = unpriced = 0
    unpriced_models: list[str] = []
    for model, usage in calls:
        cost = call_cost(usage, model)
        if cost is None:
            unpriced += 1
            if model and model not in unpriced_models:
                unpriced_models.append(model)
            continue
        priced += 1
        total += cost

    model = calls[-1][0] if calls else ""
    context = context_tokens(calls[-1][1]) if calls else 0
    baseline = baseline_tokens(rows)
    fresh = baseline if fresh is None else fresh
    multiple = read_multiple(model)
    write_mult = session_write_multiplier(rows)
    payback = breakeven_calls(context, fresh, write_mult, multiple) if multiple else None
    per_message = calls_per_message(rows)
    in_messages = breakeven_messages(payback, per_message)
    passed_at = payback_context(fresh, write_mult, multiple, per_message) if multiple else None
    ratio = handover_ratio(rows)

    return {
        "model": model,
        "calls": len(calls),
        "context_tokens": context,
        "baseline_tokens": baseline,
        "fresh_tokens": fresh,
        "read_cost_per_call_usd": read_cost_per_call(context, model),
        "session_cost_usd": round(total, 4) if priced else None,
        "priced_calls": priced,
        "unpriced_calls": unpriced,
        "unpriced_models": unpriced_models,
        "write_multiplier": write_mult,
        "breakeven_calls": round(payback, 1) if payback is not None else None,
        "messages": message_count(rows),
        "calls_per_message": round(per_message, 1) if per_message else None,
        "breakeven_messages": round(in_messages, 2) if in_messages is not None else None,
        "handover_ratio": round(ratio, 3) if ratio is not None else None,
        "messages_overdue": messages_since_context(rows, passed_at),
    }
