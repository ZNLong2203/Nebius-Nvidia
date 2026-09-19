# Nebius Sandboxes integration

Implemented in [`arborist/sandbox.py`](../arborist/sandbox.py).

## Why this service specifically

Nebius Sandboxes (ConTree) gives every executed command a **new immutable
filesystem version**, and lets you fork from any of them — Git branching, but for
container execution state.

That is the primitive the entire project rests on. Without it, "evaluate four
rival patches from an identical warm state" means four containers and four
dependency installs. With it, it means four forks of one checkpoint.

| Property | What it buys the search |
|---|---|
| Immutable versions | Backtracking is not an operation. A regressed branch is abandoned by never being forked from again |
| Fork from any checkpoint | The expensive prefix is paid once and shared by every branch, at any depth |
| Instant rollback | The parent state is always intact; no rebuild, no re-run |
| VM-level isolation | Model-written code executes without trusting it |
| OCI images | The sandbox base is whatever the project already builds on |

## The contract

Arborist needs exactly four operations. Anything satisfying them is a backend.

```python
class Backend(Protocol):
    name: str
    def base(self, files: dict[str, bytes], image: str) -> Checkpoint: ...
    def run(self, checkpoint: Checkpoint, command: str,
            files: dict[str, bytes] | None = None,
            timeout: float | None = None) -> ExecResult: ...
    def read(self, checkpoint: Checkpoint, path: str) -> bytes | None: ...
    def close(self) -> None: ...
```

With one invariant that is not expressible in the type: **`run` never mutates the
checkpoint it was given.** It returns a new one.

`ExecResult` carries `checkpoint`, `exit_code`, `stdout`, `stderr`, `seconds` and
`error`. A non-zero exit is not an error — it is the signal the search is looking
for. `error` is reserved for the execution itself failing.

## ContreeBackend

```python
from contree_sdk import ContreeSync
from contree_sdk.auth import IAMAuth
from contree_sdk.config import ContreeConfig

# The `ContreeSync(token=..., base_url=...)` shorthand leaves project_id at its
# default, and every Sandboxes request carries a `Project` header -- without it
# the API answers 400 before doing anything.
sdk = ContreeSync(
    ContreeConfig(auth=IAMAuth(token=NEBIUS_API_KEY, project_id=NEBIUS_PROJECT_ID,
                               base_url=CONTREE_BASE_URL))
)
image = sdk.images.use("python:3.12-slim")

staged = image.run(shell="mkdir -p /workspace && ls -la /workspace",
                   files={"/workspace/src/app.py": b"...", ...},
                   disposable=False).wait()          # ← the first checkpoint

child = staged.run(shell="python -m pytest -q --junitxml=.arborist/report.xml",
                   cwd="/workspace",
                   files={"/workspace/src/app.py": patched_bytes},
                   disposable=False).wait()          # ← a fork; `staged` is untouched

report = child.read("/workspace/.arborist/report.xml")
```

Three details that matter:

- **`disposable=False`** is what makes the resulting version persist and therefore
  be forkable. Disposable runs are one-shot.
- **`files=` uploads with the run**, so a patch is applied and tested in a single
  round trip, and only changed files are sent.
- **The returned object is itself runnable.** Forking is calling `.run()` on an
  older result. There is no separate branch API.

The workspace is `/workspace`; relative paths in `read()` are resolved against it.

### SDK version — read this before following the docs

The published Python guides show `Contree(api_client)` taking a pre-built
`contree_client.httpx` client. **That API only exists on the `0.4.0.dev*`
pre-releases.**

The current stable release, `contree-sdk` **0.3.6**, exposes
`ContreeSync(token=…, base_url=…)` and has no client-injection parameter. The
Mini-SWE-Agent integration page documents its own breakage against the same
change. Arborist pins 0.3.6 and codes against the released signatures, which were
confirmed by introspecting the installed package.

```toml
[project.optional-dependencies]
contree = ["contree-sdk==0.3.6"]
```

If you upgrade, `ContreeBackend.__init__` is the only place that needs to change.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `NEBIUS_API_KEY` | — | Same key as inference |
| `CONTREE_BASE_URL` | `https://api.tokenfactory.nebius.com/sandboxes` | Sandboxes control plane |
| `NEBIUS_PROJECT_ID` | — | **Required.** Sent as the `Project` header on every request; a missing value is a 400 |
| `ARBORIST_BACKEND` | `contree` | `contree` or `local` |

The OCI image comes from `--image` (default `python:3.12-slim`). Any registry
ConTree can import from works; using the image your CI already builds makes the
sandbox match production.

## LocalBackend

The same four operations, implemented with directory snapshots: `base` writes a
directory, `run` copies it and executes there, `read` reads from a snapshot.

It provides **no isolation** and is not the product. It exists for two reasons:

1. the entire search, scoring, patch validation and backtracking can be exercised
   offline, which is how the test suite runs without credentials;
2. it makes the cost of *not* having ConTree concrete — a fork is a `copytree`,
   which is exactly the work branching removes.

## Cost model

Let **s** be the setup time, **t** a test run, **k** the fan-out and **d** the depth.

| | executions | setup cost |
|---|---|---|
| Container-per-attempt | `k·d` | `k·d·s` |
| Arborist | `k·d + 1` | `1·s` |

At the default `k=4`, `d=3`, on a repo with a 45-second install: 9 minutes of
repeated setup versus 45 seconds. `stats.setup_seconds_saved` reports the measured
figure for each run, and `evals/run_eval.py` measures both modes side by side.

## Failure handling

Every exception from the SDK is caught and returned as an `ExecResult` with
`error` set. The node becomes `invalid`, the search continues, and the report
records what happened. Sandboxes is in beta; an execution failure should cost one
branch, not a run.
