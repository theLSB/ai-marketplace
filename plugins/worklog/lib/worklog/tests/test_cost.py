import pytest

from worklog import cost


def usage(inp=0, out=0, read=0, created=0, ttl="1h"):
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_input_tokens": read,
        "cache_creation_input_tokens": created,
        "cache_creation": {
            "ephemeral_1h_input_tokens": created if ttl == "1h" else 0,
            "ephemeral_5m_input_tokens": created if ttl == "5m" else 0,
        },
    }


def assistant_row(u, model="claude-opus-5", request_id="req1", uuid="a1"):
    return {
        "type": "assistant",
        "uuid": uuid,
        "requestId": request_id,
        "message": {"model": model, "usage": u},
    }


def test_model_id_loses_its_context_window_suffix():
    assert cost.normalise_model("claude-opus-5[1m]") == "claude-opus-5"
    assert cost.normalise_model("claude-opus-5") == "claude-opus-5"
    assert cost.normalise_model(None) == ""


def test_known_models_are_priced_and_others_are_not():
    assert cost.prices_for("claude-opus-5[1m]").input == 5.0
    assert cost.prices_for("claude-sonnet-5").output == 10.0
    assert cost.prices_for("<synthetic>") is None
    assert cost.prices_for("claude-opus-9") is None


def test_one_response_split_across_rows_is_billed_once():
    rows = [
        assistant_row(usage(read=100), request_id="req1", uuid="a1"),
        assistant_row(usage(read=100), request_id="req1", uuid="a2"),
        assistant_row(usage(read=200), request_id="req2", uuid="a3"),
    ]
    assert [ctx for _, ctx in ((m, cost.context_tokens(u)) for m, u in cost.billed_calls(rows))] == [100, 200]


def test_rows_that_were_never_billed_are_skipped():
    rows = [
        {"type": "user", "message": {"content": "hi"}},
        {"type": "assistant", "uuid": "a1", "requestId": None, "message": {"model": "<synthetic>", "usage": usage()}},
        {"type": "assistant", "uuid": "a2", "requestId": "req1", "message": {"model": "claude-opus-5"}},
        assistant_row(usage(read=50), request_id="req2"),
    ]
    assert len(list(cost.billed_calls(rows))) == 1


def test_context_is_everything_the_call_read():
    assert cost.context_tokens(usage(inp=2, read=1000, created=500)) == 1502


def test_write_multiplier_follows_the_ttl_actually_used():
    assert cost.write_multiplier(usage(created=100, ttl="1h")) == cost.CACHE_WRITE_1H
    assert cost.write_multiplier(usage(created=100, ttl="5m")) == cost.CACHE_WRITE_5M
    assert cost.write_multiplier(usage()) is None


def test_session_write_multiplier_uses_the_prevailing_ttl():
    rows = [
        assistant_row(usage(created=10, ttl="5m"), request_id="req1"),
        assistant_row(usage(created=900, ttl="1h"), request_id="req2"),
    ]
    assert cost.session_write_multiplier(rows) == cost.CACHE_WRITE_1H
    assert cost.session_write_multiplier([]) == cost.CACHE_WRITE_5M


def test_call_cost_charges_each_token_class_at_its_own_rate():
    got = cost.call_cost(usage(inp=10, out=100, read=1000, created=500, ttl="1h"), "claude-opus-5")
    assert got == pytest.approx(0.00805)


def test_call_cost_is_unknown_for_an_unpriced_model():
    assert cost.call_cost(usage(read=1000), "<synthetic>") is None


def test_re_reading_the_conversation_costs_the_cache_read_rate():
    assert cost.read_cost_per_call(360_000, "claude-opus-5") == pytest.approx(0.18)
    assert cost.read_cost_per_call(360_000, "claude-opus-9") is None


@pytest.mark.parametrize(
    "current,fresh,expected",
    [(400_000, 40_000, 20 / 9), (400_000, 100_000, 20 / 3), (200_000, 100_000, 20.0)],
)
def test_payback_depends_on_the_ratio_not_the_size(current, fresh, expected):
    got = cost.breakeven_calls(current, fresh, cost.CACHE_WRITE_1H, 0.1)
    assert got == pytest.approx(expected, rel=1e-3)


def test_a_fresh_session_that_is_not_smaller_never_pays_off():
    assert cost.breakeven_calls(100_000, 100_000, cost.CACHE_WRITE_1H, 0.1) is None
    assert cost.breakeven_calls(100_000, 150_000, cost.CACHE_WRITE_1H, 0.1) is None
    assert cost.breakeven_calls(100_000, 0, cost.CACHE_WRITE_1H, 0.1) is None


