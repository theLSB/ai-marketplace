---
name: pickup
description: Pick up where an earlier session left off - read a handoff document, check it still holds, and continue the work it describes.
argument-hint: "Which handoff to pick up, or 'list' to choose from all of them"
disable-model-invocation: true
---

Read a handoff document, read what it points at, check it still describes reality, then continue the work.

## 1. Find the handoff

Handoffs live in `.agents/handoffs/`, named `<date>-<slug>.md` with `<date>` as `YYYY-MM-DD-HHMM`, so the last one alphabetically is the newest:

```bash
ls .agents/handoffs/*.md | tail -1
```

If the user passed arguments, treat them as which handoff to pick up - a path, a slug or a date - and use that one instead.

`list`, `ls` or `all` as the argument means pick from all of them rather than the latest. Read
every handoff's title - its first `# ` line - and print one numbered line each, newest first:

```bash
for f in $(ls -r .agents/handoffs/*.md); do echo "$f - $(head -1 "$f")"; done
```

```
1. 2026-09-11-1601-ai-skills-plugin-mvp - MVP to ship the department's skills as Claude Code plugins
2. ...
```

Then stop and wait for the user to name one. A number picks that line; a slug or a date names
the handoff just as well. Choose nothing yourself, and read no handoff until they answer.

If the directory is missing or empty, say so and stop. Do not reconstruct the work from git history instead.

A `/tmp/claude-handoff-*.md` file belongs to an agent that was already spawned to pick it up. Leave it alone unless the user hands you the path.

## 2. Read it, and read what it points at

Read the whole document before acting on any part of it.

A handoff holds none of what other artifacts already hold - specs, plans, ADRs, issues, commits, earlier handoffs. It references them instead, so the handoff alone is not the context. Follow the references.

Handoffs chain. If it names earlier handoffs, read them in the order it asks, oldest first, so the decisions arrive before the conclusions that rest on them.

What it records as settled is settled. It says what was ruled out and why so that it is not reopened.

## 3. Check it still holds

Time has passed since it was written. Verify the cheap facts it needs you to act on: branch and working tree, that the paths and files it names still exist, the state of any ticket or card it points to.

Do not re-derive what it records as verified. Check that what it names still exists, not that its conclusions were right.

Report any drift in a line each, before continuing. Something having moved is not a reason to stop - it is a reason to say so.

## 4. Invoke the skills it suggests

Its **Suggested skills** section names skills for you. Invoke them with the Skill tool before starting the work, unless one is plainly wrong for where the work has since gone.

## 5. Continue the work

Say which handoff you picked up, where the work stopped and what you are doing next - a line each. Then do it.

Ask first only if the next step is gone, or if the drift makes it the wrong step.
