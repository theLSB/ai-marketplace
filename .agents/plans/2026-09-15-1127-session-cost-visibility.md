# Session cost visibility and handoff break-even

Branch: `feature/session-cost-visibility` (off `feature/vendor-quest-skills`)
Cards: [#1](https://gitlab.beissbarth.cloud/wega2/bb_ai_marketplace/-/issues/1), [#2](https://gitlab.beissbarth.cloud/wega2/bb_ai_marketplace/-/issues/2), [#3](https://gitlab.beissbarth.cloud/wega2/bb_ai_marketplace/-/issues/3)

## The thread

One cost model, three deliverables. The arithmetic that says "this session now costs $0.18/turn just to re-read itself, and a handoff repays in 3 turns" is a single piece of logic; everything else is a way of putting it in front of you. So the logic gets built once, with tests, in the library that already reads session transcripts — and the statusline and the skill both consume it rather than re-deriving it. WP1 is usable on its own from the CLI, WP2 makes it continuous and free, WP3 turns it into a decision and is gated on whether it is still wanted after living with WP2.

## The arithmetic

A turn re-reads the whole conversation from cache. At a context of `N` tokens that costs `N × read_rate` every turn, whether or not the turn does anything.

Handing off to a fresh session of `M` tokens costs `M × write_mult` once, then `M × read_rate` per turn. So it repays in:

```
T = (M × write_mult) / ((N − M) × read_rate)
```

With the 1h TTL on a 0.1× cache read that is `T = 20 / (N/M − 1)`. What decides it is the **ratio**, not the absolute size:

| N/M | turns to repay |
|-----|----------------|
| 10  | 2.2 |
| 4   | 6.7 |
| 2   | 20 (rarely worth it) |

Measured: session `374e17b1` ended at 360,066 cache-read tokens on Opus 5 — a **$0.18/turn floor just to re-read itself**. A 40k fresh session is in profit after 3 turns.

## Load-bearing claims

| Claim | Status |
|---|---|
| Settings accepts `statusLine: {type:"command", command, padding?, refreshInterval?}` | **verified** — CLI binary `~/.local/share/claude/versions/2.1.272` |
| Payload carries `cost.total_cost_usd`, `context_window.{total_input_tokens, total_output_tokens, context_window_size, current_usage, used_percentage}`, `model.id`, `exceeds_200k_tokens` | **verified** — same binary, `function VAt(e,n)` |
| Transcript rows carry `message.usage.{input_tokens, cache_creation_input_tokens, cache_read_input_tokens, output_tokens}` and `cache_creation.{ephemeral_5m,ephemeral_1h}_input_tokens` | **verified** — `jq` over a live transcript |
| Session lookup already exists: `current_session_id()`, `find_transcript()` | **verified** — `plugins/worklog/lib/worklog/sessions.py:36,48` |
| Row reader already exists: `read_rows()` | **verified** — `plugins/worklog/lib/worklog/transcript.py:25` |
| CLI pattern: `cmd_*(args) -> int`, `subs.add_parser(...)`, `set_defaults(func=…)`, JSON via `json.dump(…, indent=1, ensure_ascii=False)` | **verified** — `plugins/worklog/lib/worklog/cli.py:38,140,145,177` |
| Test pattern: plain pytest fns, row-builder helpers, `conftest.py` puts `lib/` on `sys.path` | **verified** — `plugins/worklog/lib/worklog/tests/conftest.py:1`, `tests/test_transcript.py:1` |
| Pricing: Opus 5 $5/$25 per MTok; cache read 0.1× (Fable 5.1 0.025×); cache write 1.25× (5m) / 2× (1h) | **verified** — bundled `claude-api` skill, `shared/prompt-caching.md:144` + model table |
| `handoff` exists and writes the document | **verified** — `plugins/handoff/skills/handoff/SKILL.md:1` |
| Project `wega2/bb_ai_marketplace` has no labels, so the board has no lists | **verified** — `glab label list`, 0 of 0 |
| Plugin `bin/` lands on PATH | **assumed** — author's docstring, `plugins/worklog/bin/worklog:2`. WP2 step 0 confirms it. |
| `refreshInterval` is seconds | **assumed** — schema shows only `.min(1)`. WP2 step 0 confirms it. |
| `context_window.current_usage` includes the `cache_creation` TTL split, and the payload includes `transcript_path` | **assumed** — WP2 step 0 dumps one real payload and settles both. |

## Options rejected

- **A standalone `session-cost` plugin.** Possible, but it would need either a hardcoded path into `worklog/lib` or its own copy of the session plumbing. The CLI is the clean seam between plugins.
- **Cost logic in the `handoff` plugin.** Possible, but `handoff` has no `lib/` and no tests today, and `worklog` already reads transcripts. Wrong home for it.
- **`/loop` as the periodic check.** The skill exists and would work — but every tick is a billed turn at full context, which is the cost it is meant to report on.
- **A `Stop` hook instead of a statusline.** Viable (`~/.claude/settings.json` already runs one for `speak-response.sh`), but it prints once per turn instead of showing a live number, and adds output nobody asked for.

## WP1 — `worklog cost`: the model and its tests ([#1](https://gitlab.beissbarth.cloud/wega2/bb_ai_marketplace/-/issues/1))

New `plugins/worklog/lib/worklog/cost.py`:

- `PRICES` — model id to input/output $ per MTok plus the per-model cache-read rate.
- `context_tokens(usage)` — input + cache_creation + cache_read.
- `turn_cost(usage, model)` — dollars for one turn.
- `session_cost(rows)` — cumulative across assistant rows, per-row model.
- `write_multiplier(usage)` — 2.0 or 1.25, from the `cache_creation` TTL split.
- `breakeven_turns(current, fresh, write_mult, read_rate)`.
- `baseline_tokens(rows)` — measured floor: context at the first assistant turn. A fresh session starts at system prompt + CLAUDE.md + memory + skills, not zero.

Unknown model ids report tokens and omit dollars. New models appear; a guessed price is worse than none.

`cmd_cost` in `cli.py` following the existing pattern: `worklog cost [--session ID] [--fresh N] [--json]`.

**Verified by:** `pytest plugins/worklog/lib/worklog/tests/` green, including `tests/test_cost.py` covering per-model pricing, unknown-model fallback, 5m vs 1h multiplier selection, break-even at ratios 10/4/2, `fresh >= current` returning never, zero-division guard, and cumulative sum across mixed-model rows. Plus `worklog cost --json` against a real transcript.

## WP2 — the statusline ([#2](https://gitlab.beissbarth.cloud/wega2/bb_ai_marketplace/-/issues/2))

**Step 0 — settle the assumptions.** Point `statusLine.command` at a throwaway script that dumps its stdin to a file, run one turn, read the payload. Confirms `transcript_path`, the `current_usage` shape, PATH resolution, and `refreshInterval` units.

**Then** `plugins/worklog/bin/worklog-statusline`: read the payload, import `cost`, print one line:

```
ctx 54k · 5% · $0.03/turn · $2.14 · payback 12t
```

`payback` uses the measured baseline from the transcript's first assistant turn, and is suppressed when the ratio makes it meaningless.

Wire `statusLine` into `~/.claude/settings.json`. That file is **not** under version control (`~/.claude` is not a git repo), so it is a local config change separate from this repo's commits, shown before it is made.

**Verified by:** the line renders with numbers matching `worklog cost --json` for the same session.

## Checkpoint

Live with the statusline. Then decide whether WP3 still earns its place.

## WP3 — `/handoff-check` (gated) ([#3](https://gitlab.beissbarth.cloud/wega2/bb_ai_marketplace/-/issues/3))

`plugins/handoff/skills/handoff-check/SKILL.md`, frontmatter matching `handoff`.

It shells out to `worklog cost --json`, asks how many turns are still expected, and recommends continue / `/compact` / `handoff` — chaining into the existing skill rather than re-implementing it.

No unit tests here, and that is the point of the split: the skill carries no arithmetic. All of it is in WP1, already tested.
