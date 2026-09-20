---
name: work-report
description: Compile a report of work done from the session logs on this machine, deciding with the user what is named and what is generalised.
argument-hint: "Which period, and who is the report for?"
disable-model-invocation: true
---

Turn the session logs written by `session-logger` into one report for a period. The logs are the only source of what was done; this skill decides, with the user, what reaches the reader.

## 1. Settle the period and the reader

Take both from the arguments if they are there. Otherwise ask with AskUserQuestion: the period (last week, last month, a named span) and who reads it (their manager, the team, themselves).

The reader decides the altitude. A manager wants themes and outcomes; a team wants the specifics.

## 2. Gather the material

```bash
worklog logs --since 2026-09-01 --until 2026-09-30
worklog sessions --since 2026-09-01 --unlogged
```

`logs` lists the work logs in the span - read every one. `sessions --unlogged` lists sessions in the same span with no log; those are invisible to the report.

Show the user the unlogged list, briefly, and ask whether to write logs for any of them first. If they say yes, follow the `session-logger` skill for each, passing `--session <id>` to `digest` and `append` - a past session logs from its transcript exactly as well as a live one.

Never read raw transcripts to fill gaps in the report itself. The logs are the record; an unlogged session is a session the user chose not to report on.

## 3. Agree what gets named

Before writing, put the inventory to the user: the tasks found, grouped into candidate themes, with a one-line proposal per theme - named explicitly, folded into a generalisation, or dropped.

Say plainly which ones you would name and why. Wait for their calls, then write. This step is the point of the skill; do not skip it and produce a finished report.

## 4. Write the report

```markdown
# Work report - September 2026

**Period** 2026-09-01 to 2026-09-30 · **Projects** jacqueline-titan, bb-conan · **Sessions** 14

## Highlights
- Three to six lines. Outcomes, not activity.

## <Theme>
What was delivered, what it was for, where it stands. Name the concrete pieces
the user asked to name; generalise the rest into a sentence.

## Open and abandoned
What was dropped or is still open, and why - short.
```

Every claim traces to a log entry. Where the logs do not say, the report does not say - report thin coverage as thin coverage rather than padding it.

Counts (sessions, tasks, files, projects) come from the logs you read, never from an estimate.

Write it to `~/.claude/worklogs/reports/<YYYY-MM-DD>--<slug>.md`, where `<slug>` is three to five kebab-case words naming the period or subject. Print the path.

Then offer, in one line, to publish it as an Artifact for sharing. Do not publish unasked.
