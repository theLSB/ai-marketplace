# bb_ai_marketplace

A Claude Code plugin marketplace for the skills and agents we author ourselves. It is one
marketplace among however many you have added - adding it does not disturb `superpowers`,
the official catalogue, or anything else.

| Plugin | Contains | What it is for |
|---|---|---|
| `swarm` | skill `swarm`, agents `swarm-boss`, `swarm-worker`, `swarm-checker` | Run a task through a boss/worker/checker team, with the checker verifying independently |
| `worklog` | skills `session-logger`, `work-report`, command `worklog` | Record what a session did, then compile reports out of those logs |
| `handoff` | skills `handoff`, `pickup` | Hand a conversation to a later session, and pick it up again |
| `quest` | skill `quest` | One entry point for planning work - routes to `grilling` or `wayfinder` |
| `grilling` | skill `grilling` | Stress-test a plan, decision or idea, one question at a time |
| `wayfinder` | skill `wayfinder` | Chart an effort too big for one session as a map of decision tickets |
| `domain-modeling` | skill `domain-modeling` | Build and sharpen a project's domain model |
| `research` | skill `research` | Investigate against primary sources and capture the findings in the repo |
| `prototype` | skill `prototype` | Build a throwaway prototype to answer a design question |

The last five come from [`mattpocock/skills`](https://github.com/mattpocock/skills); see
[Vendored skills](#vendored-skills).

**Using these plugins?** Read [Part 1](#part-1---using-the-plugins).
**Writing or releasing one?** Read [Part 2](#part-2---developing-a-plugin).

---

# Part 1 - Using the plugins

Steps 1 to 4 are in the order they have to happen. What follows them is reference.

## 1. Get access to the repo

The marketplace is a **private** GitLab project, `wega2/bb_ai_marketplace` on
`gitlab.beissbarth.cloud`, and Claude Code installs it by cloning. Read access is the only
real prerequisite, and without it the command fails as a git error rather than a plugin
error.

Ask an owner for read access (Reporter or above) on
[`wega2/bb_ai_marketplace`](https://gitlab.beissbarth.cloud/wega2/bb_ai_marketplace), then
give git a way in - Claude Code clones with your own git config and keys, having no
credentials of its own.

**With SSH**, the simplest path: add your key under
[Preferences - SSH Keys](https://gitlab.beissbarth.cloud/-/user_settings/ssh_keys) and
check it. A list of refs is the whole test.

```bash
git ls-remote git@gitlab.beissbarth.cloud:wega2/bb_ai_marketplace.git
```

**With a token**, where a key is not an option - a shared machine, a locked-down laptop.
Create a **personal access token** with the **`read_repository`** scope at
[Preferences - Access Tokens](https://gitlab.beissbarth.cloud/-/user_settings/personal_access_tokens),
then hand it to git once, running `git config --global credential.helper store` first if
that is not already set:

```bash
printf 'protocol=https\nhost=gitlab.beissbarth.cloud\nusername=oauth2\npassword=<your-token>\n\n' \
  | git credential approve
```

The username is literally `oauth2`; the token is the password. Then use the HTTPS URL,
`https://gitlab.beissbarth.cloud/wega2/bb_ai_marketplace.git`, everywhere the SSH one
appears below. On a shared or build machine prefer a project **deploy token** of the same
scope over your personal one, with its own username in place of `oauth2`. An expired token
shows up as installs and updates failing to authenticate, and nothing else.

**Keep the token out of the URL.** Claude Code records the source you give it verbatim in
`~/.claude/plugins/known_marketplaces.json` and in `settings.json`, so a
`https://oauth2:<token>@...` URL leaves the token in plaintext in two files people copy
between machines. The credential store keeps it out of both.

## 2. Possible name conflicts with existing skills

Skill names resolve across every source, highest first:
**enterprise > `~/.claude/skills` > project `.claude/skills` > plugin**. A copy of one of
*these* names in `~/.claude/skills` therefore beats the plugin and never updates, silently
- so installing over it changes nothing you can see. Only a name this marketplace also
ships can collide; everything else in that folder is untouched by any of this and should
stay where it is.

The names that can collide are the skills the marketplace can list. See what you already have:

```bash
ls ~/.claude/skills ~/.claude/agents
```

Anything on that list which has the same name as skill from the marketplace will shadow the marketplace skill.


## 3. Install

First, register the marketplace:
```bash
claude plugin marketplace add git@gitlab.beissbarth.cloud:wega2/bb_ai_marketplace.git
```
Then install with:
```bash
claude plugin install swarm@bb-ai-marketplace
claude plugin install worklog@bb-ai-marketplace
claude plugin install handoff@bb-ai-marketplace
claude plugin install quest@bb-ai-marketplace
```

`The quest` plugin declares five skills as dependencies, so installing it alone brings in
`grilling`, `wayfinder`, `domain-modeling`, `research` and `prototype`. Install one of
those directly only if you want it without the rest.

`install` and `update` each take **one** plugin, so run them one per line.

Restart Claude Code afterwards. A running session does not pick up a new plugin.

Pin to a tag or branch by appending a ref: `...bb_ai_marketplace.git#worklog--v1.0.0`.

## 4. Update

### By hand

```bash
claude plugin marketplace update bb-ai-marketplace   # refresh the catalogue
claude plugin update worklog                         # then update each plugin
```

- Refresh the catalogue first, or you update against a stale copy of it.
- **Restart Claude Code afterwards.** `update` says so itself - nothing changes in a
  running session.
- `claude plugin list` shows what version you have. No command tells you a newer one
  exists; `git ls-remote --tags <repo>` lists what has been released.
- Each version installs alongside the last, under
  `~/.claude/plugins/cache/bb-ai-marketplace/<plugin>/<version>/`.

### Automatically

Claude Code can run both those steps for you at session start and reload the result into
the session you are already in, so nothing needs restarting. **It is off until you turn it
on**, and the switch sits in your machine's registration of the marketplace rather than in
anything we publish - it is yours to set, and we cannot set it for you.

Run `/plugin`, select `bb-ai-marketplace`, choose **Enable auto-update**. The same row
reads **Disable auto-update** once it is on. The equivalent in `~/.claude/settings.json`,
beside the marketplace's `source`:

```json
"extraKnownMarketplaces": {
  "bb-ai-marketplace": {
    "source": {
      "source": "git",
      "url": "git@gitlab.beissbarth.cloud:wega2/bb_ai_marketplace.git"
    },
    "autoUpdate": true
  }
}
```

`false` turns it off again. A value here outranks the one Claude Code keeps in
`~/.claude/plugins/known_marketplaces.json`, and the `/plugin` toggle writes back into this
file when it is the one that declared the marketplace. Set in managed settings by an admin,
it locks: `/plugin` then refuses to change it and says where it came from.

It does nothing for a marketplace added from a local directory - only `git`, `github` and URL sources can be refreshed (local sources cannot).

One thing happens without either switch: when an enabled plugin has gone missing from the local catalogue, Claude Code refreshes that marketplace by itself to go and find it.

## Plugin/Skills Documentation

### The `worklog` command

The `worklog` plugin puts a `worklog` executable on `PATH` - Claude Code adds every
installed plugin's `bin/` directory. Both skills in that plugin call it by that bare name.

Two consequences:

- It resolves **inside a Claude Code session only**, and only after a restart. It is not
  on a plain terminal's `PATH`.
- Your logs are unaffected by any of this: still `~/.claude/worklogs`, or `$WORKLOG_DIR`
  if you set one.

### The cost status line

The `worklog` plugin ships `worklog-statusline`, which prints what the session costs to keep
going and when handing off would repay itself:

```
context 47% (470k) · 5h 62% · 7d 41% · $0.23/call · $32.90 · handover 48%
```

The context figure is how full the window is, coloured by how little room is left: green up
to 59%, yellow from 60%, red from 85%. Every gauge on the line uses those same two marks, and
each reads the percentage as printed, so a number and its colour always agree.

`5h` and `7d` are how much of your Claude subscription's five-hour and weekly usage limits the
account has spent - the same figures `/usage` reports - and they take the same colours as the
context figure. Each one shows only while the API reports it, so one or both can be missing;
on a plan without subscription limits neither appears.

The handover figure is how far the session has come toward the point where starting a fresh
one repays itself:

- **handover X%** - coloured on the same marks as the other gauges. The figure is left off
  until the session has a completed message to measure against.
- **handover due · X%** - red. A fresh session already repays itself, and the figure keeps
  climbing to say how far past the point the session is.

Claude Code has no status line of its own, so it has to be wired up in `~/.claude/settings.json`.
A plugin cannot do this for you: a `settings` block in `plugin.json` is ignored at load.

**Do not point it at the bare name.** Plugin `bin/` directories are on `PATH` for tool calls but
not for the status line subprocess, so `"command": "worklog-statusline"` silently prints nothing.

**Do not point it at the installed path either.** That path carries the version number, so it
breaks on every plugin update.

Instead write a shim once, at `~/.claude/bin/worklog-statusline`:

```bash
#!/usr/bin/env bash
# Run the newest installed worklog status line.
set -u

newest=$(ls -d "$HOME"/.claude/plugins/cache/bb-ai-marketplace/worklog/*/bin/worklog-statusline 2>/dev/null \
         | sort -V | tail -1)
[ -n "$newest" ] && [ -x "$newest" ] || exit 0
exec "$newest" "$@"
```

`chmod +x` it, then point settings at the shim - this never needs changing again:

```json
"statusLine": {
  "type": "command",
  "command": "/home/you/.claude/bin/worklog-statusline"
}
```

It prints nothing when the plugin is absent, which is deliberate: a status line must never be
the loudest thing on screen.

### Third party skills

`grilling`, `wayfinder`, `domain-modeling`, `research` and `prototype` are based on third party. They
were copied from [`mattpocock/skills`](https://github.com/mattpocock/skills) at commit
`3cca18b368ae95cdbdebbff572ccafa662551015` on 2026-09-07, and we now maintain our own edited version.

What was changed:

- **`grilling`** - rewritten over to ask **one question at a time** instead
  of a whole round, to answer what it can by itself before asking, to propagate every answer through the tree, and to settle where closures get recorded before the first question.
- **`wayfinder`** - the pointer to `/setup-matt-pocock-skills`, a command that does not ship here, replaced with "ask the user which tracker this repo uses".

Four of them are also the only skills here that can fire on their own; everything we wrote waits to be called by name. See [Model invocation](#model-invocation).

---

# Part 2 - Developing a plugin

## Layout

Nothing here is versioned by path. A plugin is a flat directory:

```
plugins/<name>/
  .claude-plugin/plugin.json     name, description, version, author
  skills/<skill>/SKILL.md        one directory per skill
  agents/<agent>.md              optional
  bin/<command>                  optional; Claude Code puts this on PATH
  lib/                           optional; code the skills call
.claude-plugin/marketplace.json  one entry per plugin
```

Keep a skill self-contained. Nothing inside a plugin may resolve a path above its own
root, and nothing may name `~/.claude/skills/...` - that path stops existing the moment
the skill ships as a plugin. If a skill needs a script, ship it in `bin/` and call it by
name.

Plugins are grouped by real coupling, not tidiness - the swarm agents are useless without
the swarm skill, and `session-logger` writes what `work-report` reads. Split a plugin when
someone would sensibly want one half without the other.

## Adding a plugin

1. Create `plugins/<name>/.claude-plugin/plugin.json` with `name`, `description`,
   `version`, `author`.
2. Put skills under `plugins/<name>/skills/<skill>/SKILL.md`, agents under
   `plugins/<name>/agents/`.
3. Add a matching entry to `.claude-plugin/marketplace.json` with the same `name` and
   `version`, and `"source": "./plugins/<name>"`.
4. Validate both:
   ```bash
   claude plugin validate plugins/<name> --strict
   claude plugin validate . --strict
   ```

## Model invocation

Skills we wrote set `disable-model-invocation: true`, so they fire only when asked for by
name. Keep it that way unless you deliberately want a skill the model may reach for - and
if you drop the flag, its `description` becomes load-bearing, because that text is what the
model reads to decide whether to fire it.

The vendored skills are the exception, kept as upstream wrote them: `wayfinder` sets the
flag, `grilling`, `domain-modeling`, `research` and `prototype` do not, so those four can
fire on their own. `wayfinder` calls them by name regardless.

## Testing locally before release

Add the working copy as a marketplace and install from it:

```bash
claude plugin marketplace add ./            # `.` alone is rejected; use ./ or a full path
claude plugin install <name>@bb-ai-marketplace
claude plugin details <name>@bb-ai-marketplace
```

`details` prints the component inventory and the projected token cost - always-on cost is
paid by every session, so check it before adding a skill everyone will carry.

Python code that a plugin ships gets tests:

```bash
cd plugins/worklog && python3 -m pytest lib/worklog/tests -q
```

Tests must not depend on the day they run. `worklog` derives a session's date from its
transcript's mtime, so the fixtures pin that mtime rather than asserting today's date.

There is no CI - `claude` cannot run on our GitLab or Jenkins, so validation is local. Run
`claude plugin validate . --strict` before you commit; a pre-commit hook is the place for
it.

## Releasing

Versions live in `plugin.json` and in the matching marketplace entry. The git tag is
derived from them, not the other way round, and `claude plugin tag` refuses to run if the
two disagree.

1. Run the checks that cover the change - tests, then `validate --strict` on both the
   plugin and the marketplace.
2. Bump `"version"` in **both** `plugins/<name>/.claude-plugin/plugin.json` and that
   plugin's entry in `.claude-plugin/marketplace.json`. Patch for a fix, minor for a new
   skill or command, major when someone's existing usage would break.
3. Commit. `claude plugin tag` refuses a dirty working tree.
4. Tag and push:
   ```bash
   claude plugin tag plugins/<name> --dry-run   # shows the tag it would create
   claude plugin tag plugins/<name> --push
   ```
   That creates `<name>--v<version>`, e.g. `worklog--v1.1.0`.
5. Push the branch. Consumers pick it up with the commands in Part 1.

Step 2 is what reaches consumers. Auto-update refreshes the marketplace, then compares the
`version` in each plugin's `plugin.json` against the one it already has installed - equal
versions count as up to date, whatever the files say. Push a change without bumping it and
nobody sees it.

The tag does not carry the version. It is what `#<name>--v<version>` pins to, and what
`git ls-remote --tags` lists as released. Only a plugin that declares no version in either
file falls back to the commit hash.
