# Team second brain - concept decisions

Session: grilling, 2026-09-17. Status: in progress.

## Aim

A shared knowledge base for the team. Humans dump what they know; Claude dumps what it
learns about projects. Everyone reads it, and so does Claude. Must be low maintenance:
easy to write, easy to find things in, easy to stay up to date.

Origin: `~/.ai/lessons/` - a personal, hand-maintained store of 16 problem/solution notes
indexed by a trigger table in the user's private CLAUDE.md. Proven useful, but single
user, not shared, and the index design stops scaling at around 20 entries.

## Settled

| # | Decision | Why |
|---|---|---|
| 1 | General purpose, not lessons only | Holds human knowledge and agent-written project info. Stated aim. |
| 2 | Humans and agents both read and write | Rules out human-only wikis (Confluence, Notion - not greppable) and agent-only stores (vector DB with no human UI). |
| 3 | Plain markdown files in a git repo on internal GitLab | The only form Obsidian, VS Code, grep, Claude and GitLab all read natively without a server. |
| 4 | Obsidian is a viewer, not the architecture | A vault is just a folder of markdown. Per-person choice, reversible, constrains nothing. |
| 5 | No self-hosted service | Follows from low maintenance. Rules out Outline, Trilium, hosted vector search. |
| 6 | Work continuity is out of scope | `worklog` and `handoff` plugins already cover it. |

## Open

- How knowledge gets out at the right moment (push vs pull retrieval)
- How knowledge gets in, and by whom
- How each machine stays current
- Repo location, and whether it ships with a plugin
- Note structure and taxonomy

## Verified facts

- Obsidian is free for commercial use since 2025-02-20; the former $50/user/year commercial
  licence no longer exists. No per-seat cost, no licensing blocker. (obsidian.md/terms)
- The Obsidian Git community plugin auto pulls and commits on a schedule, and pulls on
  startup. Desktop only in practice: mobile is unstable and has no SSH auth.
- That plugin has no merge conflict resolution. Conflicts drop to the terminal, so note
  granularity matters: one topic per note keeps two people off the same file.
- Obsidian Sync costs $4-5/user/month and buys real-time sync, which git already covers.
