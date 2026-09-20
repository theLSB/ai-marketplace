---
name: swarm
description: Run a task through a multi-agent boss/worker/checker team instead of doing it directly. Use when the user invokes /swarm, or asks to "run this as a swarm", "use the agent team", or wants a big piece of work (a website, a document set, a research pass, a migration) done with independent verification baked in rather than trusted to a single pass. Best for tasks with an objective definition of done that a checker can verify without re-deriving your reasoning.
disable-model-invocation: true
---

# Swarm: boss / worker / checker orchestration

This skill runs `args` (the task description) through an org-chart pattern
instead of doing the work yourself in one pass: an expensive **boss** agent
writes the spec and rules on disputes but never implements anything; cheap
**worker** agents do the actual work; independent **checker** agents
re-verify each result from primary sources without trusting the worker's own
report. No task is marked done because a worker said so — only because a
checker, working blind to the worker's reasoning, re-derived the same
answer.

The point isn't that cheap models don't make mistakes. They do, constantly.
The point is that the structure catches it without you reading every
intermediate result. Your job as orchestrator is to run the loop and report
the ledger, not to inspect each task yourself.

## Roles

Use the `Agent` tool with these `subagent_type`s (defined in this project's
`agents/` directory — install them first if they're not showing up):

- `swarm-boss` — spec, dispute rulings, final review. Never implements.
- `swarm-worker` — does the actual work for one task.
- `swarm-checker` — independently re-verifies one completed task.

If a task is unusually hard (needs real reasoning, not just following a
spec), it's fine to bump that one worker call to `model: sonnet` via the
Agent tool's model override instead of using a `swarm-worker` at its default
tier. Keep the default cheap — only upgrade the specific tasks that need it.

## The loop

### 0. Optional: audition unfamiliar models

If you're routing work to a model/tool combination you haven't used in this
pattern before and want confidence before committing a whole task category
to it, give it one small, checkable trial task first (something with an
objectively verifiable output) before assigning it real work. Skip this for
combinations you already trust.

### 1. Get the constitution

Spawn `swarm-boss` (foreground — you need its output before anything else
can start) with the task description. It returns:

- The constitution: concrete, testable criteria for "done."
- A task list: discrete, independently-checkable units of work, each with
  acceptance criteria drawn from the constitution.

Show the constitution and task list to the user briefly before burning
tokens on execution — a one-paragraph summary, not the full text, unless
they ask for it. If something looks obviously wrong (missed requirement,
scope creep), fix it with the user before proceeding. Otherwise, proceed
without asking for step-by-step approval — that's the entire point of
writing the constitution up front instead of prompting task-by-task.

### 2. Work each task

For each task (parallelize independent ones with `run_in_background`, keep
dependent ones sequential):

1. Spawn `swarm-worker` with: the task, its acceptance criteria, and the
   full constitution. Do **not** give it other workers' self-reports —
   only the artifacts/state it actually needs to do its job.
2. When it reports done, spawn a **fresh** `swarm-checker` (new context —
   it must not inherit the worker's conversation) with: the acceptance
   criteria, the constitution, and a pointer to where the output lives.
   Do not pass along the worker's narrative or reasoning.
3. Checker returns PASS or FAIL+specific reason, or flags that the check
   itself seems wrong.
   - **PASS** → mark the task done in your ledger, move on.
   - **FAIL** → send the checker's specific reason back to the *same*
     worker session (continue it, don't restart fresh) to fix. Increment a
     retry counter. Re-check. Cap at 3 rounds per task.
   - **Worker disputes the FAIL**, or the **checker flags its own criteria
     as wrong** → escalate to `swarm-boss` with the acceptance criteria,
     the worker's output, and the checker's rejection reason. Apply the
     ruling. If the boss says the checker was wrong, note that in the
     ledger as a miscalibrated check, not a worker win.
   - Retry cap hit with no resolution → stop and surface it to the user
     instead of shipping a failing task silently.

### 2a. Time-box every backgrounded agent

Any worker or checker running in the background is on a 15-minute clock.
When you spawn one, schedule a wakeup (`ScheduleWakeup`) ~15 minutes out. If
it's still running when that wakeup fires:

1. Interject with a message asking it to pause and report exactly what it's
   doing and how far it's gotten — don't let it keep working past this point
   without a go-ahead.
2. Relay that status (elapsed time, what it's doing, why it might be taking
   long) to the user.
3. Let the user decide: resume it (send a message telling it to continue),
   or abort it (`TaskStop`) — folding the abort into the ledger as a stall
   rather than silently retrying.

Re-arm the 15-minute wakeup each time an agent is allowed to continue, so a
genuinely long task gets checked in on repeatedly, not just once.

This is the orchestrator's job, not the boss's. The boss is spawned on
demand for spec/dispute work and returns when done — it has no standing to
run on a timer or inspect a sibling agent's progress. Only the orchestrator
holds the scheduling and monitoring tools, so it's the one that watches the
clock.

### 3. Final review

Once every task is PASS, spawn `swarm-boss` once more for a holistic review
against the full constitution — cross-task consistency, gaps no single
task's checker would catch. Anything it finds becomes a new task, run
through the same worker→checker loop. Don't let the boss fix it directly.

### 4. Report the ledger, not the transcript

Summarize for the user: total tasks, how many needed retries and why, how
many disputes were escalated and how they were resolved, what the final
boss review caught (if anything), and where the finished output lives. This
is the artifact that replaces reading every individual agent's output —
keep it tight enough that skipping the details was actually worth it.

## Notes

- Nothing is exempt from checking, including the boss's own output in the
  final review pass. Rank in the org chart doesn't buy a pass on
  verification.
- A checker rejecting a worker isn't assumed correct by default — disputes
  are real and get investigated in both directions. A checker being
  overruled means the check was miscalibrated, which is useful signal for
  next time, not noise to ignore.
- This pattern is generic — it doesn't care whether the task is code, prose,
  research, or anything else with a checkable definition of done. What
  changes per task is the constitution's criteria and what tools the worker
  and checker need, not the loop itself.
