import io
import json
import re

from worklog import statusline

ANSI = re.compile(r"\033\[[0-9;]*m")


def plain(text):
    return ANSI.sub("", text)


def usage(inp=0, out=0, read=0, created=0):
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_input_tokens": read,
        "cache_creation_input_tokens": created,
        "cache_creation": {"ephemeral_1h_input_tokens": created, "ephemeral_5m_input_tokens": 0},
    }


def prompt_row(uuid="u1"):
    return {"type": "user", "uuid": uuid, "promptSource": "typed", "message": {"content": "do the thing"}}


def command_row(uuid="u1"):
    return {"type": "user", "uuid": uuid, "message": {"content": "<command-name>/doctor</command-name>"}}


def call_row(uuid, request_id, **kw):
    return {
        "type": "assistant",
        "uuid": uuid,
        "requestId": request_id,
        "message": {"model": "claude-opus-5", "usage": usage(**kw)},
    }


def write_transcript(tmp_path, first_context=40_000, calls_per_message=1):
    path = tmp_path / "session.jsonl"
    rows = [prompt_row()]
    for n in range(calls_per_message):
        rows.append(call_row(f"a{n}", f"req{n}", created=first_context if n == 0 else 10))
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def payload(tmp_path=None, **overrides):
    data = {
        "model": {"id": "claude-opus-5[1m]"},
        "cost": {"total_cost_usd": 5.83},
        "context_window": {
            "total_input_tokens": 400_000,
            "context_window_size": 1_000_000,
            "used_percentage": 40.0,
            "current_usage": usage(read=400_000),
        },
    }
    if tmp_path is not None:
        data["transcript_path"] = str(write_transcript(tmp_path))
    data.update(overrides)
    return data


def test_token_counts_are_shortened():
    assert statusline.tokens(950) == "950"
    assert statusline.tokens(54_260) == "54k"
    assert statusline.tokens(1_250_000) == "1.2M"


def test_the_line_carries_context_rate_spend_and_handover(tmp_path):
    line = plain(statusline.build_line(payload(tmp_path)))
    assert line == "context 40% (400k) · $0.20/call · $5.83 · handover 48%"


def test_context_falls_back_to_the_raw_usage(tmp_path):
    data = payload(tmp_path)
    del data["context_window"]["total_input_tokens"]
    assert "context 40% (400k)" in plain(statusline.build_line(data))


def test_percentage_is_computed_when_not_supplied(tmp_path):
    data = payload(tmp_path)
    del data["context_window"]["used_percentage"]
    assert plain(statusline.build_line(data)).startswith("context 40% (400k)")


def test_an_unpriced_model_still_shows_context_and_spend(tmp_path):
    line = plain(statusline.build_line(payload(tmp_path, model={"id": "claude-opus-9"})))
    assert "context 40% (400k)" in line
    assert "$5.83" in line
    assert "/call" not in line
    assert "handover" not in line


def test_without_a_transcript_there_is_no_handover_label():
    line = plain(statusline.build_line(payload()))
    assert "context 40% (400k)" in line
    assert "handover" not in line


def test_a_small_session_reads_as_a_low_percentage(tmp_path):
    data = payload(tmp_path)
    data["context_window"]["total_input_tokens"] = 40_000
    assert plain(statusline.build_line(data)).endswith("handover 5%")


def test_the_line_carries_the_limit_windows_after_the_context_gauge(tmp_path):
    data = payload(tmp_path, rate_limits=limits(five=62.0, seven=41.0))
    line = plain(statusline.build_line(data))
    assert line == "context 40% (400k) · 5h 62% · 7d 41% · $0.20/call · $5.83 · handover 48%"


def test_the_limit_windows_show_even_without_a_context_figure():
    assert plain(statusline.build_line({"rate_limits": limits(five=62.0)})) == "5h 62%"


def test_an_empty_payload_produces_an_empty_line():
    assert statusline.build_line({}) == ""


def test_bad_input_prints_nothing_and_still_succeeds(monkeypatch, capsys):
    monkeypatch.setattr(statusline.sys, "stdin", io.StringIO("not json"))
    assert statusline.main() == 0
    assert capsys.readouterr().out == ""


