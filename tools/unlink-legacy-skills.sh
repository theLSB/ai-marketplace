#!/usr/bin/env bash
# Removes the symlinks an earlier install.sh put in ~/.claude/skills and ~/.claude/agents.
# Those outrank plugin-provided skills, so anyone still holding them keeps the old
# versions and never sees an update. Shows what it would remove; --apply does it.
set -euo pipefail

legacy_repo="${LEGACY_SKILLS_REPO:-$HOME/data/projects/private/ai-skills}"
apply=0
[ "${1:-}" = "--apply" ] && apply=1

found=0
for dir in "$HOME/.claude/skills" "$HOME/.claude/agents"; do
  [ -d "$dir" ] || continue
  for target in "$dir"/*; do
    [ -L "$target" ] || continue
    case "$(readlink -f "$target")" in
      "$legacy_repo"/*) ;;
      *) continue ;;
    esac
    found=1
    if [ "$apply" -eq 1 ]; then
      rm "$target"
      echo "removed: $target"
    else
      echo "would remove: $target -> $(readlink "$target")"
    fi
  done
done

if [ "$found" -eq 0 ]; then
  echo "nothing to remove: no symlinks into $legacy_repo"
elif [ "$apply" -eq 0 ]; then
  echo
  echo "re-run with --apply to remove them."
fi
