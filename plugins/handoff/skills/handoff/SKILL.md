---
name: handoff
description: Hand the current conversation off to a fresh agent - spawned now in the background, or saved as a handoff document for later.
argument-hint: "What will the next session be used for?"
disable-model-invocation: true
---

Write a handoff summary of the current conversation, check a fresh reader can act on it, then either spawn an agent with it now or save it for later.

## 1. Write the summary

**History** - how the work arrived here. The turns that changed direction: what was tried, what was ruled out and why, what the user corrected. Not a transcript - it exists to give the next agent the same footing and sense of direction this session ended with. Name any decisions already settled, so they are not reopened.

**Current state** - where the work stopped. What is done, what is in progress, what the next step is, and the details needed to resume it: paths, branch, commands, failing test names, error text.

**Suggested skills** - which skills the next agent should invoke with the Skill tool.

Do not duplicate what other artifacts already hold (specs, plans, ADRs, issues, commits, diffs). Reference them by path or URL.

Redact secrets and personal data - keys, passwords, tokens, PII. The summary is read by another agent and may be written to disk.

If the user passed arguments, treat them as what the next session will focus on and tailor the summary to it.

## 2. Check a fresh reader can act on it

Dispatch a subagent with the Agent tool (fresh context, not a fork; haiku is enough) and give it the summary. Ask it to report only what it cannot resolve from the summary alone: references it cannot follow, missing paths or names, steps it could not act on.

It has none of this session's context, so it catches dangling references, not facts left out. Fix what it finds. Re-check once if the fixes were substantial, then stop.

## 3. Ask what to do with it

Ask the user with AskUserQuestion:

- **Save and log** - write the handoff document, then log the session.
- **Save for later** - write the handoff document and stop.
- **Continue now** - spawn a background agent that picks the work up immediately.

Offer **Save and log** only when the `worklog:session-logger` skill is available - it ships in the separate `worklog` plugin.

### Save and log

Write the document as under **Save for later**, then invoke `worklog:session-logger` with the Skill tool and follow it. Print both paths - the handoff document and the log file.

### Save for later

Write the summary to `.agents/handoffs/<date>-<slug>.md` and print the path. Spawn nothing.

### Continue now

Write the summary to `/tmp/claude-handoff-<slug>.md`, then spawn:

```bash
claude --bg --name "<name>" "Read /tmp/claude-handoff-<slug>.md, delete it, then continue the work it describes."
```

Never put the summary itself in the command. It contains quotes, backticks and `$`, which the shell mangles or executes.

`-n`/`--name` is required - it is the display name in the job list, session picker and terminal title. Use the slug's wording.

The command returns immediately. Give the user the agent's name, and note that `claude agents`, `claude logs <id>` and `claude attach <id>` manage it.

## Naming

`<slug>` is three to five kebab-case words naming the topic, never a hash: `conan-cache-contamination`, `fix-login-redirect-loop`. `<date>` is `YYYY-MM-DD-HHMM`, so handoffs sort by time and no two collide.
