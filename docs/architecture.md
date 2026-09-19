# Architecture

## Shape

Arborist is a search engine with two replaceable dependencies: something that
executes commands and returns immutable states, and something that writes text.
Everything else is pure logic and is tested without either.

```
                        ┌──────────────────────────────────────────┐
   arborist fix ───────►│                                          │
   (cli.py)             │              search.py                   │
                        │  select → expand → score → prune → repeat │
   POST /api/runs ─────►│                                          │
   (server.py)          └───────┬───────────────────────┬──────────┘
                                │                       │
                    ┌───────────▼─────────┐   ┌─────────▼──────────┐
                    │      agent.py       │   │     sandbox.py     │
                    │ diagnose / propose  │   │  Backend contract  │
                    │     / adjudicate    │   │                    │
                    └───────────┬─────────┘   ├────────────────────┤
                                │             │ ContreeBackend     │──► Nebius Sandboxes
                    ┌───────────▼─────────┐   │ LocalBackend       │──► directory snapshots
                    │       llm.py        │   └────────────────────┘
                    │  tiering, budget,   │
                    │   JSON recovery     │──────────────────────────► Token Factory
                    └───────────┬─────────┘                            (Nemotron 3)
                                │
                    ┌───────────▼─────────┐
                    │  tools/tavily.py    │──────────────────────────► Tavily
                    └─────────────────────┘

   repo.py    — repository IO, patch application, JUnit parsing, diffing
   report.py  — a run rendered as the pull request body a human reviews
   publish.py — branch, commit, push, open — each one opt-in
   models.py  — the data that crosses every boundary
   config.py  — one place that reads the environment
```

## Module responsibilities

| Module | Owns | Never does |
|---|---|---|
| [`config.py`](../arborist/config.py) | Reading the environment once into a frozen `Settings`; the tier → model-id map | Anything conditional on credentials |
| [`models.py`](../arborist/models.py) | `Edit`, `Hypothesis`, `TestReport`, `Node` — the only types that cross module boundaries | Behaviour beyond serialisation |
| [`llm.py`](../arborist/llm.py) | Token Factory calls, per-tier token accounting, budget enforcement, JSON recovery | Knowing what a prompt means |
| [`agent.py`](../arborist/agent.py) | The three prompts, and turning model output into dataclasses | Calling the sandbox, or deciding what to explore |
| [`sandbox.py`](../arborist/sandbox.py) | The four-operation backend contract and its two implementations | Knowing what a patch or a test is |
| [`repo.py`](../arborist/repo.py) | Reading a tree, applying edits, parsing JUnit, producing diffs | Any network call |
| [`search.py`](../arborist/search.py) | Selection, scoring, expansion, pruning, termination, the run report | Talking to a provider directly |
| [`report.py`](../arborist/report.py) | Turning a finished run into markdown: the fix, the evidence, the rejected alternatives | Touching git or the network |
| [`publish.py`](../arborist/publish.py) | Git and `gh` plumbing, and the guard rails in front of each outward-facing step | Acting without being asked — every entry point plans first |
| [`server.py`](../arborist/server.py) | HTTP surface, one thread per run, SSE fan-out with replay | Search logic |
| [`cli.py`](../arborist/cli.py) | Terminal rendering of the same event stream | Search logic |

Two rules keep this honest:

- **`search.py` depends on interfaces, not services.** It receives a `Backend`
  and an `LLM`. That is why the whole algorithm is testable offline.
- **`agent.py` returns dataclasses, never raw model output.** Nothing downstream
  parses a string.

## The state a node carries

A `Node` is what the UI and the report see. `_NodeState` in `search.py` is the
private half — it also holds the checkpoint handle, the full file contents at
that state, and the list of hypotheses already tried on this branch.

Keeping the **file contents per node** is what makes depth work: a child patches
its parent's files, not the original repository, so partial repairs accumulate
down a branch instead of being re-derived.

```
Node (public)                    _NodeState (private)
├── id, parent_id, depth         ├── node          → the public half
├── checkpoint_id                ├── checkpoint    → forkable handle
├── hypothesis                   ├── files         → {path: contents} at this state
├── edits, explanation           ├── report
├── report, score, status        ├── stdout, stderr
├── fixed[], regressions[]       └── tried[]       → what this branch already attempted
└── stdout_tail, wall_seconds
```

## Design decisions worth knowing

**Immutability is the invariant.** No operation mutates an existing checkpoint.
Backtracking is therefore not an operation at all — it is the absence of one.

**Scoring reads JUnit XML, not stdout.** `--junitxml` is appended to the test
command and the report is read back out of the specific checkpoint the branch
produced. That yields per-test identities, which is what makes a *trade*
("fixed two, broke one") distinguishable from progress. Text parsing exists only
as a fallback.

**Validation precedes execution.** A patch whose search block does not match
exactly once is rejected in `repo.apply_edits` before any sandbox call. Bad
patches cost tokens, never wall-clock.

**One event stream, two front ends.** `search.py` emits events; the CLI renders
them to a terminal and the server relays them over SSE. Neither front end knows
anything the other does not.

**Two backends, one contract.** `LocalBackend` implements the same four
operations with directory snapshots. It provides no isolation and is not the
product — it exists so the search can be exercised offline, and so
`--no-branching` has a faithful baseline to compare against.
