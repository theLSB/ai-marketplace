import json
import os
from datetime import date, datetime, time

import pytest

from worklog import cli

SESSION = "f0d30ba8-c4f6-4020-a450-b3188a9a2970"
SLUG = "-home-user-titan-jacqueline-titan"
DAY = date(2026, 9, 10)

ROWS = [
    {"type": "ai-title", "aiTitle": "Calibration fix"},
    {
        "type": "user",
        "uuid": "u1",
        "timestamp": "2026-09-10T10:00:00Z",
        "promptSource": "typed",
        "cwd": "/repo",
        "gitBranch": "dk_test",
        "message": {"content": "fix the LED state"},
    },
    {
        "type": "assistant",
        "uuid": "a1",
        "timestamp": "2026-09-10T10:05:00Z",
        "message": {
            "content": [
                {"type": "text", "text": "Fixed it."},
                {"type": "tool_use", "name": "Edit", "input": {"file_path": "/repo/src/JacquelineDlg.cpp"}},
            ]
        },
    },
    {
        "type": "user",
        "uuid": "u2",
        "timestamp": "2026-09-10T10:10:00Z",
        "promptSource": "typed",
        "message": {"content": "<command-name>session-logger</command-name>"},
    },
]


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    transcripts = tmp_path / "claude" / "projects" / SLUG
    transcripts.mkdir(parents=True)
    transcript = transcripts / f"{SESSION}.jsonl"
    transcript.write_text(
        "\n".join(json.dumps(row) for row in ROWS) + "\n", encoding="utf-8"
    )
    stamp = datetime.combine(DAY, time(12, 0)).timestamp()
    os.utime(transcript, (stamp, stamp))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setenv("WORKLOG_DIR", str(tmp_path / "worklogs"))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SESSION)
    return tmp_path


def digest(capsys, *args):
    assert cli.main(["digest", *args]) == 0
    return json.loads(capsys.readouterr().out)


def test_digest_describes_the_current_session_and_its_turns(workspace, capsys):
    payload = digest(capsys)

    assert payload["session"]["id"] == SESSION
    assert payload["session"]["project"] == "jacqueline-titan"
    assert payload["session"]["title"] == "Calibration fix"
    assert payload["session"]["log_exists"] is False
    assert payload["session"]["turns_total"] == 2
    assert payload["session"]["head_turn"] == "u2"
    assert [t["prompt"] for t in payload["turns"]] == ["fix the LED state", ""]
    assert payload["turns"][0]["files_changed"] == ["/repo/src/JacquelineDlg.cpp"]
    assert payload["turns"][1]["command"] == "/session-logger"


def test_digest_clips_long_text(workspace, capsys):
    payload = digest(capsys, "--max-prompt", "5")
    assert payload["turns"][0]["prompt"].startswith("fix t")
    assert "+12 chars" in payload["turns"][0]["prompt"]


def test_append_writes_the_log_and_digest_then_reports_nothing_pending(workspace, capsys):
    entry = workspace / "entry.md"
    entry.write_text("## Fix LED state\n\nEdited the dialog.\n", encoding="utf-8")

    assert cli.main(["append", "--file", str(entry)]) == 0
    written = capsys.readouterr().out.strip()
    assert written.endswith("(last_turn u2)")

    log = workspace / "worklogs" / f"{DAY.isoformat()}--jacqueline-titan--{SESSION}.md"
    assert "## Fix LED state" in log.read_text(encoding="utf-8")

    payload = digest(capsys)
    assert payload["session"]["turns_pending"] == 0
    assert payload["session"]["log_exists"] is True
    assert payload["turns"] == []

    everything = digest(capsys, "--all")
    assert everything["session"]["turns_pending"] == 2


def test_append_refuses_empty_entries(workspace, tmp_path):
    empty = tmp_path / "empty.md"
    empty.write_text("\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main(["append", "--file", str(empty)])


def test_digest_without_a_session_id_explains_itself(workspace, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID")
    monkeypatch.setenv("TMPDIR", "/tmp")
    with pytest.raises(SystemExit) as failure:
        cli.main(["digest"])
    assert "no session id" in str(failure.value)


def test_digest_names_the_session_it_cannot_find(workspace):
    with pytest.raises(SystemExit) as failure:
        cli.main(["digest", "--session", "11111111-2222-3333-4444-555555555555"])
    assert "no transcript found" in str(failure.value)


def test_sessions_marks_logged_and_unlogged(workspace, capsys):
    assert cli.main(["sessions"]) == 0
    assert "unlogged" in capsys.readouterr().out

    entry = workspace / "e.md"
    entry.write_text("## done\n", encoding="utf-8")
    cli.main(["append", "--file", str(entry)])
    capsys.readouterr()

    assert cli.main(["sessions"]) == 0
    assert "logged" in capsys.readouterr().out
    assert cli.main(["sessions", "--unlogged"]) == 0
    assert "(no sessions match)" in capsys.readouterr().out


def test_logs_and_path_report_the_log_location(workspace, capsys):
    assert cli.main(["path"]) == 0
    assert f"{DAY.isoformat()}--jacqueline-titan--{SESSION}.md" in capsys.readouterr().out

    assert cli.main(["logs"]) == 0
    assert "(no work logs match)" in capsys.readouterr().out


def test_a_note_can_be_appended_without_swallowing_unlogged_turns(workspace, capsys):
    entry = workspace / "entry.md"
    entry.write_text("## Fix LED state\n", encoding="utf-8")
    note = workspace / "note.md"
    note.write_text("## Note: still untested on hardware\n", encoding="utf-8")

    assert cli.main(["append", "--file", str(entry), "--last-turn", "u1"]) == 0
    assert cli.main(["append", "--file", str(note), "--keep-watermark"]) == 0
    assert capsys.readouterr().out.strip().endswith("(last_turn u1)")

    payload = digest(capsys)
    assert payload["session"]["watermark"] == "u1"
    assert [t["uuid"] for t in payload["turns"]] == ["u2"]

    log = workspace / "worklogs" / f"{DAY.isoformat()}--jacqueline-titan--{SESSION}.md"
    text = log.read_text(encoding="utf-8")
    assert "## Fix LED state" in text and "## Note: still untested on hardware" in text


def test_a_note_creates_the_log_without_setting_a_watermark(workspace, capsys):
    note = workspace / "note.md"
    note.write_text("## Note: hardware arrives Friday\n", encoding="utf-8")

    assert cli.main(["append", "--file", str(note), "--keep-watermark"]) == 0
    assert capsys.readouterr().out.strip().endswith("(last_turn none)")

    payload = digest(capsys)
    assert payload["session"]["log_exists"] is True
    assert payload["session"]["turns_pending"] == 2


def test_the_cost_report_states_handover_readiness(workspace, capsys):
    transcript = workspace / "claude" / "projects" / SLUG / f"{SESSION}.jsonl"
    billed = [
        {"type": "user", "uuid": "u1", "promptSource": "typed", "message": {"content": "hi"}},
        {
            "type": "assistant",
            "uuid": "a1",
            "requestId": "req1",
            "message": {
                "model": "claude-opus-5",
                "usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_read_input_tokens": 10_000,
                    "cache_creation_input_tokens": 0,
                    "cache_creation": {"ephemeral_1h_input_tokens": 0, "ephemeral_5m_input_tokens": 0},
                },
            },
        },
    ]
    transcript.write_text("\n".join(json.dumps(row) for row in billed) + "\n", encoding="utf-8")
    assert cli.main(["cost"]) == 0
    assert "readiness 7%" in capsys.readouterr().out
