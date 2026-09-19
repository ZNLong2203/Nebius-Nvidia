# Run flow

One run, end to end. Same path whether it started from `arborist fix` or
`POST /api/runs`; only the event renderer differs.

## Sequence

```
CLI / HTTP                search.py                backend            Token Factory
    │                         │                       │                     │
    │ RunConfig               │                       │                     │
    ├────────────────────────►│                       │                     │
    │                         │ load_repo()           │                     │
    │                         │ base(files, image)    │                     │
    │                         ├──────────────────────►│                     │
    │◄── checkpoint(base) ────┤                       │                     │
    │                         │ run(setup_command)    │   ◄── PAID ONCE ──  │
    │                         ├──────────────────────►│                     │
    │◄── checkpoint(setup) ───┤                       │                     │
    │                         │ run(test --junitxml)  │                     │
    │                         ├──────────────────────►│                     │
    │                         │ read(report.xml)      │                     │
    │◄── node(baseline) ──────┤                       │                     │
    │                         │                                             │
    │            ┌────────────┴─── loop until green / budget ───────────┐   │
    │            │                                                     │   │
    │◄─ diagnosing ─┤ diagnose()  ──────────────────────────────────────────►│ Super
    │◄─ diagnosed ──┤            (+ Tavily if the cause is external)   │   │
    │            │                                                     │   │
    │            │ for each hypothesis, in parallel:                   │   │
    │            │     propose_patch() ─────────────────────────────────────►│ Nano
    │            │     apply_edits()           ← reject here, no sandbox │   │
    │            │     run(test) from parent checkpoint ──►│            │   │
    │◄─ node ────┤     score() vs parent identities        │            │   │
    │            └─────────────────────────────────────────────────────┘   │
    │                         │                                             │
    │◄── run_finished ────────┤ unified_diff(original, winner.files)        │
```

## Phases

### 1. Ingest

`repo.load_repo` walks the tree, skipping `.git`, `__pycache__`, `node_modules`,
`.venv`, `dist`, `runs` and friends, and any file over 400 KB. Binary files are
carried into the sandbox but excluded from the text map the models see.

### 2. Build the prefix — *the expensive part, paid once*

```
base()                    → repo materialised at /workspace
run(setup_command)        → dependencies installed        ← this checkpoint is the asset
run(test --junitxml=…)    → baseline measured
```

The setup duration is recorded. With branching on it is paid once; with branching
off it is paid again on every attempt, and `stats.setup_seconds_saved` reports the
difference.

If the baseline is already green the run stops here, having spent **zero** model
calls.

### 3. Search

One expansion per iteration — see [search-algorithm.md](search-algorithm.md).

### 4. Report

```python
diff = unified_diff(original_files, winning_state.files)
```

The diff is the cumulative effect of the whole winning path. `write_report`
emits two files into `runs/`:

- `run-xxxxxxxx.json` — every node, its hypothesis, its edits, which tests it
  fixed and broke, scores, stats, per-tier token usage
- `run-xxxxxxxx.patch` — the winning diff alone

## The report

The interesting part is not the winning patch; it is everything around it. The
JSON contains every branch explored, including the ones that were rejected and
why — the diff that broke two tests, the hypothesis that could not be applied,
the theory that went nowhere.

That is the artifact a reviewer actually wants and no coding agent ships: not
"here is a fix", but "here is a fix, here is what else I tried, and here is what
each alternative did to your test suite."

## Events

`search.py` emits these; the CLI prints them and the server relays them as SSE.

| Event | When | Key fields |
|---|---|---|
| `run_started` | first thing | `run_id`, `repo`, `test_command` |
| `checkpoint` | prefix built | `stage` (`base` \| `setup`), `checkpoint`, `seconds` |
| `node` | a node is created **or re-emitted when it becomes the next fork point** | `node` (full object) |
| `diagnosing` | before a diagnosis call | `node_id`, `tier` |
| `diagnosed` | after it | `root_cause`, `hypotheses`, `searched`, `search_query` |
| `progress` | after an expansion | `best_score`, `stalls` |
| `adjudicated` | Ultra broke a tie | `verdict` |
| `budget_exceeded` | token budget hit | `message` |
| `error` | anything unexpected | `message` |
| `run_finished` | last thing | `result` (the whole report) |

`node` firing twice for the same id is normal: once on creation, once when it is
selected for expansion. Consumers should treat it as upsert. The CLI suppresses
the second by checking `node.expanded`.

The server appends one more, `done`, after the run thread exits — including when
it failed. See [api.md](api.md).

## Failure handling

| Failure | Result |
|---|---|
| Setup command fails | Run aborts with `error`; nothing else attempted |
| Baseline test run produces no report | Run aborts — there is nothing to measure against |
| Patch does not apply | Node marked `invalid`, no sandbox call, search continues |
| Sandbox execution errors | Node marked `invalid` with the error in `note`, search continues |
| Model returns unparseable JSON | Recovered if possible, else an empty object → no hypotheses → that expansion ends |
| Token budget exhausted | Loop stops, partial tree returned with `error` set |
| Anything else | Caught, recorded, partial tree returned |

A run never raises. It always returns a `RunResult` containing whatever was
learned before it stopped.
