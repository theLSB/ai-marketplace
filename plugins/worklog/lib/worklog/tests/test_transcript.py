from worklog import transcript


def user_row(text, uuid="u1", source="typed", **extra):
    row = {
        "type": "user",
        "uuid": uuid,
        "timestamp": "2026-09-10T10:00:00Z",
        "promptSource": source,
        "cwd": "/repo",
        "gitBranch": "main",
        "message": {"content": text},
    }
    row.update(extra)
    return row


def assistant_row(blocks, uuid="a1"):
    return {"type": "assistant", "uuid": uuid, "timestamp": "2026-09-10T10:01:00Z", "message": {"content": blocks}}


def test_a_typed_prompt_is_human_input():
    assert transcript.is_human_prompt(user_row("do the thing"))


def test_injected_and_derived_rows_are_not_prompts():
    assert not transcript.is_human_prompt(user_row("reminder", source="system"))
    assert not transcript.is_human_prompt(user_row("output", source=None, toolUseResult={"ok": True}))
    assert not transcript.is_human_prompt(user_row([{"type": "text", "text": "skill"}], isMeta=True))
    assert not transcript.is_human_prompt(user_row("   "))
    assert not transcript.is_human_prompt(assistant_row([]))


def test_a_slash_command_is_human_input():
    row = user_row("<command-message>doctor</command-message><command-name>/doctor</command-name>", source=None)
    assert transcript.is_human_prompt(row)


def test_a_command_the_system_sent_is_not_human_input():
    assert not transcript.is_human_prompt(user_row("<command-name>/doctor</command-name>", source="system"))


def test_an_interrupt_notice_is_not_human_input():
    assert not transcript.is_human_prompt(user_row("[Request interrupted by user]", source=None))


def test_clean_prompt_drops_injected_blocks():
    raw = "real question\n<system-reminder>ignore me</system-reminder>\n<local-command-stdout>noise</local-command-stdout>"
    assert transcript.clean_prompt(raw) == "real question"


def test_slash_command_is_recognised_with_and_without_arguments():
    assert transcript.slash_command("<command-name>/usage</command-name>") == "/usage"
    assert (
        transcript.slash_command("<command-name>loop</command-name><command-args>5m /foo</command-args>")
        == "/loop 5m /foo"
    )
    assert transcript.slash_command("plain text") == ""


def test_parse_turns_groups_replies_and_tools_under_each_prompt():
    rows = [
        assistant_row([{"type": "text", "text": "orphan"}], uuid="a0"),
        user_row("first", uuid="u1"),
        assistant_row(
            [
                {"type": "thinking", "thinking": "private"},
                {"type": "text", "text": "working"},
                {"type": "tool_use", "name": "Edit", "input": {"file_path": "/repo/a.py"}},
                {"type": "tool_use", "name": "Bash", "input": {"command": "ls -la", "description": "List files"}},
            ]
        ),
        user_row("tool output", source=None, toolUseResult={"ok": True}),
        assistant_row([{"type": "text", "text": "done"}], uuid="a2"),
        user_row("second", uuid="u2"),
        assistant_row([{"type": "tool_use", "name": "Read", "input": {"file_path": "/repo/b.py"}}], uuid="a3"),
    ]

    turns = transcript.parse_turns(rows)

    assert [t.prompt for t in turns] == ["first", "second"]
    assert [t.ordinal for t in turns] == [1, 2]
    assert turns[0].replies == ["working", "done"]
    assert [str(t) for t in turns[0].tools] == ["Edit: /repo/a.py", "Bash: List files"]
    assert turns[0].files_changed == ["/repo/a.py"]
    assert turns[0].branch == "main"
    assert turns[1].files_read == ["/repo/b.py"]
    assert turns[1].files_changed == []


def test_repeated_edits_to_one_file_are_listed_once():
    rows = [
        user_row("edit twice"),
        assistant_row(
            [
                {"type": "tool_use", "name": "Edit", "input": {"file_path": "/repo/a.py"}},
                {"type": "tool_use", "name": "Write", "input": {"file_path": "/repo/a.py"}},
            ]
        ),
    ]
    assert transcript.parse_turns(rows)[0].files_changed == ["/repo/a.py"]


def test_bash_without_a_description_falls_back_to_the_command():
    rows = [user_row("run"), assistant_row([{"type": "tool_use", "name": "Bash", "input": {"command": "make\nall"}}])]
    assert str(transcript.parse_turns(rows)[0].tools[0]) == "Bash: make"


def test_session_meta_reports_title_span_and_place():
    rows = [
        user_row("first", uuid="u1"),
        {"type": "ai-title", "aiTitle": "Old title"},
        {"type": "ai-title", "aiTitle": "Work logger design"},
        assistant_row([{"type": "text", "text": "ok"}]),
    ]
    meta = transcript.session_meta(rows)
    assert meta["title"] == "Work logger design"
    assert meta["cwd"] == "/repo"
    assert meta["branch"] == "main"
    assert meta["started"] == "2026-09-10T10:00:00Z"
    assert meta["ended"] == "2026-09-10T10:01:00Z"


def test_turns_since_returns_only_what_follows_the_watermark():
    turns = transcript.parse_turns([user_row("a", uuid="u1"), user_row("b", uuid="u2"), user_row("c", uuid="u3")])
    assert [t.prompt for t in transcript.turns_since(turns, "u1")] == ["b", "c"]
    assert [t.prompt for t in transcript.turns_since(turns, "")] == ["a", "b", "c"]
    assert [t.prompt for t in transcript.turns_since(turns, "gone")] == ["a", "b", "c"]
    assert transcript.turns_since(turns, "u3") == []


def test_read_rows_skips_unparsable_lines(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text('{"type":"user"}\nnot json\n\n{"type":"assistant"}\n', encoding="utf-8")
    assert [r["type"] for r in transcript.read_rows(path)] == ["user", "assistant"]


def test_files_written_by_bash_count_as_changed():
    rows = [
        user_row("write it"),
        assistant_row(
            [
                {
                    "type": "tool_use",
                    "name": "Bash",
                    "input": {"command": "cat > /repo/new.py <<'PY'\nx = 1\nPY", "description": "Write module"},
                },
                {"type": "tool_use", "name": "Bash", "input": {"command": "python3 -m pytest -q", "description": "Run tests"}},
            ]
        ),
    ]
    turn = transcript.parse_turns(rows)[0]
    assert turn.files_changed == ["/repo/new.py"]
    assert [str(t) for t in turn.tools] == ["Bash: Write module", "Bash: Run tests"]
