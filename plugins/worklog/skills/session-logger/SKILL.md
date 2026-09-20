---
name: session-logger
description: Write what this session did into the machine's work log - one entry per task, read from the session transcript - or append a note to it.
argument-hint: "Nothing, or `append <what to record>`"
disable-model-invocation: false
---

Read this session's own transcript, group it into tasks, and append one entry per task to the session's work log. The `work-report` skill later compiles reports out of these logs.

The transcript is the source, not your context. Anything compacted away is still in the file, so a long session logs as completely as a short one.

**If the arguments start with `append`, go straight to "Appending a note" at the end** - none of the steps below apply. Anything else, including no arguments, logs the session.

## 1. Read what happened

```bash
worklog digest
```

Prints JSON: the session's facts, and every turn not yet logged - prompt, your replies, tools used, files changed and read.

**Check `log_exists` and `watermark` first.** When this session already has a log, you are extending it: the turns returned are the only ones missing, everything before the watermark is already written, and you must not re-read or re-log it. This is the normal case when the session carried on after an earlier run.

If `turns_pending` is 0, or the only turn returned is the invocation of this skill, nothing has happened since the last run. Say so in one line and stop - do not write an entry.

The last turn is always the one that invoked this skill, directly or through another skill such as `handoff`. Ignore it when writing entries.

Use `--all` to re-read the whole session, `--max-prompt 0 --max-reply 0` to stop it clipping long text. `--all` is for rewriting a log from scratch, and the entries it produces replace nothing - delete the log file first if that is what you mean.

## 2. Group turns into tasks

A task is one thing the user wanted done, not one prompt. Several turns of iterating on the same fix are one task; a prompt that changed direction starts a new one. A question answered in one turn is still a task.

Keep it granular - this is the detailed level. Do not merge unrelated work to make the log shorter; the report skill is where things get generalised, and it can only generalise what is written here.

Every turn lands in exactly one entry. If the work was abandoned or superseded, it still gets an entry saying so - that is the part a report would otherwise invent.

## 3. Write the entries

One block per task, oldest first, fields omitted when empty:

```markdown
## Refine Jacqueline head IP validation

- **kind**: change
- **when**: 2026-09-10 10:04 → 10:41 (turns 3-7)
- **where**: jacqueline-titan · dk_test_logic
- **asked**: LEDs stayed yellow when an endpoint was edited to an invalid IP.
- **did**: Validation moved ahead of the connection test; LED reset on invalid input.
- **files**: src/SettingsDlg.cpp, src/JacquelineDlg.cpp
- **outcome**: done, unit tests pass
- **notes**: Rejected debouncing the field - the test is already async.
```

`kind` is one of `change`, `investigation`, `decision`, `support` (questions answered, explanations, environment fixes) or `note`. `outcome` is what actually happened: done, tests pass, abandoned, superseded, open. `notes` carries decisions taken and options ruled out - the things nothing else on disk records.

Write what was done, not how it went. No narration of your own process, no tool-by-tool retelling.

Redact secrets, tokens, keys and personal data. These logs are read later and quoted into reports.

If the user passed arguments, treat them as what to emphasise or leave out.

## 4. Commit them to the log

Write the entries to a scratch file, then:

```bash
worklog append --file <scratch.md>
```

It creates or extends `~/.claude/worklogs/<date>--<project>--<session-id>.md`, refreshes the frontmatter and advances the watermark to the newest turn. Print the path it reports and stop.

Never edit a log file by hand - the watermark lives in its frontmatter and `append` is what keeps it true.

## Appending a note

`/session-logger append <what to record>` adds one note to this session's log and logs no turns. It is for what the transcript cannot show: something tested by hand, a decision taken away from the keyboard, a correction to an entry already written.

If nothing follows `append`, ask what to record, in one line.

Write it as an entry of kind `note`, timed now, naming the entry it qualifies when it qualifies one:

```markdown
## Note: LED fix still untested on hardware

- **kind**: note
- **when**: 2026-09-10 16:20
- **refers to**: Refine Jacqueline head IP validation
- **did**: Checked in the simulator only; the head is not on the bench until Friday.
```

Then append it with the watermark left where it is:

```bash
worklog append --file <scratch.md> --keep-watermark
```

`--keep-watermark` is not optional here. Without it the note advances the watermark to the newest turn, and every turn of real work still waiting to be logged is skipped for good.

A note never rewrites an existing entry - the log is append-only, and a correction is a new note that says what changed.
