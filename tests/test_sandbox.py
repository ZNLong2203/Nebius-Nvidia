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


# --------------------------------------------------------------------------- #
# the Nebius backend's preflight
# --------------------------------------------------------------------------- #


class _FakeInfo:
    def __init__(self, permissions):
        self.permissions = permissions


class _FakeSdk:
    def __init__(self, permissions=None, raises=None):
        self._permissions = permissions or {}
        self._raises = raises
        self.config = type("C", (), {"auth": type("A", (), {"base_url": "https://sandboxes.test"})()})()

    def get_token_info(self, refresh: bool = False):
        if self._raises:
            raise self._raises
        return _FakeInfo(self._permissions)


def _backend_with(sdk, workdir="/workspace"):
    """A ContreeBackend whose SDK is stubbed, so preflight can be exercised."""
    from arborist.sandbox import ContreeBackend

    backend = ContreeBackend.__new__(ContreeBackend)
    backend._sdk = sdk
    backend._timeout = 1.0
    backend._workdir = workdir
    backend._forks = 0
    return backend


def test_preflight_passes_when_the_key_can_spawn_and_import():
    backend = _backend_with(_FakeSdk({"spawn": True, "import": True, "list": False}))
    backend._preflight()  # no raise


def test_preflight_names_the_missing_permissions_and_the_way_out():
    """Sandboxes is Beta-gated; the API's own 403 says nothing about that."""
    import pytest

    backend = _backend_with(_FakeSdk({"spawn": False, "import": False}))
    with pytest.raises(RuntimeError) as excinfo:
        backend._preflight()

    message = str(excinfo.value)
    assert "spawn, import denied" in message
    assert "Beta" in message
    assert "--backend local" in message, "an unusable key must still leave a way to work"


def test_preflight_reports_an_unreachable_service(monkeypatch):
    import pytest

    backend = _backend_with(_FakeSdk(raises=ConnectionError("no route")))
    with pytest.raises(RuntimeError, match="could not reach Nebius Sandboxes"):
        backend._preflight()


def test_local_backend_resolves_python_to_this_interpreter():
    """`python -m pytest` in a test command must mean the environment Arborist runs in.

    Compared by prefix, not by path: in a uv virtualenv `python` on PATH is
    `bin/python` while `sys.executable` is `bin/python3`, and they are the same
    interpreter. The invariant is the environment, not the symlink name.
    """
    import sys

    backend = LocalBackend()
    try:
        cp = backend.base({}, "ignored")
        result = backend.run(cp, "python -c 'import sys; print(sys.prefix)'")
        assert result.ok, result.stderr
        assert result.stdout.strip() == sys.prefix
    finally:
        backend.close()


class _FakeState:
    """Stands in for a ConTree image or checkpoint: runnable, and records how."""

    def __init__(self, log, uuid="c0"):
        self._log = log
        self.uuid = uuid
        self.exit_code = 0
        self.stdout = ""
        self.stderr = ""

    def run(self, **kwargs):
        self._log.append(kwargs)
        return _FakeState(self._log, uuid=f"c{len(self._log)}")

    def wait(self):
        return self

    def read(self, path):
        self._log.append({"read": path})
        return b""


class _FakeImages:
    def __init__(self, log):
        self._log = log
        self.refs = []

    def oci(self, ref, timeout=None):
        self.refs.append(ref)
        return _FakeState(self._log)

    def use(self, ref):  # pragma: no cover - fails the test if reached
        raise AssertionError("use() only finds images already imported")


def test_an_image_is_imported_when_the_project_does_not_have_it():
    log = []
    sdk = _FakeSdk({"spawn": True, "import": True})
    sdk.images = _FakeImages(log)
    backend = _backend_with(sdk)

    backend.base({"a.py": b"x"}, "docker.io/org/image:tag")
    assert sdk.images.refs == ["docker.io/org/image:tag"]


def test_the_workdir_is_where_files_land_commands_run_and_reports_are_read():
    """SWE-bench images keep the installed project at /testbed, not /workspace."""
    log = []
    sdk = _FakeSdk({"spawn": True, "import": True})
    sdk.images = _FakeImages(log)
    backend = _backend_with(sdk, workdir="/testbed")

    base = backend.base({"pkg/a.py": b"x"}, "img")
    assert list(log[0]["files"]) == ["/testbed/pkg/a.py"]

    backend.run(base, "pytest -q", files={"pkg/a.py": b"y"})
    assert log[1]["cwd"] == "/testbed"
    assert list(log[1]["files"]) == ["/testbed/pkg/a.py"]

    backend.read(base, ".arborist/report.xml")
    assert log[2] == {"read": "/testbed/.arborist/report.xml"}

