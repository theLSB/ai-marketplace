"""Command line entry point used by the session-logger and work-report skills."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from . import cost, logs, sessions, transcript


def _resolve_session(session_id: str | None) -> sessions.Session:
    session_id = session_id or sessions.current_session_id()
    if not session_id:
        raise SystemExit("no session id: pass --session, or set CLAUDE_CODE_SESSION_ID")
    path = sessions.find_transcript(session_id)
    if not path:
        raise SystemExit(f"no transcript found for session {session_id}")
    return sessions.session_from_path(path)


def _span(args: argparse.Namespace) -> tuple[date | None, date | None]:
    since = date.fromisoformat(args.since) if args.since else None
    until = date.fromisoformat(args.until) if args.until else None
    if args.days:
        since = date.today() - timedelta(days=args.days - 1)
    return since, until


def _clip(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit].rstrip() + f" ... [+{len(text) - limit} chars]"


def cmd_digest(args: argparse.Namespace) -> int:
    session = _resolve_session(args.session)
    rows = list(transcript.read_rows(session.path))
    meta = transcript.session_meta(rows)
    turns = transcript.parse_turns(rows)
    existing = logs.find_log(session.id)
    mark = "" if args.all else logs.watermark(existing)
    pending = transcript.turns_since(turns, mark)
    payload = {
        "session": {
            "id": session.id,
            "project": session.project,
            "slug": session.slug,
            "transcript": str(session.path),
            "log": str(existing or logs.log_path(session)),
            "log_exists": bool(existing),
            "watermark": mark,
            "head_turn": turns[-1].uuid if turns else "",
            "turns_total": len(turns),
            "turns_pending": len(pending),
            **meta,
        },
        "turns": [],
    }
    for turn in pending:
        item = turn.as_dict()
        item["prompt"] = _clip(item["prompt"], args.max_prompt)
        item["replies"] = [_clip(r, args.max_reply) for r in item["replies"]]
        payload["turns"].append(item)
    json.dump(payload, sys.stdout, indent=1, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def cmd_append(args: argparse.Namespace) -> int:
    session = _resolve_session(args.session)
    rows = list(transcript.read_rows(session.path))
    meta = transcript.session_meta(rows)
    turns = transcript.parse_turns(rows)
    entries = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    if not entries.strip():
        raise SystemExit("nothing to append: entries were empty")
    if args.keep_watermark:
        last_turn = ""
    else:
        last_turn = args.last_turn or (turns[-1].uuid if turns else "")
    header = {
        "session": session.id,
        "project": session.project,
        "cwd": meta["cwd"],
        "branch": meta["branch"],
        "title": meta["title"],
        "started": meta["started"],
        "last_turn": last_turn,
    }
    target = logs.find_log(session.id) or logs.log_path(session)
    written = logs.write_entries(target, header, entries)
    recorded = logs.watermark(written)
    print(f"{written} (last_turn {recorded[:8] or 'none'})")
    return 0


def cmd_sessions(args: argparse.Namespace) -> int:
    since, until = _span(args)
    found = sessions.list_sessions(since=since, until=until, project=args.project)
    if args.unlogged:
        found = logs.unlogged_sessions(found)
    for session in found:
        log = logs.find_log(session.id)
        rows = list(transcript.read_rows(session.path))
        meta = transcript.session_meta(rows)
        turns = transcript.parse_turns(rows)
        print(
            f"{session.day} {session.id}  {'logged  ' if log else 'unlogged'}  "
            f"{len(turns):>3} turns  {session.project:<28} {meta['title'] or '(untitled)'}"
        )
    if not found:
        print("(no sessions match)")
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    since, until = _span(args)
    found = logs.list_logs(since=since, until=until)
    for log in found:
        print(f"{log.day} {log.project:<28} {log.header.get('title', '') or '(untitled)'}")
        print(f"          {log.path}")
    if not found:
        print("(no work logs match)")
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    session = _resolve_session(args.session)
    print(logs.find_log(session.id) or logs.log_path(session))
    return 0


def cmd_cost(args: argparse.Namespace) -> int:
    session = _resolve_session(args.session)
    rows = list(transcript.read_rows(session.path))
    report = cost.summarise(rows, fresh=args.fresh)
    if args.json:
        json.dump({"session": session.id, **report}, sys.stdout, indent=1)
        sys.stdout.write("\n")
        return 0

    def money(value: float | None) -> str:
        return "n/a" if value is None else f"${value:,.2f}"

    print(f"session  {session.id[:8]}  {report['model'] or '(none)'}  {report['calls']} calls")
    print(f"context  {report['context_tokens']:,} tokens")
    print(f"re-read  {money(report["read_cost_per_call_usd"])} per API call, before the call does anything")
    print(f"spent    {money(report['session_cost_usd'])}")
    payback = report["breakeven_calls"]
    fresh = report["fresh_tokens"]
    if payback is None:
        print(f"handoff  never pays off against a fresh {fresh:,}-token session")
    else:
        in_messages = report["breakeven_messages"]
        unit = f"{in_messages:g} messages" if in_messages is not None else f"{payback:g} API calls"
        print(f"handoff  pays back after {unit}, against a fresh {fresh:,}-token session")
        if in_messages is not None:
            print(f"         ({payback:g} API calls, at {report['calls_per_message']:g} calls per message here)")
    ratio = report["handover_ratio"]
    if ratio is not None:
        print(f"readiness {ratio * 100:.0f}% of the way to a worthwhile handover")
    if report["unpriced_models"]:
        print(f"note     no price on file for {', '.join(report['unpriced_models'])}; dollars exclude them")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="worklog", description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)

    digest = subs.add_parser("digest", help="turns of a session not yet written to its work log")
    digest.add_argument("--session", help="session id (default: the current session)")
    digest.add_argument("--all", action="store_true", help="ignore the watermark, emit every turn")
    digest.add_argument("--max-prompt", type=int, default=4000, help="clip each prompt (0 = no clip)")
    digest.add_argument("--max-reply", type=int, default=2500, help="clip each reply (0 = no clip)")
    digest.set_defaults(func=cmd_digest)

    append = subs.add_parser("append", help="add written entries to a session's work log")
    append.add_argument("--session", help="session id (default: the current session)")
    append.add_argument("--file", help="markdown file holding the entries (default: stdin)")
    append.add_argument("--last-turn", help="watermark to record (default: newest turn)")
    append.add_argument(
        "--keep-watermark",
        action="store_true",
        help="leave the watermark where it is, for a note that logs no new turns",
    )
    append.set_defaults(func=cmd_append)

    for name, help_text, func in (
        ("sessions", "transcripts on this machine and whether they are logged", cmd_sessions),
        ("logs", "work logs on disk", cmd_logs),
    ):
        sub = subs.add_parser(name, help=help_text)
        sub.add_argument("--since", help="first day to include, YYYY-MM-DD")
        sub.add_argument("--until", help="last day to include, YYYY-MM-DD")
        sub.add_argument("--days", type=int, help="include the last N days, today counting as one")
        if name == "sessions":
            sub.add_argument("--project", help="restrict to projects whose directory name contains this")
            sub.add_argument("--unlogged", action="store_true", help="only sessions with no log")
        sub.set_defaults(func=func)

    where = subs.add_parser("path", help="work log path for a session")
    where.add_argument("--session", help="session id (default: the current session)")
    where.set_defaults(func=cmd_path)

    spend = subs.add_parser("cost", help="what a session costs per API call, and when a handoff repays itself")
    spend.add_argument("--session", help="session id (default: the current session)")
    spend.add_argument(
        "--fresh",
        type=int,
        help="context a fresh session would start at (default: this session's own first turn)",
    )
    spend.add_argument("--json", action="store_true", help="emit the full report as JSON")
    spend.set_defaults(func=cmd_cost)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
