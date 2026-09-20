import os
from datetime import date, datetime, time

import pytest

from worklog import sessions

REAL_ID = "f0d30ba8-c4f6-4020-a450-b3188a9a2970"


@pytest.mark.parametrize(
    "cwd, slug",
    [
        (
            "/home/kid1mu5@muccor.internal/data/projects/wega/production/titan/jacqueline_titan",
            "-home-kid1mu5-muccor-internal-data-projects-wega-production-titan-jacqueline-titan",
        ),
        ("/home/kid1mu5@muccor.internal/Downloads/Übersetzung", "-home-kid1mu5-muccor-internal-Downloads--bersetzung"),
        ("/tmp/a.b", "-tmp-a-b"),
    ],
)
def test_project_slug_matches_claude_code_naming(cwd, slug):
    assert sessions.project_slug(cwd) == slug


def test_project_name_keeps_the_last_two_segments():
    assert sessions.project_name("-home-user-data-titan-jacqueline-titan") == "jacqueline-titan"
    assert sessions.project_name("-tmp") == "tmp"


def test_current_session_id_prefers_the_environment():
    assert sessions.current_session_id(env={sessions.SESSION_ID_ENV: REAL_ID}) == REAL_ID


def test_current_session_id_falls_back_to_a_scratchpad_path():
    scratchpad = f"/tmp/claude-99/-home-user-proj/{REAL_ID}/scratchpad"
    assert sessions.current_session_id(env={}, scratchpad=scratchpad) == REAL_ID


def test_current_session_id_is_none_when_nothing_carries_it():
    assert sessions.current_session_id(env={sessions.SESSION_ID_ENV: "not-a-uuid"}, scratchpad="/tmp") is None


def _make_transcript(root, slug, session_id, day=None):
    directory = root / slug
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{session_id}.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    if day:
        stamp = datetime.combine(day, time(12, 0)).timestamp()
        os.utime(path, (stamp, stamp))
    return path


def test_find_transcript_searches_every_project(tmp_path):
    path = _make_transcript(tmp_path, "-home-user-b", REAL_ID)
    _make_transcript(tmp_path, "-home-user-a", "11111111-2222-3333-4444-555555555555")
    assert sessions.find_transcript(REAL_ID, root=tmp_path) == path


def test_find_transcript_returns_none_when_absent(tmp_path):
    assert sessions.find_transcript(REAL_ID, root=tmp_path) is None


def test_list_sessions_filters_by_day_and_project(tmp_path):
    old = "11111111-2222-3333-4444-555555555555"
    _make_transcript(tmp_path, "-proj-a", old, day=date(2026, 1, 1))
    _make_transcript(tmp_path, "-proj-b", REAL_ID, day=date(2026, 6, 15))
    (tmp_path / "-proj-b" / "notes.jsonl").write_text("{}\n", encoding="utf-8")

    everything = sessions.list_sessions(root=tmp_path)
    assert [s.id for s in everything] == [old, REAL_ID]

    recent = sessions.list_sessions(root=tmp_path, since=date(2026, 6, 1))
    assert [s.id for s in recent] == [REAL_ID]

    early = sessions.list_sessions(root=tmp_path, until=date(2026, 1, 31))
    assert [s.id for s in early] == [old]

    scoped = sessions.list_sessions(root=tmp_path, project="-proj-a")
    assert [s.id for s in scoped] == [old]

    by_fragment = sessions.list_sessions(root=tmp_path, project="PROJ-B")
    assert [s.id for s in by_fragment] == [REAL_ID]

    assert sessions.list_sessions(root=tmp_path, project="nothing") == []


def test_session_exposes_project_and_day(tmp_path):
    _make_transcript(tmp_path, "-home-user-titan-jacqueline-titan", REAL_ID, day=date(2026, 6, 15))
    session = sessions.list_sessions(root=tmp_path)[0]
    assert session.project == "jacqueline-titan"
    assert session.day == date(2026, 6, 15)
