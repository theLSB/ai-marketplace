import pytest

from worklog import shell


@pytest.mark.parametrize(
    "command, expected",
    [
        ("cat > /repo/a.py <<'PY'", ["/repo/a.py"]),
        ("echo hi >> notes.md", ["notes.md"]),
        ("make 2> build.log", ["build.log"]),
        ("sed -i 's/a/b/' src/main.c", ["src/main.c"]),
        ("sed -i -e 's/a/b/' one.py two.py", ["one.py", "two.py"]),
        ("cp src/a.h build/a.h", ["build/a.h"]),
        ("mv old.md docs/new.md", ["docs/new.md"]),
        ("touch a.txt b.txt", ["a.txt", "b.txt"]),
        ("tee -a /var/log/out.log", ["/var/log/out.log"]),
        ("rm /repo/stale.o", ["/repo/stale.o"]),
        ("cat a.py > b.py; sed -i 's/x/y/' c.py", ["b.py", "c.py"]),
        ("printf x > a.md && printf y > a.md", ["a.md"]),
    ],
)
def test_writes_are_found(command, expected):
    assert shell.changed_paths(command) == expected


@pytest.mark.parametrize(
    "command",
    [
        "ls -la /repo",
        "grep -rn thing src/",
        "python3 -m pytest -q",
        "cat notes.md",
        "make 2>/dev/null",
        "echo hi > /dev/null",
        "find . -name '*.tmp' > /dev/null",
        "cat > $OUT",
        "sed 's/a/b/' src/main.c",
        "cp -r src build",
    ],
)
def test_reads_and_unclear_targets_are_ignored(command):
    assert shell.changed_paths(command) == []


def test_a_heredoc_body_is_not_mistaken_for_commands():
    command = "cat > /repo/x.py <<'PY'\nopen('trap.txt','w')\nPY"
    assert shell.changed_paths(command) == ["/repo/x.py"]


@pytest.mark.parametrize(
    "command, expected",
    [
        ("env | grep -iE 'claude|session' | sed 's/=.*/=<set>/' | sort", []),
        ("echo '2 > 1' ", []),
        ("cat > 'my file.md' <<'MD'", ["my file.md"]),
        ("echo x >out.txt", ["out.txt"]),
        ('printf y > "spaced name.log"', ["spaced name.log"]),
    ],
)
def test_quoted_angle_brackets_are_not_redirects(command, expected):
    assert shell.changed_paths(command) == expected


def test_a_heredoc_body_is_data_not_shell():
    command = "cat > /repo/x.sh <<'SH'\necho hi > /repo/trap.txt\nsed -i 's/a/b/' /repo/other.c\nSH"
    assert shell.changed_paths(command) == ["/repo/x.sh"]


def test_commands_after_a_heredoc_are_still_read():
    command = "cat > a.md <<'MD'\nbody > ignored.txt\nMD\nsed -i 's/x/y/' b.md"
    assert shell.changed_paths(command) == ["a.md", "b.md"]


def test_two_heredocs_in_one_command_are_both_skipped():
    command = "cat > a.py <<'PY'\nx > 1\nPY\ncat > b.py <<'PY2'\ny > 2\nPY2"
    assert shell.changed_paths(command) == ["a.py", "b.py"]


@pytest.mark.parametrize(
    "command, expected",
    [
        ("R=/repo\ncat > $R/a.py <<'PY'\nx=1\nPY", ["/repo/a.py"]),
        ("R=/repo; sed -i 's/x/y/' $R/b.py", ["/repo/b.py"]),
        ("D=/repo/src\ncp x.h ${D}/x.h", ["/repo/src/x.h"]),
        ("cat > $OUT/a.py <<'PY'\nx=1\nPY", []),
    ],
)
def test_paths_written_through_the_command_own_variables(command, expected):
    assert shell.changed_paths(command) == expected


def test_assignments_are_collected_once_each():
    assert shell.assignments("R=/a\nR=/b\necho $R") == {"R": "/a"}


def test_expand_leaves_unknown_variables_alone():
    assert shell.expand("$R/x", {"R": "/repo"}) == "/repo/x"
    assert shell.expand("$OTHER/x", {"R": "/repo"}) == "$OTHER/x"
