# Development

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[contree,dev]"
cp .env.example .env          # add NEBIUS_API_KEY
```

Python 3.11+. `uv` works too and is faster:

```bash
uv venv .venv -p 3.12 && uv pip install -e ".[contree,dev]"
```

## Tests

```bash
pytest -q          # 56 tests, no network, no credentials
ruff check .
```

The suite runs offline because both external dependencies have offline
implementations of their contracts:

| Real | Offline stand-in | Where |
|---|---|---|
| Nemotron via Token Factory | `ScriptedLLM` — pops pre-programmed responses per tier | `arborist/llm.py` |
| Nebius Sandboxes | `LocalBackend` — directory snapshots | `arborist/sandbox.py` |

Everything else is genuinely executed: selection, scoring, patch application,
regression detection, backtracking, the HTTP API and the CLI.

| File | Covers |
|---|---|
| `tests/test_repo.py` | Patch application and its failure modes, diffing, JUnit and text parsing, context selection |
| `tests/test_llm.py` | JSON recovery from fenced, prose-wrapped and malformed output; usage accounting |
| `tests/test_sandbox.py` | The backend contract, especially that children never mutate parents and siblings are isolated |
| `tests/test_search.py` | Scoring, and an end-to-end repair of all three bugs in `examples/broken-invoice` at depth 3 |
| `tests/test_server.py` | Endpoints, run lifecycle, event replay, failure reporting |
| `tests/test_cli.py` | Exit codes, rendered output, report files |

The test worth reading first is `test_search.py::test_search_repairs_every_bug_by_deepening`.
It asserts the agent reaches depth 3, that scores increase monotonically along the
winning path, and that the diff never touches `tests/`.

## Running against the real services

```bash
arborist fix examples/broken-invoice \
  --setup "pip install -q -r requirements.txt" \
  -k 4 --max-nodes 16
```

Useful flags:

| Flag | Effect |
|---|---|
| `--backend local` | Skip Sandboxes; same agent logic, directory snapshots |
| `--no-branching` | Linear baseline: one hypothesis, no checkpoint reuse |
| `-k, --fanout` | Candidate patches per expansion |
| `--max-nodes` | Hard cap on sandbox evaluations |
| `--context, -c` | Files or globs always shown to the model |
| `--out` | Where the run report is written (default `runs/`) |

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `NEBIUS_API_KEY` | — | Token Factory and Sandboxes |
| `NEBIUS_BASE_URL` | `https://api.tokenfactory.nebius.com/v1/` | Inference endpoint |
| `CONTREE_BASE_URL` | `https://api.tokenfactory.nebius.com/sandboxes` | Sandboxes endpoint |
| `NEBIUS_PROJECT_ID` | — | Optional project scoping |
| `TAVILY_API_KEY` | — | Enables the external-docs tool |
| `ARBORIST_BACKEND` | `contree` | `contree` \| `local` |
| `ARBORIST_BRANCHING` | `1` | `0` for the linear baseline |
| `ARBORIST_FANOUT` | `4` | Candidates per expansion |
| `ARBORIST_MAX_NODES` | `24` | Sandbox evaluation cap |
| `ARBORIST_MAX_DEPTH` | `4` | Tree depth cap |
| `ARBORIST_TOKEN_BUDGET` | `1500000` | Total tokens across all tiers |

## Adding an execution backend

Implement the four methods in [sandboxes.md](sandboxes.md#the-contract), honour
the immutability invariant, and register it in `build_backend`. Then run
`tests/test_sandbox.py` against it — those tests are the contract, particularly
`test_a_child_never_mutates_its_parent` and `test_siblings_are_isolated_from_each_other`.

## Adding an eval case

1. Create `evals/cases/<name>/` with a repo whose tests fail.
2. Add an entry to `CASES` in [`evals/run_eval.py`](../evals/run_eval.py) with its
   path, test command, setup command, and the number of distinct bugs.
3. `python evals/run_eval.py --cases <name>`

A good case has bugs that are **independent** (so depth is required) or
**interacting** (so backtracking is required). `broken-invoice` is the first kind;
`regression-trap` is the second, and is the more interesting test of the design.

## Supporting another language

The only language-specific assumptions live in `repo.py`:

- `TEXT_SUFFIXES` — which files the models are allowed to read
- `parse_junit` — works with any runner that emits JUnit XML (Jest, Go's
  `gotestsum`, Maven Surefire, RSpec)
- `parse_pytest_text` — the fallback, which is pytest-shaped

Point `--test` at a command that emits JUnit XML to `.arborist/report.xml` and
most of it works unchanged.

## Code conventions

- `search.py` never imports a provider; it receives a `Backend` and an `LLM`
- `agent.py` returns dataclasses, never raw model output
- Anything that can fail on a branch becomes a node status, not an exception
- `ruff` at line length 110; `B008` and `PLW1510` are deliberately ignored
  (Typer's option idiom, and a non-zero test exit being the expected signal)
