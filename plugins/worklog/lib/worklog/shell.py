"""Reading file targets out of shell commands, so Bash edits show up in a work log."""

from __future__ import annotations

import re
import shlex

SEPARATORS = re.compile(r"[\n;|]|&&|\|\|")
REDIRECT_OP = re.compile(r"^(?:\d|&)?>>?$")
REDIRECT_ATTACHED = re.compile(r"^(?:\d|&)?>>?(\S+)$")
NOT_A_FILE = re.compile(r"^(?:/dev/|/proc/|-$)|[*?$`'\"]")
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?")
DESTINATION_COMMANDS = frozenset({"cp", "mv", "install", "rsync"})
TARGET_COMMANDS = frozenset({"touch", "tee", "rm", "unlink"})
SCRIPT_FLAGS = frozenset({"-e", "-f", "--expression", "--file"})
ASSIGNMENT = re.compile(r"(?:^|\s)([A-Za-z_]\w*)=([^\s;|&]+)")
VARIABLE = re.compile(r"\$\{?([A-Za-z_]\w*)\}?")


def strip_heredocs(command: str) -> str:
    """The command without heredoc bodies - their text is data, not shell to read."""
    kept: list[str] = []
    awaiting: list[str] = []
    for line in command.splitlines():
        if awaiting:
            if line.strip() == awaiting[0]:
                awaiting.pop(0)
            continue
        kept.append(line)
        awaiting.extend(match.group(1) for match in HEREDOC.finditer(line))
    return "\n".join(kept)


def assignments(command: str) -> dict[str, str]:
    """Variables the command sets itself, so paths written through them can be read."""
    found = {}
    for name, value in ASSIGNMENT.findall(strip_heredocs(command)):
        found.setdefault(name, _unquote(value))
    return found


def expand(token: str, variables: dict[str, str]) -> str:
    """The token with known variables substituted; unknown ones are left in place."""
    return VARIABLE.sub(lambda m: variables.get(m.group(1), m.group(0)), token)


def _is_path(token: str) -> bool:
    if not token or NOT_A_FILE.search(token):
        return False
    return "/" in token or "." in token


def _unquote(token: str) -> str:
    return token[1:-1] if len(token) > 1 and token[0] == token[-1] and token[0] in "'\"" else token


def _is_quoted(token: str) -> bool:
    return token[:1] in {"'", '"'}


def _split(fragment: str) -> list[str]:
    """Tokens with their quotes intact, so a quoted '>' is not read as a redirect."""
    try:
        return shlex.split(fragment, posix=False)
    except ValueError:
        return fragment.split()


def _sed_targets(words: list[str]) -> list[str]:
    """Candidate files sed rewrites in place. Without -e, its first argument is the script."""
    if not any(w.startswith("-i") for w in words[1:]):
        return []
    script_given = False
    candidates: list[str] = []
    skip_next = False
    for word in words[1:]:
        if skip_next:
            skip_next = False
            continue
        if word in SCRIPT_FLAGS:
            skip_next = True
            script_given = True
            continue
        if word.startswith("-"):
            continue
        candidates.append(word)
    return candidates if script_given else candidates[1:]


def changed_paths(command: str) -> list[str]:
    """Paths a command writes to, as far as shell syntax makes plain. Order kept, no repeats."""
    found: list[str] = []
    variables = assignments(command)

    def keep(path: str) -> None:
        path = expand(_unquote(path), variables)
        if _is_path(path) and path not in found:
            found.append(path)

    for fragment in SEPARATORS.split(strip_heredocs(command)):
        tokens = _split(fragment.strip())
        words: list[str] = []
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if not _is_quoted(token) and REDIRECT_OP.match(token) and index + 1 < len(tokens):
                keep(tokens[index + 1])
                index += 2
                continue
            attached = None if _is_quoted(token) else REDIRECT_ATTACHED.match(token)
            if attached:
                keep(attached.group(1))
                index += 1
                continue
            words.append(token)
            index += 1
        if not words:
            continue
        name = _unquote(words[0]).rsplit("/", 1)[-1]
        arguments = [_unquote(w) for w in words[1:] if not w.startswith("-")]
        if name == "sed":
            for path in _sed_targets([_unquote(w) for w in words]):
                keep(path)
        elif name in DESTINATION_COMMANDS and len(arguments) > 1:
            keep(arguments[-1])
        elif name in TARGET_COMMANDS:
            for path in arguments:
                keep(path)
    return found