def test_summarise_reports_the_session_as_a_whole():
    rows = [
        assistant_row(usage(inp=2, out=100, created=20_000, ttl="1h"), request_id="req1"),
        assistant_row(usage(inp=2, out=100, read=200_000, created=500, ttl="1h"), request_id="req2"),
    ]
    got = cost.summarise(rows)
    assert got["calls"] == 2
    assert got["context_tokens"] == 200_502
    assert got["baseline_tokens"] == 20_002
    assert got["write_multiplier"] == cost.CACHE_WRITE_1H
    assert got["read_cost_per_call_usd"] == pytest.approx(0.100251)
    assert got["session_cost_usd"] > 0
    assert got["unpriced_calls"] == 0
    assert got["breakeven_calls"] == pytest.approx(2.2, abs=0.05)


def test_summarise_counts_tokens_but_not_dollars_for_an_unpriced_model():
    rows = [assistant_row(usage(read=1000), model="claude-opus-9", request_id="req1")]
    got = cost.summarise(rows)
    assert got["context_tokens"] == 1000
    assert got["session_cost_usd"] is None
    assert got["unpriced_models"] == ["claude-opus-9"]


def test_summarise_survives_a_session_with_nothing_billed():
    got = cost.summarise([{"type": "user", "message": {"content": "hi"}}])
    assert got["calls"] == 0
    assert got["context_tokens"] == 0
    assert got["breakeven_calls"] is None


def prompt_row(uuid="u1"):
    return {"type": "user", "uuid": uuid, "promptSource": "typed", "message": {"content": "hello"}}


def test_only_typed_prompts_count_as_messages():
    rows = [
        prompt_row("u1"),
        {"type": "user", "uuid": "u2", "promptSource": "system", "message": {"content": "reminder"}},
        assistant_row(usage(read=10), request_id="req1"),
        prompt_row("u3"),
    ]
    assert cost.message_count(rows) == 2


def test_calls_per_message_is_measured_not_assumed():
    rows = [prompt_row("u1")] + [
        assistant_row(usage(read=10), request_id=f"req{n}", uuid=f"a{n}") for n in range(6)
    ]
    assert cost.calls_per_message(rows) == 6.0


def test_calls_per_message_is_unknown_before_the_first_message():
    assert cost.calls_per_message([assistant_row(usage(read=10), request_id="req1")]) is None


def test_breakeven_converts_into_messages():
    assert cost.breakeven_messages(6.0, 6.0) == 1.0
    assert cost.breakeven_messages(3.0, 6.0) == 0.5
    assert cost.breakeven_messages(None, 6.0) is None
    assert cost.breakeven_messages(3.0, None) is None


def test_summarise_reports_both_units():
    rows = [prompt_row("u1")] + [
        assistant_row(usage(inp=2, out=50, created=20_000), request_id="req1", uuid="a1"),
        assistant_row(usage(inp=2, out=50, read=200_000, created=500), request_id="req2", uuid="a2"),
    ]
    got = cost.summarise(rows)
    assert got["messages"] == 1
    assert got["calls_per_message"] == 2.0
    assert got["breakeven_messages"] == pytest.approx(got["breakeven_calls"] / 2.0, abs=0.05)


def command_row(text, uuid="u1"):
    return {"type": "user", "uuid": uuid, "message": {"content": f"<command-name>{text}</command-name>"}}


def test_baseline_is_the_first_call_when_nothing_was_picked_up():
    rows = [
        prompt_row("u1"),
        assistant_row(usage(read=20_000), request_id="req1", uuid="a1"),
        assistant_row(usage(read=30_000), request_id="req2", uuid="a2"),
    ]
    assert cost.baseline_tokens(rows) == 20_000


def test_baseline_includes_what_a_pickup_read():
    rows = [
        command_row("/handoff:pickup", uuid="u1"),
        assistant_row(usage(read=20_000), request_id="req1", uuid="a1"),
        assistant_row(usage(read=32_000), request_id="req2", uuid="a2"),
        prompt_row("u2"),
        assistant_row(usage(read=40_000), request_id="req3", uuid="a3"),
    ]
    assert cost.baseline_tokens(rows) == 32_000


def test_a_pickup_after_work_started_does_not_move_the_baseline():
    rows = [
        prompt_row("u1"),
        assistant_row(usage(read=20_000), request_id="req1", uuid="a1"),
        command_row("/handoff:pickup", uuid="u2"),
        assistant_row(usage(read=50_000), request_id="req2", uuid="a2"),
    ]
    assert cost.baseline_tokens(rows) == 20_000