def test_a_real_payload_is_printed(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(statusline.sys, "stdin", io.StringIO(json.dumps(payload(tmp_path))))
    assert statusline.main() == 0
    assert plain(capsys.readouterr().out).strip().startswith("context 40% (400k)")


def test_a_handover_already_worth_it_reads_as_due(tmp_path):
    data = payload()
    data["transcript_path"] = str(write_transcript(tmp_path, calls_per_message=10))
    assert "handover due · 333%" in plain(statusline.build_line(data))


def write_overdue_transcript(tmp_path):
    """A session that passed the point of a worthwhile handover one message ago."""
    path = tmp_path / "overdue.jsonl"
    rows = [
        prompt_row("u1"),
        call_row("a1", "req1", created=40_000),
        prompt_row("u2"),
        call_row("a2", "req2", read=900_000, created=10),
        prompt_row("u3"),
        call_row("a3", "req3", read=950_000, created=10),
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def test_a_passed_threshold_shows_how_far_past_it_is(tmp_path):
    data = payload(transcript_path=str(write_overdue_transcript(tmp_path)))
    data["context_window"]["total_input_tokens"] = 950_010
    assert "handover due · 113%" in plain(statusline.build_line(data))


def test_a_session_opened_with_a_slash_command_counts_messages(tmp_path):
    path = tmp_path / "s.jsonl"
    rows = [command_row(), call_row("a1", "req1", created=40_000)]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    data = payload()
    data["transcript_path"] = str(path)
    assert "handover 48%" in plain(statusline.build_line(data))


def test_the_label_waits_for_a_message_to_count(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text(json.dumps(call_row("a1", "req1", created=40_000)) + "\n", encoding="utf-8")
    data = payload()
    data["transcript_path"] = str(path)
    assert "handover" not in plain(statusline.build_line(data))


def test_a_distant_handover_is_green_with_its_percentage():
    label = statusline.handover_label(0.12)
    assert statusline.GREEN in label and plain(label) == "handover 12%"
    assert statusline.GREEN in statusline.handover_label(0.59)


def test_the_handover_gauge_turns_yellow_from_sixty_percent():
    for ratio in (0.60, 0.72, 0.84):
        label = statusline.handover_label(ratio)
        assert statusline.YELLOW in label, ratio
        assert plain(label) == f"handover {round(ratio * 100)}%"


def test_the_handover_gauge_turns_red_from_eighty_five_percent():
    for ratio in (0.85, 0.93, 0.99):
        label = statusline.handover_label(ratio)
        assert statusline.RED in label, ratio
        assert plain(label) == f"handover {round(ratio * 100)}%"


def test_a_passed_threshold_is_red_and_keeps_counting():
    label = statusline.handover_label(1.7)
    assert statusline.RED in label and plain(label) == "handover due · 170%"


def test_the_threshold_itself_reads_as_due():
    assert plain(statusline.handover_label(1.0)) == "handover due · 100%"


def test_the_handover_colour_follows_the_percentage_shown():
    assert plain(statusline.handover_label(0.596)) == "handover 60%"
    assert statusline.YELLOW in statusline.handover_label(0.596)
    assert plain(statusline.handover_label(0.846)) == "handover 85%"
    assert statusline.RED in statusline.handover_label(0.846)


def test_every_coloured_label_is_closed():
    for ratio in (0.1, 0.85, 1.4):
        assert statusline.handover_label(ratio).endswith(statusline.RESET)


def test_a_gauge_takes_its_colour_from_the_marks_it_is_given():
    assert statusline.share_colour(0, 60, 85) == statusline.GREEN
    assert statusline.share_colour(59, 60, 85) == statusline.GREEN
    assert statusline.share_colour(60, 60, 85) == statusline.YELLOW
    assert statusline.share_colour(84, 60, 85) == statusline.YELLOW
    assert statusline.share_colour(85, 60, 85) == statusline.RED
    assert statusline.share_colour(140, 60, 85) == statusline.RED


def test_every_gauge_shares_the_same_marks():
    assert statusline.GREEN in statusline.context_label(590_000, 59.0)
    assert statusline.YELLOW in statusline.context_label(600_000, 60.0)
    assert statusline.RED in statusline.context_label(850_000, 85.0)
    assert statusline.GREEN in statusline.handover_label(0.59)
    assert statusline.YELLOW in statusline.handover_label(0.60)
    assert statusline.RED in statusline.handover_label(0.85)
    for share, colour in ((59, statusline.GREEN), (60, statusline.YELLOW), (85, statusline.RED)):
        (label,) = statusline.rate_limit_labels({"five_hour": {"used_percentage": share}})
        assert colour in label, share


def test_a_context_with_room_to_spare_is_green():
    for share in (12.0, 50.0):
        assert statusline.GREEN in statusline.context_label(200_000, share), share
    assert plain(statusline.context_label(200_000, 20.0)) == "context 20% (200k)"


def test_a_context_past_sixty_turns_yellow():
    for share in (60.0, 72.0, 84.0):
        assert statusline.YELLOW in statusline.context_label(650_000, share), share


def test_a_nearly_full_context_is_red():
    label = statusline.context_label(920_000, 92.0)
    assert statusline.RED in label and plain(label) == "context 92% (920k)"


def test_the_context_colour_follows_the_percentage_shown():
    assert statusline.GREEN in statusline.context_label(594_000, 59.4)
    assert statusline.YELLOW in statusline.context_label(596_000, 59.6)
    assert statusline.YELLOW in statusline.context_label(844_000, 84.4)
    assert statusline.RED in statusline.context_label(846_000, 84.6)


def test_a_full_window_reads_in_millions():
    assert plain(statusline.context_label(1_250_000, 96.0)) == "context 96% (1.2M)"


def test_a_context_without_a_share_carries_no_percentage_or_colour():
    assert statusline.context_label(400_000, None) == "context 400k"


def test_every_coloured_context_label_is_closed():
    for share in (12.0, 65.0, 92.0):
        assert statusline.context_label(400_000, share).endswith(statusline.RESET)


def limits(five=None, seven=None):
    block = {}
    if five is not None:
        block["five_hour"] = {"used_percentage": five, "resets_at": 1_800_000_000}
    if seven is not None:
        block["seven_day"] = {"used_percentage": seven, "resets_at": 1_800_400_000}
    return block


def test_both_windows_are_reported_shortest_first():
    labels = statusline.rate_limit_labels(limits(five=62.0, seven=41.0))
    assert [plain(label) for label in labels] == ["5h 62%", "7d 41%"]


def test_a_single_window_does_not_wait_for_the_other():
    assert [plain(label) for label in statusline.rate_limit_labels(limits(five=62.0))] == ["5h 62%"]
    assert [plain(label) for label in statusline.rate_limit_labels(limits(seven=41.0))] == ["7d 41%"]


def test_no_windows_reported_means_no_segments():
    assert statusline.rate_limit_labels({}) == []
    assert statusline.rate_limit_labels(None) == []
    assert statusline.rate_limit_labels("not a block") == []


def test_an_unreadable_window_is_dropped_without_costing_the_other():
    assert [plain(label) for label in statusline.rate_limit_labels({"five_hour": "junk", **limits(seven=41.0)})] == ["7d 41%"]
    assert [plain(label) for label in statusline.rate_limit_labels(limits(five="most of it", seven=41.0))] == ["7d 41%"]
    assert [plain(label) for label in statusline.rate_limit_labels(limits(five=True, seven=41.0))] == ["7d 41%"]
    assert statusline.rate_limit_labels({"five_hour": {}}) == []


def test_a_window_takes_the_same_colours_as_the_context_gauge():
    for share, colour in ((30.0, statusline.GREEN), (62.0, statusline.YELLOW), (92.0, statusline.RED)):
        (label,) = statusline.rate_limit_labels({"five_hour": {"used_percentage": share}})
        assert colour in label, share


def test_a_window_past_its_limit_keeps_counting():
    (label,) = statusline.rate_limit_labels({"five_hour": {"used_percentage": 104.0}})
    assert statusline.RED in label and plain(label) == "5h 104%"


def test_every_window_label_is_closed():
    for label in statusline.rate_limit_labels(limits(five=30.0, seven=92.0)):
        assert label.endswith(statusline.RESET)


def write_pickup_transcript(tmp_path):
    path = tmp_path / "pickup.jsonl"
    rows = [
        {"type": "user", "uuid": "u1", "message": {"content": "<command-name>/handoff:pickup</command-name>"}},
        call_row("a0", "req0", read=40_000),
        call_row("a1", "req1", read=60_000),
        prompt_row("u2"),
        call_row("a2", "req2", read=80_000),
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def test_the_label_counts_what_the_pickup_had_to_read(tmp_path):
    line = plain(statusline.build_line(payload(transcript_path=str(write_pickup_transcript(tmp_path)))))
    assert "handover 71%" in line
