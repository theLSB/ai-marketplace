"""Where work logs live, what they remember, and how they grow."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from .sessions import SESSION_ID_IN_NAME, Session

FENCE = "---"
HEADER_KEYS = ("session", "project", "cwd", "branch", "title", "started", "last_turn", "logged")


def worklog_dir() -> Path:
    return Path(os.environ.get("WORKLOG_DIR") or Path.home() / ".claude" / "worklogs")


def reports_dir() -> Path:
    return worklog_dir() / "reports"


def log_name(day: date, project: str, session_id: str) -> str:
    return f"{day.isoformat()}--{project}--{session_id}.md"


def log_path(session: Session, directory: Path | None = None) -> Path:
    directory = worklog_dir() if directory is None else directory
    return directory / log_name(session.day, session.project, session.id)


def find_log(session_id: str, directory: Path | None = None) -> Path | None:
    """A session's existing log, whatever day or project name it was filed under."""
    directory = worklog_dir() if directory is None else directory
    matches = sorted(directory.glob(f"*{session_id}.md"))
    return matches[0] if matches else None


def read_header(path: str | Path) -> dict[str, str]:
    """The frontmatter of a log file as a flat mapping; empty if it has none."""
    header: dict[str, str] = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return header
    if not text.startswith(FENCE):
        return header
    _, _, rest = text.partition(FENCE)
    body, _, _ = rest.partition(f"\n{FENCE}")
    for line in body.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip():
            header[key.strip()] = value.strip()
    return header


def watermark(path: str | Path | None) -> str:
    """The uuid of the last turn already written to this log."""
    return read_header(path).get("last_turn", "") if path else ""


def _render_header(header: dict[str, str]) -> str:
    ordered = [k for k in HEADER_KEYS if header.get(k)]
    extra = [k for k in header if k not in HEADER_KEYS and header.get(k)]
    lines = [f"{key}: {header[key]}" for key in ordered + extra]
    return f"{FENCE}\n" + "\n".join(lines) + f"\n{FENCE}\n"


def _split_body(text: str) -> str:
    if not text.startswith(FENCE):
        return text
    _, _, rest = text.partition(FENCE)
    _, sep, body = rest.partition(f"\n{FENCE}")
    return body.lstrip("\n") if sep else text


def write_entries(path: str | Path, header: dict[str, str], entries: str) -> Path:
    """Append entries to a log, creating it if new, and refresh its frontmatter."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    merged = {**read_header(path), **{k: v for k, v in header.items() if v}}
    merged["logged"] = datetime.now().astimezone().isoformat(timespec="seconds")
    body = _split_body(existing)
    joined = body.rstrip("\n")
    addition = entries.strip("\n")
    if addition:
        joined = f"{joined}\n\n{addition}" if joined else addition
    path.write_text(_render_header(merged) + joined.strip("\n") + "\n", encoding="utf-8")
    return path


@dataclass(frozen=True)
class LogFile:
    path: Path
    header: dict[str, str]

    @property
    def session_id(self) -> str:
        return self.header.get("session") or self.path.stem.rsplit("--", 1)[-1]

    @property
    def day(self) -> date | None:
        match = re.match(r"(\d{4}-\d{2}-\d{2})", self.path.name)
        return date.fromisoformat(match.group(1)) if match else None

    @property
    def project(self) -> str:
        return self.header.get("project", "")


def list_logs(
    directory: Path | None = None,
    since: date | None = None,
    until: date | None = None,
) -> list[LogFile]:
    """Work logs on disk, oldest first, optionally narrowed to a span of days."""
    directory = worklog_dir() if directory is None else directory
    logs = []
    for path in sorted(directory.glob("*.md")):
        log = LogFile(path=path, header=read_header(path))
        day = log.day
        if since and (day is None or day < since):
            continue
        if until and (day is None or day > until):
            continue
        logs.append(log)
    return sorted(logs, key=lambda l: (l.day or date.min, l.path.name))


def unlogged_sessions(sessions: Iterable[Session], directory: Path | None = None) -> list[Session]:
    """Sessions with no log file yet - the ones a report would otherwise miss."""
    directory = worklog_dir() if directory is None else directory
    logged = {
        match.group(0)
        for path in directory.glob("*.md")
        if (match := SESSION_ID_IN_NAME.search(path.stem))
    }
    return [s for s in sessions if s.id not in logged]
