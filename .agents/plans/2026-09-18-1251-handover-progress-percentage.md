# Handover readiness as a percentage

Branch: `fix/handover-progress-percentage` (off `main`)
Cards: [#9](https://gitlab.beissbarth.cloud/wega2/bb_ai_marketplace/-/issues/9), [#10](https://gitlab.beissbarth.cloud/wega2/bb_ai_marketplace/-/issues/10), [#11](https://gitlab.beissbarth.cloud/wega2/bb_ai_marketplace/-/issues/11)

## The thread

The handover figure in the status line answers a different question from the one it is read for,
and it runs out of resolution about a fifth of the way into a session.

It shows `breakeven_messages`: how quickly a fresh session would repay its cache rebuild *once
started*. That quantity has the shape `C / (context − baseline)` — a hyperbola. It falls from ~100
to 1 inside the first fifteen messages and then sits on 1 for the rest of the session. All its
precision is spent while a handover is pointless, and it has none left by the time the decision
matters. That is why it looks frozen.

What is wanted is the opposite shape: how far the session has travelled toward the point where a
handover becomes worth doing. That is `context / threshold` — a number that starts near zero,
climbs past 100%, moves on every message, and keeps its resolution where the decision is made. The
threshold is already computed today (`payback_context`); it is simply never shown.

So `cost.py` grows one function returning that ratio, the status line renders it as a percentage,
and the break-even-in-messages arithmetic stops driving the display. Each work package is
independently testable; WP1 is usable from the CLI on its own.

## The measurement

Replay of a real session (`35b25658`, 79 messages, 324 calls, Opus 5), showing what the status line
displayed at the end of each turn against what the percentage would have shown:

| message | context | `breakeven_messages` | shown now | ratio |
|---|---|---|---|---|
| 1 | 42,618 | — | — | 5% |
| 5 | 70,262 | 8.11 | 8 msg | 26% |
| 14 | 126,413 | 2.46 | 2 msg | 51% |
| 18 | 198,548 | 1.28 | **1 msg** | 82% |
| 24 | 253,444 | 0.95 | **1 msg** | 104% |
| 45 | 439,771 | 0.54 | **1 msg** | 177% |
| 46 | 282,473 | 0.84 | **1 msg** | 115% |
| 79 | 425,437 | 0.54 | **1 msg** | 170% |

From message 18 to message 79 — 61 consecutive messages, 77% of the session — the displayed
integer never changes while context doubles from 198k to 425k.

Message 46 is a compaction: context falls 439,771 → 282,473 in one step. It is real and the gauge
must be free to fall with it.

## The arithmetic

The threshold is the existing break-even formula solved for context, at one message:

```
threshold = baseline + (baseline × write_mult) / (1 × calls_per_message × read_multiple)
ratio     = context / threshold
```

For Opus 5 (`read_multiple` = 0.1, 1h writes = 2.0×) that puts the threshold at roughly 5–6×
baseline. `ratio ≥ 1.0` means a fresh session repays itself inside a single message.

## Load-bearing claims

| Claim | Status |
|---|---|
| The displayed figure is `breakeven_messages`, rendered by `handover_label` | **verified** — `plugins/worklog/lib/worklog/statusline.py:40-53,88-90` |
| `payback_context` already computes the threshold and is called inside `summarise` | **verified** — `plugins/worklog/lib/worklog/cost.py:211-220,260` |
| `summarise` returns `messages_overdue` but not the threshold | **verified** — `plugins/worklog/lib/worklog/cost.py:262-279` |
| `handover_label` prints `(0 msg)` when `overdue` is `None`, via `-(overdue or 0)` | **verified** — `statusline.py:49`; a passing test locks the wart in at `tests/test_statusline.py:192-193` |
| `messages_overdue` is non-monotone across a session (`None→0→1→2→2→None→4→1→8`) | **verified** — replay of `35b25658` with `cost.messages_since_context` |
| The status line is the only consumer of `messages_overdue`; the CLI never prints it | **verified** — `grep` over `cli.py`, `skills/` — only `breakeven_calls`, `breakeven_messages`, `calls_per_message` are used, at `cli.py:152-161` |
| `worklog cost --json` dumps the whole `summarise` dict, so removing a key is a contract change | **verified** — `plugins/worklog/lib/worklog/cli.py:141-143` |
| Tests are plain pytest with row-builder helpers; `conftest.py` puts `lib/` on `sys.path` | **verified** — `tests/conftest.py:1-4`, `tests/test_cost.py:6-25` |
| Baseline suite is green at 136 passed | **verified** — `python3 -m pytest lib/worklog/tests -q` |
| Every expected number in WP1/WP2 below | **verified** — computed against the current `cost` functions with the exact fixtures used in the tests |
| Plugin version bump is the house convention for a behaviour change | **verified** — `git log`: "Bump worklog to 1.4.0", "Bump worklog to 1.3.0" |

## Options rejected

- **Running max over the replay so the gauge never falls.** Proposed in chat, withdrawn here: the
  replay shows a real compaction at message 46 dropping context by 157k. A running max would have
  pinned the gauge at 177% while the true reading was 115%, hiding exactly the event that buys the
  user room. The raw ratio dips by at most ~5 points from `calls_per_message` wobble, which is
  within tolerance for a gauge whose job is "a general sense".
- **A messages-remaining countdown** (`(threshold − context) / growth_per_message`). Readable, but
  it inherits the `calls_per_message` jitter *and* needs a growth estimate, so it is noisier than
  the percentage while saturating at "due" just the same.
- **Percentage of the context window** (`context / context_window_size`). Already on the line as
  `ctx 400k 40%`, and it says nothing about the cost economics that drive a handover.
- **Deleting `messages_since_context` / `messages_overdue`.** They leave the status line, but
  `worklog cost --json` publishes the key. Dropping it is a separate, breaking change.

---

## WP1 — the ratio, in the cost model ([#9](https://gitlab.beissbarth.cloud/wega2/bb_ai_marketplace/-/issues/9))

**Files:**
- Modify: `plugins/worklog/lib/worklog/cost.py` (add after `payback_context`, ~line 221)
- Test: `plugins/worklog/lib/worklog/tests/test_cost.py`

**Produces:** `cost.handover_threshold(rows) -> int | None`,
`cost.handover_ratio(rows, current: int | None = None) -> float | None`, and a
`"handover_ratio"` key in the `summarise` dict.

- [ ] **Step 1: Write the failing tests**

Append to `plugins/worklog/lib/worklog/tests/test_cost.py`:

```python
def test_handover_threshold_is_the_context_where_payback_takes_one_message():
    rows = _growing_rows()
    assert cost.handover_threshold(rows) == 135_000


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
    peak = _growing_rows() + [prompt_row("u4"), assistant_row(usage(read=120_000), request_id="req4", uuid="a4")]
    compacted = peak + [prompt_row("u5"), assistant_row(usage(read=30_000), request_id="req5", uuid="a5")]
    assert cost.handover_ratio(peak) == pytest.approx(0.889, abs=0.001)
    assert cost.handover_ratio(compacted) == pytest.approx(0.222, abs=0.001)


def test_handover_ratio_is_unknown_when_the_threshold_is():
    assert cost.handover_ratio([assistant_row(usage(created=40_000))]) is None


def test_summarise_reports_the_handover_ratio():
    got = cost.summarise(_growing_rows())
    assert got["handover_ratio"] == pytest.approx(60_000 / 135_000, abs=0.001)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd plugins/worklog && python3 -m pytest lib/worklog/tests/test_cost.py -q`
Expected: FAIL — `AttributeError: module 'worklog.cost' has no attribute 'handover_threshold'`

- [ ] **Step 3: Add the two functions**

Insert into `plugins/worklog/lib/worklog/cost.py` immediately after `payback_context`:

```python
def handover_threshold(rows: Iterable[dict[str, Any]]) -> int | None:
    """Context at which a fresh session repays its cache rebuild inside one message."""
    rows = list(rows)
    calls = list(billed_calls(rows))
    if not calls:
        return None
    multiple = read_multiple(calls[-1][0])
    if multiple is None:
        return None
    return payback_context(
        baseline_tokens(rows), session_write_multiplier(rows), multiple, calls_per_message(rows)
    )


def handover_ratio(rows: Iterable[dict[str, Any]], current: int | None = None) -> float | None:
    """How far the session has come toward that threshold; 1.0 means a handover is due.

    Falls when the context does, so a compaction reads as the room it actually buys.
    """
    rows = list(rows)
    threshold = handover_threshold(rows)
    if not threshold:
        return None
    if current is None:
        calls = list(billed_calls(rows))
        current = context_tokens(calls[-1][1]) if calls else 0
    return current / threshold
```

- [ ] **Step 4: Publish it from `summarise`**

In `summarise`, add one line beside the other derived values (after `passed_at = …`, ~line 260):

```python
    ratio = handover_ratio(rows)
```

and one key to the returned dict, after `"breakeven_messages"`:

```python
        "handover_ratio": round(ratio, 3) if ratio is not None else None,
```

- [ ] **Step 5: Run the tests**

Run: `cd plugins/worklog && python3 -m pytest lib/worklog/tests -q`
Expected: PASS, 143 passed (136 baseline + 7 new)

- [ ] **Step 6: Commit**

```bash
git add plugins/worklog/lib/worklog/cost.py plugins/worklog/lib/worklog/tests/test_cost.py
git commit -m "Add handover readiness ratio to the cost model"
```

---

## WP2 — the status line shows the percentage ([#10](https://gitlab.beissbarth.cloud/wega2/bb_ai_marketplace/-/issues/10))

**Files:**
- Modify: `plugins/worklog/lib/worklog/statusline.py:16,32-37,40-53,85-90`
- Test: `plugins/worklog/lib/worklog/tests/test_statusline.py`

**Consumes:** `cost.handover_ratio` from WP1.
**Produces:** `statusline.handover_label(ratio: float) -> str`, `statusline.HANDOVER_NEAR_RATIO`,
`statusline.session_rows(path) -> list[dict] | None`.

- [ ] **Step 1: Replace the label tests**

In `plugins/worklog/lib/worklog/tests/test_statusline.py`, delete the seven tests from
`test_an_unsettled_calculation_is_green_and_carries_no_figure` (line 170) through
`test_every_coloured_label_is_closed` (line 203) and put these in their place:

```python
def test_a_distant_handover_is_green_with_its_percentage():
    label = statusline.handover_label(0.12)
    assert statusline.GREEN in label and plain(label) == "handover 12%"


def test_the_gauge_turns_yellow_as_the_threshold_approaches():
    for ratio in (0.80, 0.90, 0.99):
        label = statusline.handover_label(ratio)
        assert statusline.YELLOW in label, ratio
        assert plain(label) == f"handover {round(ratio * 100)}%"


def test_a_passed_threshold_is_red_and_keeps_counting():
    label = statusline.handover_label(1.7)
    assert statusline.RED in label and plain(label) == "handover due · 170%"


def test_the_threshold_itself_reads_as_due():
    assert plain(statusline.handover_label(1.0)) == "handover due · 100%"


def test_colour_follows_the_percentage_actually_shown():
    assert statusline.GREEN in statusline.handover_label(0.799)
    assert statusline.YELLOW in statusline.handover_label(0.801)


def test_every_coloured_label_is_closed():
    for ratio in (0.1, 0.85, 1.4):
        assert statusline.handover_label(ratio).endswith(statusline.RESET)
```

- [ ] **Step 2: Update the whole-line tests**

Same file, replace these assertions with the values the new label produces (each verified against
the fixtures already in the file):

- line 75 — `test_the_line_carries_context_rate_spend_and_handover`:
  `assert line == "ctx 400k 40% · $0.20/call · $5.83 · handover 48%"`
- line 107 — `test_a_fresh_session_that_would_be_no_smaller_reads_as_no_advantage`: rename to
  `test_a_small_session_reads_as_a_low_percentage` and assert
  `plain(statusline.build_line(data)).endswith("handover 5%")`
- line 129 — `test_a_handover_already_worth_it_is_recommended`: rename to
  `test_a_handover_already_worth_it_reads_as_due` and assert
  `"handover due · 333%" in plain(statusline.build_line(data))`
- line 150 — `test_a_recommended_handover_counts_the_messages_since`: rename to
  `test_a_passed_threshold_shows_how_far_past_it_is` and assert
  `"handover due · 113%" in plain(statusline.build_line(data))`
- line 159 — `test_a_session_opened_with_a_slash_command_counts_messages`: assert
  `"handover 48%" in plain(statusline.build_line(data))`
- line 167 — `test_the_label_waits_for_a_message_to_count`: assert
  `"handover" not in plain(statusline.build_line(data))`
- line 221 — `test_the_label_counts_what_the_pickup_had_to_read`: assert
  `"handover 71%" in line`

- [ ] **Step 3: Run them and watch them fail**

Run: `cd plugins/worklog && python3 -m pytest lib/worklog/tests/test_statusline.py -q`
Expected: FAIL — the label still reads `handover threshold near (2 msg)`

- [ ] **Step 4: Rewrite the label and its caller**

In `plugins/worklog/lib/worklog/statusline.py`, replace `PAYBACK_NEAR_MESSAGES = 5` (line 16) with:

```python
HANDOVER_NEAR_RATIO = 0.8
```

Replace `session_report` (lines 32-37) with:

```python
def session_rows(path: str | None):
    """The transcript's rows, or None when there is nothing billed to read."""
    if not path or not Path(path).exists():
        return None
    rows = list(transcript.read_rows(path))
    return rows if any(True for _ in cost.billed_calls(rows)) else None
```

Replace `handover_label` (lines 40-53) with:

```python
def handover_label(ratio: float) -> str:
    """How far the session is from the point a fresh one pays for itself.

    Green while there is room, yellow as the threshold comes into reach, red once it is past —
    and there the figure keeps climbing, so it says how far past.
    """
    percent = round(ratio * 100)
    if ratio >= 1.0:
        return f"{RED}handover due · {percent}%{RESET}"
    colour = YELLOW if ratio >= HANDOVER_NEAR_RATIO else GREEN
    return f"{colour}handover {percent}%{RESET}"
```

Replace the tail of `build_line` (lines 85-90) with:

```python
    rows = session_rows(payload.get("transcript_path"))
    ratio = cost.handover_ratio(rows, context) if rows is not None and context else None
    if ratio is not None:
        parts.append(handover_label(ratio))
```

- [ ] **Step 5: Run the tests**

Run: `cd plugins/worklog && python3 -m pytest lib/worklog/tests -q`
Expected: PASS, 142 passed (143 from WP1, seven label tests replaced by six)

- [ ] **Step 6: Check it against a live transcript**

```bash
t=$(ls -t ~/.claude/projects/*/*.jsonl | head -1)
printf '{"model":{"id":"claude-opus-5[1m]"},"context_window":{"total_input_tokens":240000,"context_window_size":1000000},"cost":{"total_cost_usd":1.23},"transcript_path":"%s"}' "$t" \
  | PYTHONPATH=plugins/worklog/lib python3 -m worklog.statusline
```
Expected: a line ending in `handover NN%` or `handover due · NNN%`, no `msg` figure.

- [ ] **Step 7: Commit**

```bash
git add plugins/worklog/lib/worklog/statusline.py plugins/worklog/lib/worklog/tests/test_statusline.py
git commit -m "Show handover readiness as a percentage in the status line"
```

---

## WP3 — say the same thing in `worklog cost`, and release ([#11](https://gitlab.beissbarth.cloud/wega2/bb_ai_marketplace/-/issues/11))

Keeps the two surfaces telling one story: the report currently says "pays back after 0.5 messages"
where the line now says "handover due · 170%". Drop this package if the report should stay as it is.

**Files:**
- Modify: `plugins/worklog/lib/worklog/cli.py:152-161`
- Modify: `plugins/worklog/.claude-plugin/plugin.json:4`
- Test: `plugins/worklog/lib/worklog/tests/test_cli.py`

**Consumes:** the `"handover_ratio"` key from WP1.

- [ ] **Step 1: Write the failing test**

Append to `plugins/worklog/lib/worklog/tests/test_cli.py`:

```python
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
```

The `workspace` fixture, `SLUG` and `SESSION` are already defined at the top of `test_cli.py`
(lines 9-10, 45-58); it points `CLAUDE_CONFIG_DIR` and `CLAUDE_CODE_SESSION_ID` at a temporary
transcript, which this test overwrites with rows that carry billable usage. Threshold for these
rows is 135,000 tokens against a 10,000-token context, so the report reads 7%.

- [ ] **Step 2: Run it and watch it fail**

Run: `cd plugins/worklog && python3 -m pytest lib/worklog/tests/test_cli.py -q`
Expected: FAIL — "readiness" not in output

- [ ] **Step 3: Print the line**

In `cmd_cost`, after the existing `handoff` block (`cli.py:161`):

```python
    ratio = report["handover_ratio"]
    if ratio is not None:
        print(f"readiness {ratio * 100:.0f}% of the way to a worthwhile handover")
```

- [ ] **Step 4: Run the tests**

Run: `cd plugins/worklog && python3 -m pytest lib/worklog/tests -q`
Expected: PASS, 143 passed

- [ ] **Step 5: Bump the version**

In `plugins/worklog/.claude-plugin/plugin.json`, `"version": "1.4.0"` becomes `"version": "1.5.0"`.

- [ ] **Step 6: Commit**

```bash
git add plugins/worklog/lib/worklog/cli.py plugins/worklog/lib/worklog/tests/test_cli.py plugins/worklog/.claude-plugin/plugin.json
git commit -m "Report handover readiness in worklog cost and bump to 1.5.0"
```

---

## Afterwards

The install does not pick up a new version by itself — `claude plugin update worklog@bb-ai-marketplace`
had to be run by hand to materialise 1.4.0 in the cache, and the status line only changes once the
new version directory exists.

## Known and not addressed

`messages_overdue` stays in the `summarise` dict for the `--json` contract, still non-monotone and
still unused by anything that renders. Removing it is a breaking change to that contract and wants
its own decision.
