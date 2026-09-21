"""Execution backends.

Arborist only needs four things from an execution environment:

1. build a *base* state from a repository,
2. run a command **from any previous state** and get a new state back,
3. read a file out of a state,
4. never mutate a state that already exists.

Point 2 is the whole reason this project exists. Nebius Sandboxes (ConTree)
gives it natively: every ``run`` produces a new immutable filesystem version and
you may fork from any of them, so the expensive prefix -- cloning, installing
dependencies, warming caches -- is paid once and shared by every branch the
search explores.

:class:`LocalBackend` implements the same contract with directory snapshots so
the search algorithm, the scoring and the whole test suite can run with no
credentials. It is a development aid, not the product.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol

WORKDIR = "/workspace"


@dataclass
class Checkpoint:
    """An immutable filesystem state you can fork from."""

    id: str
    handle: Any = None
    label: str = ""


@dataclass
class ExecResult:
    checkpoint: Checkpoint
    exit_code: int
    stdout: str
    stderr: str
    seconds: float
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.error


class Backend(Protocol):
    name: str

    def base(self, files: dict[str, bytes], image: str) -> Checkpoint: ...

    def run(
        self,
        checkpoint: Checkpoint,
        command: str,
        files: dict[str, bytes] | None = None,
        timeout: float | None = None,
    ) -> ExecResult: ...

    def read(self, checkpoint: Checkpoint, path: str) -> bytes | None: ...

    def close(self) -> None: ...


# --------------------------------------------------------------------------- #
# Nebius Sandboxes / ConTree
# --------------------------------------------------------------------------- #


class ContreeBackend:
    """Nebius Token Factory Sandboxes.

    Every :meth:`run` returns a new image version; forking is simply calling
    ``run`` again on an older version. Rolling a failed branch back costs one
    dictionary lookup instead of a rebuild.
    """

    name = "contree"

    def __init__(self, token: str, base_url: str, project_id: str = "", timeout: float = 900.0) -> None:
        try:
            from contree_sdk import ContreeSync
            from contree_sdk.auth import IAMAuth
            from contree_sdk.config import ContreeConfig
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(
                "contree-sdk is not installed. Install it with: pip install 'arborist[contree]'"
            ) from exc

        if not token:
            raise RuntimeError("NEBIUS_API_KEY is required for the contree backend.")
        if not project_id:
            # Every Sandboxes request carries a `Project` header; without it the
            # API answers 400 before doing anything, which is a confusing way to
            # learn that one environment variable is missing.
            raise RuntimeError(
                "NEBIUS_PROJECT_ID is required for the contree backend -- Sandboxes scopes "
                "every request to a project. Find it in the Nebius Token Factory console "
                "(it looks like `project-e00abc...`) and add it to .env."
            )

        # The shorthand `ContreeSync(token=..., base_url=...)` leaves project_id
        # at its default, so the auth object has to be built in full.
        #
        # The warning threshold is zeroed because the SDK's default (24h) is
        # meant for long-lived tokens, while `whoami` reports a rolling session
        # that always ends five minutes from now. Left alone, every run opens
        # with "Token expires in 0 hours" -- which is never true: a client held
        # well past that mark keeps working.
        self._sdk = ContreeSync(
            ContreeConfig(
                auth=IAMAuth(token=token, project_id=project_id, base_url=base_url),
                token_expiration_warning_threshold=timedelta(0),
            )
        )
        self._timeout = timeout
        self._forks = 0
        self._preflight()

    # Required to build a checkpoint and to fork from it. The API answers a bare
    # 403 when they are missing, several seconds into a run, with nothing to say
    # that the feature is gated rather than the request malformed.
    REQUIRED_PERMISSIONS = ("spawn", "import")

    def _preflight(self) -> None:
        """Fail immediately, and legibly, when the key cannot use Sandboxes."""
        try:
            info = self._sdk.get_token_info()
        except Exception as exc:
            raise RuntimeError(
                f"could not reach Nebius Sandboxes at {self._sdk.config.auth.base_url}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        permissions = dict(getattr(info, "permissions", {}) or {})
        missing = [p for p in self.REQUIRED_PERMISSIONS if not permissions.get(p)]
        if missing:
            raise RuntimeError(
                "this Nebius key has no Sandboxes permissions "
                f"({', '.join(missing)} denied). Sandboxes is in Beta and access is granted "
                "per project -- request it at contree@nebius.com or in the Nebius Discord. "
                "Until then, run with `--backend local`, which uses directory snapshots and "
                "exercises the same search."
            )

    @property
    def fork_count(self) -> int:
        return self._forks

    def base(self, files: dict[str, bytes], image: str) -> Checkpoint:
        img = self._sdk.images.use(image)
        # One run materialises the repo inside the image and gives us the first
        # reusable checkpoint. Everything after this forks from here.
        staged = img.run(
            shell=f"mkdir -p {WORKDIR} && ls -la {WORKDIR}",
            files={f"{WORKDIR}/{p}": data for p, data in files.items()},
            cwd="/",
            disposable=False,
            timeout=self._timeout,
        ).wait()
        return Checkpoint(id=str(staged.uuid), handle=staged, label="base")

    def run(
        self,
        checkpoint: Checkpoint,
        command: str,
        files: dict[str, bytes] | None = None,
        timeout: float | None = None,
    ) -> ExecResult:
        started = time.time()
        payload = {f"{WORKDIR}/{p}": data for p, data in (files or {}).items()}
        try:
            result = checkpoint.handle.run(
                shell=command,
                cwd=WORKDIR,
                files=payload or None,
                disposable=False,
                timeout=timeout or self._timeout,
            ).wait()
        except Exception as exc:  # noqa: BLE001 - surfaced to the node, never fatal
            return ExecResult(
                checkpoint=checkpoint,
                exit_code=-1,
                stdout="",
                stderr="",
                seconds=time.time() - started,
                error=f"{type(exc).__name__}: {exc}",
            )

        self._forks += 1
        return ExecResult(
            checkpoint=Checkpoint(id=str(result.uuid), handle=result),
            exit_code=int(result.exit_code or 0),
            stdout=_as_text(result.stdout),
            stderr=_as_text(result.stderr),
            seconds=time.time() - started,
        )

    def read(self, checkpoint: Checkpoint, path: str) -> bytes | None:
        target = path if path.startswith("/") else f"{WORKDIR}/{path}"
        try:
            return checkpoint.handle.read(target)
        except Exception:  # noqa: BLE001 - a missing file is a normal outcome
            return None

    def close(self) -> None:  # pragma: no cover - nothing to release
        return None


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


# --------------------------------------------------------------------------- #
# Local fallback
# --------------------------------------------------------------------------- #


@dataclass
class _LocalState:
    path: Path


class LocalBackend:
    """Directory-snapshot stand-in for Sandboxes.

    Same contract, no isolation and no credentials. Forking copies a directory,
    which is exactly the cost ConTree removes -- running the benchmark against
    both backends is how ``evals/`` measures what branching is worth.
    """

    name = "local"

    def __init__(self, root: str | Path | None = None, timeout: float = 900.0) -> None:
        self._root = Path(root or tempfile.mkdtemp(prefix="arborist-"))
        self._root.mkdir(parents=True, exist_ok=True)
        self._states: dict[str, _LocalState] = {}
        self._timeout = timeout
        self._forks = 0

    @property
    def fork_count(self) -> int:
        return self._forks

    def _new_state(self, from_path: Path | None) -> Checkpoint:
        sid = uuid.uuid4().hex[:12]
        path = self._root / sid
        if from_path is None:
            path.mkdir(parents=True)
        else:
            shutil.copytree(from_path, path, symlinks=True)
        self._states[sid] = _LocalState(path=path)
        return Checkpoint(id=sid, handle=path)

    def base(self, files: dict[str, bytes], image: str) -> Checkpoint:
        cp = self._new_state(None)
        _write_files(Path(cp.handle), files)
        cp.label = "base"
        return cp

    def run(
        self,
        checkpoint: Checkpoint,
        command: str,
        files: dict[str, bytes] | None = None,
        timeout: float | None = None,
    ) -> ExecResult:
        started = time.time()
        child = self._new_state(Path(checkpoint.handle))
        self._forks += 1
        if files:
            _write_files(Path(child.handle), files)

        env = dict(os.environ)
        env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        # Put the interpreter running Arborist first on PATH, so `python` and
        # `pytest` in a test command mean this environment. Under the contree
        # backend they mean the image's own python; locally, without this, they
        # would mean whatever the machine happens to have -- which on a Mac is a
        # system python with no pytest.
        interpreter_bin = str(Path(sys.executable).parent)
        env["PATH"] = interpreter_bin + os.pathsep + env.get("PATH", "")
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=child.handle,
                capture_output=True,
                text=True,
                timeout=timeout or self._timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return ExecResult(
                checkpoint=child,
                exit_code=-1,
                stdout="",
                stderr="",
                seconds=time.time() - started,
                error="timeout",
            )
        return ExecResult(
            checkpoint=child,
            exit_code=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            seconds=time.time() - started,
        )

    def read(self, checkpoint: Checkpoint, path: str) -> bytes | None:
        root = Path(checkpoint.handle)
        target = Path(path)
        if target.is_absolute():
            # Absolute paths in the contract refer to the sandbox filesystem;
            # map the workspace prefix onto this snapshot and pass the rest through.
            try:
                target = root / target.relative_to(WORKDIR)
            except ValueError:
                target = Path(str(target).lstrip("/"))
                target = root / target
        else:
            target = root / target
        if not target.is_file():
            return None
        return target.read_bytes()

    def close(self) -> None:
        shutil.rmtree(self._root, ignore_errors=True)


def _write_files(root: Path, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        dest = root / rel.lstrip("/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)


def build_backend(settings) -> Backend:
    """Pick a backend from settings, falling back to local when unusable."""
    if settings.backend == "local":
        return LocalBackend(timeout=settings.exec_timeout)
    return ContreeBackend(
        token=settings.nebius_api_key,
        base_url=settings.contree_base_url,
        project_id=settings.nebius_project_id,
        timeout=settings.exec_timeout,
    )
