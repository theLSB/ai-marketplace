from datetime import date, datetime, timezone

import pytest

from worklog import logs
from worklog.sessions import Session

SESSION_A = "f0d30ba8-c4f6-4020-a450-b3188a9a2970"
SESSION_B = "11111111-2222-3333-4444-555555555555"


@pytest.fixture
def worklogs(tmp_path, monkeypatch):
    directory = tmp_path / "worklogs"
    directory.mkdir()
    monkeypatch.setenv("WORKLOG_DIR", str(directory))
    return directory


def make_session(session_id=SESSION_A, day=date(2026, 9, 10), slug="-home-user-titan-jacqueline-titan"):
    moment = datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc)
    return Session(id=session_id, path=tmp_transcript(session_id), slug=slug, modified=moment)


def tmp_transcript(session_id):
    from pathlib import Path

    return Path(f"/nonexistent/{session_id}.jsonl")


def test_worklog_dir_follows_the_environment(worklogs):
    assert logs.worklog_dir() == worklogs
    assert logs.reports_dir() == worklogs / "reports"


def test_log_name_sorts_by_day_and_names_project_and_session():
    assert logs.log_name(date(2026, 9, 10), "jacqueline-titan", SESSION_A) == f"2026-09-10--jacqueline-titan--{SESSION_A}.md"


def test_log_path_uses_the_configured_directory(worklogs):
    assert logs.log_path(make_session()).parent == worklogs


def test_write_entries_creates_a_log_with_frontmatter(worklogs):
    path = logs.log_path(make_session())
    logs.write_entries(path, {"session": SESSION_A, "project": "titan", "last_turn": "u1"}, "## Task one\n\nDid a thing.")

    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "session: " + SESSION_A in text
    assert "## Task one" in text
    assert logs.watermark(path) == "u1"
    assert logs.read_header(path)["logged"]


def test_write_entries_appends_and_advances_the_watermark(worklogs):
    path = logs.log_path(make_session())
    logs.write_entries(path, {"session": SESSION_A, "last_turn": "u1"}, "## Task one")
    logs.write_entries(path, {"session": SESSION_A, "last_turn": "u5"}, "## Task two")

    text = path.read_text(encoding="utf-8")
    assert text.count("---") == 2
    assert "## Task one" in text and "## Task two" in text
    assert text.index("## Task one") < text.index("## Task two")
    assert logs.watermark(path) == "u5"


def test_write_entries_keeps_header_fields_it_is_not_given(worklogs):
    path = logs.log_path(make_session())
    logs.write_entries(path, {"session": SESSION_A, "title": "First title", "last_turn": "u1"}, "## One")
    logs.write_entries(path, {"session": SESSION_A, "last_turn": "u2"}, "## Two")
    assert logs.read_header(path)["title"] == "First title"


def test_read_header_and_watermark_tolerate_a_log_without_frontmatter(tmp_path):
    path = tmp_path / "plain.md"
    path.write_text("just notes\n", encoding="utf-8")
    assert logs.read_header(path) == {}
    assert logs.watermark(path) == ""
    assert logs.watermark(None) == ""


def test_find_log_locates_a_session_whatever_the_day_in_its_name(worklogs):
    path = worklogs / f"2026-01-01--other-name--{SESSION_A}.md"
    path.write_text("---\nsession: x\n---\n", encoding="utf-8")
    assert logs.find_log(SESSION_A) == path
    assert logs.find_log(SESSION_B) is None


def test_list_logs_orders_by_day_and_filters_a_span(worklogs):
    for day, session_id in ((date(2026, 1, 5), SESSION_B), (date(2026, 9, 10), SESSION_A)):
        (worklogs / logs.log_name(day, "titan", session_id)).write_text(
            f"---\nsession: {session_id}\nproject: titan\n---\nbody\n", encoding="utf-8"
        )

    assert [log.day for log in logs.list_logs()] == [date(2026, 1, 5), date(2026, 9, 10)]
    assert [log.session_id for log in logs.list_logs(since=date(2026, 6, 1))] == [SESSION_A]
    assert [log.session_id for log in logs.list_logs(until=date(2026, 6, 1))] == [SESSION_B]
    assert logs.list_logs()[0].project == "titan"


def test_unlogged_sessions_reports_only_sessions_without_a_log(worklogs):
    logged = make_session(SESSION_A)
    missing = make_session(SESSION_B)
    (worklogs / logs.log_name(date(2026, 9, 10), "titan", SESSION_A)).write_text("---\n---\n", encoding="utf-8")

    assert [s.id for s in logs.unlogged_sessions([logged, missing])] == [SESSION_B]