def test_summary_baseline_follows_a_pickup():
    rows = [
        command_row("/handoff:pickup", uuid="u1"),
        assistant_row(usage(read=20_000), request_id="req1", uuid="a1"),
        assistant_row(usage(read=32_000), request_id="req2", uuid="a2"),
        prompt_row("u2"),
        assistant_row(usage(read=60_000), request_id="req3", uuid="a3"),
    ]
    got = cost.summarise(rows)
    assert got["baseline_tokens"] == 32_000
    assert got["fresh_tokens"] == 32_000


def test_each_call_carries_the_messages_sent_before_it():
    rows = [
        prompt_row("u1"),
        assistant_row(usage(read=10), request_id="req1", uuid="a1"),
        prompt_row("u2"),
        assistant_row(usage(read=20), request_id="req2", uuid="a2"),
    ]
    assert [at for at, _, _ in cost.calls_by_message(rows)] == [1, 2]


def test_payback_context_is_break_even_run_backwards():
    fresh, write_mult, multiple, per_message = 40_000, 2.0, 0.1, 5.0
    at = cost.payback_context(fresh, write_mult, multiple, per_message)
    calls = cost.breakeven_calls(at, fresh, write_mult, multiple)
    assert cost.breakeven_messages(calls, per_message) == pytest.approx(1.0, abs=0.01)


def test_payback_context_is_unknown_without_a_baseline_or_messages():
    assert cost.payback_context(0, 2.0, 0.1, 5.0) is None
    assert cost.payback_context(40_000, 2.0, 0.0, 5.0) is None
    assert cost.payback_context(40_000, 2.0, 0.1, None) is None


def _growing_rows():
    return [
        prompt_row("u1"),
        assistant_row(usage(read=10_000), request_id="req1", uuid="a1"),
        prompt_row("u2"),
        assistant_row(usage(read=50_000), request_id="req2", uuid="a2"),
        prompt_row("u3"),
        assistant_row(usage(read=60_000), request_id="req3", uuid="a3"),
    ]


def test_messages_since_context_counts_from_the_crossing():
    assert cost.messages_since_context(_growing_rows(), 50_000) == 1


def test_messages_since_context_is_unknown_until_it_is_crossed():
    assert cost.messages_since_context(_growing_rows(), 200_000) is None
    assert cost.messages_since_context(_growing_rows(), None) is None


def test_summarise_counts_the_messages_since_payback_passed():
    rows = [
        prompt_row("u1"),
        assistant_row(usage(created=20_000), request_id="req1", uuid="a1"),
        prompt_row("u2"),
        assistant_row(usage(read=500_000, created=100), request_id="req2", uuid="a2"),
        prompt_row("u3"),
        assistant_row(usage(read=520_000, created=100), request_id="req3", uuid="a3"),
    ]
    got = cost.summarise(rows)
    assert got["breakeven_messages"] < cost.PAYBACK_PASSED_MESSAGES
    assert got["messages_overdue"] == 1


def test_handover_threshold_is_the_context_where_payback_takes_one_message():
    assert cost.handover_threshold(_growing_rows()) == 135_000


def test_handover_threshold_is_unknown_without_a_priced_model_or_a_message():
    unpriced = [prompt_row("u1"), assistant_row(usage(read=10_000), model="claude-opus-9")]
    assert cost.handover_threshold(unpriced) is None
    assert cost.handover_threshold([assistant_row(usage(created=40_000))]) is None
    assert cost.handover_threshold([]) is None


def test_handover_ratio_measures_the_way_to_that_threshold():
    assert cost.handover_ratio(_growing_rows()) == pytest.approx(60_000 / 135_000, abs=0.001)


def test_handover_ratio_prefers_the_live_context_when_given():
    assert cost.handover_ratio(_growing_rows(), 135_000) == pytest.approx(1.0, abs=0.001)


def test_handover_ratio_falls_back_with_the_context_after_a_compaction():
    peak = _growing_rows() + [
        prompt_row("u4"),
        assistant_row(usage(read=120_000), request_id="req4", uuid="a4"),
    ]
    compacted = peak + [
        prompt_row("u5"),
        assistant_row(usage(read=30_000), request_id="req5", uuid="a5"),
    ]
    assert cost.handover_ratio(peak) == pytest.approx(0.889, abs=0.001)
    assert cost.handover_ratio(compacted) == pytest.approx(0.222, abs=0.001)


def test_handover_ratio_is_unknown_when_the_threshold_is():
    assert cost.handover_ratio([assistant_row(usage(created=40_000))]) is None


def test_summarise_reports_the_handover_ratio():
    got = cost.summarise(_growing_rows())
    assert got["handover_ratio"] == pytest.approx(60_000 / 135_000, abs=0.001)
