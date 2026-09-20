---
name: handoff-check
description: Work out whether this session is still worth continuing, or whether compacting or handing off would now pay for itself.
argument-hint: "How much work is left - a few turns, a stretch, or a long way?"
disable-model-invocation: true
---

Read what this session costs to keep going, work out when a fresh one would repay itself, and recommend continuing, compacting, or handing off. Recommend only - the choice is the user's.

## 1. Read the numbers

```bash
worklog cost --json
```

It resolves the current session on its own. The fields that matter:

- `context_tokens` - the whole conversation, re-read on every API call.
- `read_cost_per_call_usd` - what the next API call pays before it does anything.
- `session_cost_usd` - spent so far.
- `fresh_tokens` - what a fresh session would start at, measured from this session's own first call.
- `breakeven_messages` - **messages** before a fresh session repays the cache it has to rebuild. `null` means either that it never does, or that no message has been sent yet.
- `breakeven_calls` and `calls_per_message` - the same figure in API calls, and the ratio between the two.

Use `breakeven_messages`. One message fans out into several API calls - measured between 4 and 48 depending on how tool-heavy the work is - so a payback quoted in calls reads as far larger than it is. Fall back to `breakeven_calls` only when `breakeven_messages` is `null` because nothing has been typed yet, and say which unit you are quoting.

If the command is not found, the worklog plugin is not installed - say so and stop. If it reports no session, say so and stop rather than guessing at numbers.

## 2. Ask the one thing the transcript cannot tell you

`breakeven_messages` says when a reset repays itself. Whether that is worth having depends on how much work is left, which only the user knows.

If the user passed an argument, treat it as the answer. Otherwise ask with AskUserQuestion, offering: a message or two, a handful (3-10), a long way to go (10+). Ask in messages - it is what the user counts, and it is the unit the comparison uses.

## 3. Compare

Call the payback `P` and the messages still expected `T`, both in messages:

- `P` is `null` - **continue**. A fresh session would be no smaller, so there is nothing to win.
- `P` below 1 - **reset**. The handoff repays itself inside the next message, whatever happens after.
- `T` below `P` - **continue**. The work finishes before a reset pays for itself.
- `T` between `P` and twice `P` - **marginal**. Continue unless the work is already at a natural seam.
- `T` at least twice `P` - **reset**, and the next section picks which kind.

## 4. Compact or hand off

Both rebuild the cached prefix and cost the same to rebuild. What differs is what survives.

- **`/compact`** when the work continues in the same thread and nothing needs to outlive the session. Cheapest, and the model chooses what to keep.
- **The `handoff` skill** when the work is at a seam, or when the context should persist to disk for a later session. It costs one extra turn to write the document, and what it keeps is curated rather than guessed.

## 5. Say it, then let the user choose

Lead with the recommendation in one line, with the two figures behind it - what a turn now costs to re-read, and the payback against the turns expected. Then ask with AskUserQuestion, recommended option first: continue, compact, hand off.

On "hand off", invoke the `handoff` skill with the Skill tool rather than writing a summary here. On the others, do nothing further - the user carries on, or runs `/compact` themselves.

## What this does not price

The arithmetic covers money only. It cannot see whether the work sits at a natural seam, or how much rework a lossy handoff would cause - and rework costs far more than the cache ever will. Say so when the call is marginal, and leave the judgment to the user.
