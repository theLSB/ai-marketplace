"""Finding session transcripts on disk and describing them."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

SESSION_ID_ENV = "CLAUDE_CODE_SESSION_ID"
SESSION_ID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
SESSION_ID_RE = re.compile(rf"^{SESSION_ID}$")
SESSION_ID_IN_NAME = re.compile(SESSION_ID)


def claude_home() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def projects_root() -> Path:
    return claude_home() / "projects"


def project_slug(cwd: str | Path) -> str:
    """The directory name Claude Code uses under projects/ for a working directory."""
    return re.sub(r"[^a-zA-Z0-9]", "-", str(cwd))


def project_name(slug: str) -> str:
    """Short label for a slug: its last two path-ish segments."""
    parts = [p for p in slug.split("-") if p]
    return "-".join(parts[-2:]) if len(parts) > 2 else (slug.strip("-") or slug)


def current_session_id(env: dict[str, str] | None = None, scratchpad: str | None = None) -> str | None:
    """This session's id, from the environment or from a scratchpad path containing it."""
    env = os.environ if env is None else env
    candidate = env.get(SESSION_ID_ENV, "").strip()
    if SESSION_ID_RE.match(candidate):
        return candidate
    for part in reversed(Path(scratchpad or env.get("TMPDIR", "")).parts):
        if SESSION_ID_RE.match(part):
            return part
    return None


def find_transcript(session_id: str, root: Path | None = None) -> Path | None:
    """Locate a session's transcript without assuming which project it belongs to."""
    root = projects_root() if root is None else root
    matches = sorted(root.glob(f"*/{session_id}.jsonl"))
    return matches[0] if matches else None


@dataclass(frozen=True)
class Session:
    id: str
    path: Path
    slug: str
    modified: datetime

    @property
    def project(self) -> str:
        return project_name(self.slug)

    @property
    def day(self) -> date:
        return self.modified.date()


def session_from_path(path: Path) -> Session:
    stat = path.stat()
    return Session(
        id=path.stem,
        path=path,
        slug=path.parent.name,
        modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).astimezone(),
    )


def list_sessions(
    root: Path | None = None,
    since: date | None = None,
    until: date | None = None,
    project: str | None = None,
) -> list[Session]:
    """Every transcript on this machine, newest last, optionally narrowed by day or project.

    `project` matches any part of a project directory name, so "titan" is enough.
    """
    root = projects_root() if root is None else root
    wanted = project.lower() if project else ""
    found = []
    for path in root.glob("*/*.jsonl"):
        if wanted and wanted not in path.parent.name.lower():
            continue
        if not SESSION_ID_RE.match(path.stem):
            continue
        session = session_from_path(path)
        if since and session.day < since:
            continue
        if until and session.day > until:
            continue
        found.append(session)
    return sorted(found, key=lambda s: s.modified)
