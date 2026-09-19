from arborist.sandbox import LocalBackend


def test_base_materialises_the_repo():
    backend = LocalBackend()
    try:
        cp = backend.base({"a.txt": b"hello", "pkg/b.txt": b"nested"}, "ignored")
        assert backend.read(cp, "a.txt") == b"hello"
        assert backend.read(cp, "pkg/b.txt") == b"nested"
    finally:
        backend.close()


def test_run_returns_output_and_a_new_checkpoint():
    backend = LocalBackend()
    try:
        cp = backend.base({"a.txt": b"hello"}, "ignored")
        result = backend.run(cp, "cat a.txt")
        assert result.ok
        assert result.stdout.strip() == "hello"
        assert result.checkpoint.id != cp.id
    finally:
        backend.close()


def test_a_child_never_mutates_its_parent():
    """The whole contract: states are immutable, so a branch cannot poison its base."""
    backend = LocalBackend()
    try:
        base = backend.base({"a.txt": b"original"}, "ignored")
        child = backend.run(base, "echo changed > a.txt").checkpoint
        assert backend.read(child, "a.txt").strip() == b"changed"
        assert backend.read(base, "a.txt") == b"original"
    finally:
        backend.close()


def test_siblings_are_isolated_from_each_other():
    backend = LocalBackend()
    try:
        base = backend.base({"a.txt": b"0"}, "ignored")
        left = backend.run(base, "echo left > a.txt").checkpoint
        right = backend.run(base, "echo right > a.txt").checkpoint
        assert backend.read(left, "a.txt").strip() == b"left"
        assert backend.read(right, "a.txt").strip() == b"right"
    finally:
        backend.close()


def test_forking_is_cheap_relative_to_rebuilding():
    """Files uploaded with a run land in the child only."""
    backend = LocalBackend()
    try:
        base = backend.base({"a.txt": b"0"}, "ignored")
        child = backend.run(base, "cat a.txt", files={"a.txt": b"patched"}).checkpoint
        assert backend.read(child, "a.txt") == b"patched"
        assert backend.read(base, "a.txt") == b"0"
        assert backend.fork_count == 1
    finally:
        backend.close()


def test_a_failing_command_is_reported_not_raised():
    backend = LocalBackend()
    try:
        cp = backend.base({}, "ignored")
        result = backend.run(cp, "exit 3")
        assert result.exit_code == 3
        assert not result.ok
    finally:
        backend.close()


def test_reading_a_missing_file_returns_none():
    backend = LocalBackend()
    try:
        cp = backend.base({}, "ignored")
        assert backend.read(cp, "nope.txt") is None
    finally:
        backend.close()
