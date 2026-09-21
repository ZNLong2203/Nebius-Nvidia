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

# Every Sandboxes request is scoped to a project. The SDK falls back to
# NEBIUS_PROJECT_ID from the environment; passing it explicitly means a missing
# value fails here, legibly, instead of as a 403 that reads like missing access.
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

## Access is Beta-gated — check this first

Sandboxes is in Beta and rights are granted per project. A key that works
perfectly for inference can have every Sandboxes permission denied:

```python
>>> sdk.get_token_info().permissions
{'import': False, 'spawn': False, 'spawn_disposable': False,
 'list': False, 'cancel': False, 'set_image_tag': False}
```

The API's own answer to this is a bare `403 You do not have permission to
perform this action`, several seconds into a run, with nothing to say the
feature is gated rather than the request malformed. `ContreeBackend` therefore
runs a **preflight** on construction: it calls `whoami`, checks for `spawn` and
`import`, and fails immediately with what is missing and how to get it
(contree@nebius.com, or the Nebius Discord).

Two things that look like problems and are not:

- **`Token expires in 0 hours`** — `whoami` reports a rolling session that
  always ends five minutes out, and the SDK warns below 24 hours. Verified
  harmless: a client reused 400 seconds after creation still ran, and its
  checkpoint still held its files. `ContreeBackend` zeroes the threshold so the
  warning does not greet every run.
- **A 403 when access *has* been granted** — that is a missing
  `NEBIUS_PROJECT_ID`, not an entitlement problem, even though the message is
  word for word the same. See below.

Until access is granted, `--backend local` exercises the identical search over
directory snapshots.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `NEBIUS_API_KEY` | — | Same key as inference |
| `CONTREE_BASE_URL` | `https://api.tokenfactory.nebius.com/sandboxes` | Sandboxes control plane |
| `NEBIUS_PROJECT_ID` | — | **Required.** Sent as the `Project` header on every request. Missing, it surfaces as a `400 Missing "Project" header` or, through the SDK, a 403 indistinguishable from missing Beta access |
| `ARBORIST_BACKEND` | `contree` | `contree` or `local` |

The OCI image comes from `--image` (default `python:3.12-slim`). `base()` calls
`images.oci()`, which resolves the reference in the project and imports it from
its registry when it is missing, so any public image works on first use; using
the image your CI already builds makes the sandbox match production. (An
earlier version called `images.use()`, which only resolves images already
imported — every other image failed at the first run.)

`--workdir` (`ARBORIST_WORKDIR`, default `/workspace`) is where the repository is
written and every command runs. Images that ship a project already installed —
SWE-bench's put it at `/testbed` — need the patch written over that copy rather
than beside it; [`evals/swebench`](../evals/swebench/README.md) runs that way.

## LocalBackend

The same four operations, implemented with directory snapshots: `base` writes a
directory, `run` copies it and executes there, `read` reads from a snapshot.

It provides **no isolation** and is not the product. It exists for two reasons:

1. the entire search, scoring, patch validation and backtracking can be exercised
   offline, which is how the test suite runs without credentials;
2. it makes the cost of *not* having ConTree concrete — a fork is a `copytree`,
   which is exactly the work branching removes.

## Measured on the Beta

Everything above this section was written before Sandboxes access was granted.
These figures were measured on the live service on 2026-09-21, `contree-sdk`
0.3.6, image `python:3.12-slim`.

| Measure | Result |
|---|---|
| `base()` — import image, upload files, first checkpoint | 1.6 s |
| `run()` of a trivial command from a checkpoint | 0.9 s |
| 1 fork running `sleep 5` | 5.8 s |
| 4 forks of one checkpoint, concurrently | 6.7 s wall (3.4× over serial) |
| 8 forks of one checkpoint, concurrently | 7.1 s wall (6.6× over serial) |
| Account limits reported by `whoami` | 50 concurrent instances, 8 concurrent imports, 3600 s max |

**Forks are genuinely parallel.** This was the claim the design rests on, and
it held: eight rival evaluations from one warm state cost barely more wall time
than one.

**The first end-to-end run** — `examples/broken-invoice`, fan-out 3, node cap
8 — solved in 182 s: six patches, eight sandbox executions, green at depth 3.
Of those 182 seconds, **18 were spent in the sandbox**. The setup step
(`pip install pytest`) took 5.2 s and ran once; the six evaluations that forked
from it instead of repeating it saved 31 s.

Two consequences worth stating plainly:

- **On this workload the model is the bottleneck, not the sandbox.** Execution
  is about a tenth of wall time. Making Sandboxes faster would barely move a
  run; running more candidates per model call would.
- **Setup savings scale with the install, and these installs are small.** A
  five-second `pip install` makes the saving real but modest. The case for
  forking on these repos is parallel evaluation and free backtracking; the
  setup argument grows with the project, as the model below describes.

## Cost model

Let **s** be the setup time, **t** a test run, **k** the fan-out and **d** the depth.

| | executions | setup cost |
|---|---|---|
| Container-per-attempt | `k·d` | `k·d·s` |
| Arborist | `k·d + 1` | `1·s` |

At the default `k=4`, `d=3`, on a repo with a 45-second install: 9 minutes of
repeated setup versus 45 seconds. That line is arithmetic; the measured figure
for the five-second installs in this repository is in the section above. `stats.setup_seconds_saved` reports the measured
figure for each run, and `evals/run_eval.py` measures both modes side by side.

## Failure handling

Every exception from the SDK is caught and returned as an `ExecResult` with
`error` set. The node becomes `invalid`, the search continues, and the report
records what happened. Sandboxes is in beta; an execution failure should cost one
branch, not a run.
