"""Turning a session transcript into the turns and tool calls it records."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

from . import shell

HUMAN_PROMPT_SOURCES = frozenset({"typed", "suggestion_accepted", "queued"})
WRITING_TOOLS = frozenset({"Edit", "Write", "NotebookEdit", "MultiEdit"})
READING_TOOLS = frozenset({"Read", "NotebookRead"})

_PICKUP = re.compile(r"\bpickup\b", re.I)
_COMMAND_NAME = re.compile(r"<command-name>\s*(.*?)\s*</command-name>", re.S)
_COMMAND_ARGS = re.compile(r"<command-args>\s*(.*?)\s*</command-args>", re.S)
_NOISE_BLOCKS = re.compile(
    r"<(system-reminder|local-command-stdout|command-message|command-name|command-args)>.*?</\1>",
    re.S,
)


def read_rows(path: str | Path) -> Iterator[dict[str, Any]]:
    """Every parsable row of a transcript, in file order; unparsable lines are skipped."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


@dataclass(frozen=True)
class ToolCall:
    name: str
    target: str = ""

    def __str__(self) -> str:
        return f"{self.name}: {self.target}" if self.target else self.name


@dataclass
class Turn:
    uuid: str
    ordinal: int
    timestamp: str = ""
    prompt: str = ""
    command: str = ""
    branch: str = ""
    cwd: str = ""
    replies: list[str] = field(default_factory=list)
    tools: list[ToolCall] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    files_read: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "uuid": self.uuid,
            "ordinal": self.ordinal,
            "timestamp": self.timestamp,
            "prompt": self.prompt,
            "command": self.command,
            "branch": self.branch,
            "cwd": self.cwd,
            "replies": self.replies,
            "tools": [str(t) for t in self.tools],
            "files_changed": self.files_changed,
            "files_read": self.files_read,
        }


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(p for p in parts if p)
    return ""


def clean_prompt(raw: str) -> str:
    """The prompt as the user meant it, with injected blocks and reminders removed."""
    return _NOISE_BLOCKS.sub("", raw).strip()


def slash_command(raw: str) -> str:
    """The `/name args` a prompt invoked, or empty if it was ordinary text."""
    name = _COMMAND_NAME.search(raw)
    if not name:
        return ""
    args = _COMMAND_ARGS.search(raw)
    invocation = f"/{name.group(1).lstrip('/')}"
    return f"{invocation} {args.group(1)}".strip() if args and args.group(1) else invocation


def _sent_by_the_user(source: Any, text: str) -> bool:
    """A slash command is recorded without a promptSource, so it is recognised by its content."""
    if source in HUMAN_PROMPT_SOURCES:
        return True
    return source is None and bool(slash_command(text))


def is_pickup(command: str) -> bool:
    """True for the command that picks up a handoff, under any of its plugin-scoped names."""
    return bool(command and _PICKUP.search(command))


def is_human_prompt(row: dict[str, Any]) -> bool:
    """True for rows that carry something the user actually sent."""
    if row.get("type") != "user" or row.get("isSidechain"):
        return False
    if row.get("toolUseResult") or row.get("isMeta"):
        return False
    text = _text_of(row.get("message", {}).get("content"))
    if not _sent_by_the_user(row.get("promptSource"), text):
        return False
    return bool(text.strip())


def _tool_call(name: str, params: dict[str, Any]) -> ToolCall:
    if name in WRITING_TOOLS or name in READING_TOOLS:
        return ToolCall(name, str(params.get("file_path", "")))
    if name == "Bash":
        target = params.get("description") or str(params.get("command", "")).splitlines()[:1]
        return ToolCall(name, target if isinstance(target, str) else (target[0] if target else ""))
    if name in {"Agent", "Task"}:
        return ToolCall(name, str(params.get("description", "")))
    if name == "Skill":
        return ToolCall(name, str(params.get("skill", "")))
    return ToolCall(name, str(params.get("file_path") or params.get("pattern") or ""))


def _add_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def parse_turns(rows: Iterable[dict[str, Any]]) -> list[Turn]:
    """One Turn per user prompt, holding everything that happened before the next prompt."""
    turns: list[Turn] = []
    for row in rows:
        if is_human_prompt(row):
            raw = _text_of(row.get("message", {}).get("content"))
            turns.append(
                Turn(
                    uuid=row.get("uuid", ""),
                    ordinal=len(turns) + 1,
                    timestamp=row.get("timestamp", ""),
                    prompt=clean_prompt(raw),
                    command=slash_command(raw),
                    branch=row.get("gitBranch", "") or "",
                    cwd=row.get("cwd", "") or "",
                )
            )
            continue
        if row.get("type") != "assistant" or row.get("isSidechain") or not turns:
            continue
        turn = turns[-1]
        content = row.get("message", {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text", "").strip():
                turn.replies.append(block["text"].strip())
            elif block.get("type") == "tool_use":
                name = block.get("name", "")
                params = block.get("input") or {}
                turn.tools.append(_tool_call(name, params))
                if name in WRITING_TOOLS:
                    _add_unique(turn.files_changed, str(params.get("file_path", "")))
                elif name in READING_TOOLS:
                    _add_unique(turn.files_read, str(params.get("file_path", "")))
                elif name == "Bash":
                    for path in shell.changed_paths(str(params.get("command", ""))):
                        _add_unique(turn.files_changed, path)
    return turns


def session_meta(rows: Iterable[dict[str, Any]]) -> dict[str, str]:
    """Session-wide facts: its title, where it ran, and when it started and stopped."""
    meta = {"title": "", "cwd": "", "branch": "", "started": "", "ended": "", "version": ""}
    for row in rows:
        if row.get("type") == "ai-title" and row.get("aiTitle"):
            meta["title"] = row["aiTitle"]
        stamp = row.get("timestamp")
        if stamp:
            meta["started"] = meta["started"] or stamp
            meta["ended"] = stamp
        for key, source in (("cwd", "cwd"), ("branch", "gitBranch"), ("version", "version")):
            if row.get(source):
                meta[key] = row[source]
    return meta


def turns_since(turns: list[Turn], uuid: str | None) -> list[Turn]:
    """The turns after the one already logged; all of them if that turn is unknown."""
    if not uuid:
        return list(turns)
    for index, turn in enumerate(turns):
        if turn.uuid == uuid:
            return turns[index + 1 :]
    return list(turns)
