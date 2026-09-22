# Evals

```bash
python evals/run_eval.py --cases all
```

Every case runs twice under the same patch budget — branching on and off — and the
results land in `results.md`: solved yes/no, tests passing before and after,
patches evaluated, sandbox executions, **how many times setup had to run**,
invalid patches, wall time, and tokens per tier.

## What each case is for

Measured on Nebius Sandboxes at commit `7b11e3d`, three runs per arm
([`results-contree.md`](results-contree.md)):

- **`broken-invoice` and `masked-faults` need exploring**, and that is where the
  search wins outright: branching solved them 3/3 and 2/3, the linear baseline
  0/3 on both, spending its full budget each time.
- **`regression-trap` and `outside-knowledge` need one good patch**, and both
  arms solve them 3/3 — so branching costs nothing where it is not needed. They
  also earned their keep during the build: they caught a patch-application bug
  that was losing three of five branches.

On real repositories, see [`swebench/`](swebench/README.md): 14 of 23 SWE-bench
Lite issues resolved and re-verified, at a third of the linear agent's cost.

## What "the same budget" means

`max_nodes` caps how many candidate patches each arm may evaluate, and both arms
get the same figure. Depth is only a constraint on the branching arm: the linear
arm evaluates one hypothesis per expansion, so a shared `max_depth` would cap it
at four patches against the other's twelve — not the same budget, and quietly
decisive.

Neither arm now ends with budget left. A node that has been expanded can be
revisited, so one bad patch no longer empties the frontier and stops a search
that has spent a fraction of its allowance. That used to make the linear arm
look beaten when it had simply been cut off.

## The rule for a case

**The answer key lives in this file, never inside the case directory.**
Everything inside a case is loaded into the agent's context, so a README that
names the bug is an answer key, and a result obtained by reading one measures
nothing. A case states the *expected behaviour* in docstrings and test names,
and nothing about the defect.

The second trap is a case the model can solve from its priors without reading
anything. Guard against it by making the *obvious* fix insufficient.

## The cases

### `broken-invoice` — depth

Three independent bugs in three files (see [`../examples/README.md`](../examples/README.md)).
No single edit fixes all three and none masks another, so the search must keep a
partial repair and build on it. Green is reached at depth 3.

### `regression-trap` — backtracking

A bounded TTL cache with two red tests whose obvious fixes fight each other.

- One test wants `get` to drop an expired entry. Easy, one line.
- The other wants a recently read entry to survive eviction. The one-line fix for
  *that* is to refresh the timestamp on read — which makes entries look young
  forever and destroys expiry.

Each fix in isolation looks like progress and the second undoes the first — that
was the intent.

**It does not work.** Run against Nemotron 3, both the branching search and the
linear baseline repair it, the baseline in a single patch. The model does not
take the bait, so the case measures nothing about search. A case that one patch
solves cannot, and the same is true of the other two. Replacing them with a case
where the second fault is invisible until the first is repaired is open work.

### `masked-faults` — a case one patch cannot solve

Three faults in a ledger, arranged so that the later ones are **invisible from
the starting state** and the obvious fix gives no signal.

1. `parse.py` imports a name `rules.py` does not define, so the suite does not
   collect. One error, no test results, nothing else observable.
2. `rules.is_large` uses `>` where the documented boundary is inclusive.
3. `report.in_period` excludes the period's final day.

The data is shaped to make these interact: eleven transactions sit exactly on
the threshold and fourteen fall on the final day of the period.

| State | Result |
|---|---|
| as shipped | 1 collection error — faults 2 and 3 cannot be seen |
| import fixed | 3 failed, 1 passed |
| **+ the threshold, which is what the failing test is named after** | **3 failed, 1 passed — no change at all** |
| + the period boundary instead | 1 failed, 3 passed |
| all three | 4 passed |

The third row is the point. The test that fails is called
`test_large_is_inclusive_of_the_threshold`, so the obvious move is to fix the
threshold — and that produces *no measurable improvement*, because the period
filter is still dropping the rows that would have proved it. An agent that
scores its work will read that as "my fix was wrong" and may revert it. The
fault that unlocks three tests is the one nothing points at.

Reading the source cannot separate them: which fix moves the numbers depends on
where the rows fall in the data. Only running does.

**What it measures: whether a search is worth anything.** On Sandboxes, commit
`7b11e3d`, three runs per arm:

| | solved | patches (median) | wall (median) | setup runs |
|---|---|---|---|---|
| branching | **2/3** | 8 | 313 s | 1 per run |
| linear baseline | **0/3** | 12 — budget exhausted | 470 s | 11–12 per run |

The [branching tree](../evals/evidence/masked-faults-branching.json) put three
rival repairs on one checkpoint: the fix the failing test is named after came
back **neutral**, its sibling reached 3/4, and the next fork closed it out. The
[linear tree](../evals/evidence/masked-faults-linear.json) spent ten of its twelve
patches retrying the right theories on one state, and every one that applied
regressed the suite back to a collection error — it had no sibling from the same
state to compare against, so it could not tell a wrong theory from a wrong
implementation of a right one.

### `outside-knowledge` — knowing when to look it up

An order model written against Pydantic 1.x, in a project whose pin has moved to
2.x. (That framing lives here, not in the case: the module docstring used to say
it, which handed the agent the answer.) Nothing in the tree records what `@root_validator` and `@validator` became;
a repo-local agent can read every file and still not know. This is the class of
failure the Tavily lookup exists for.

It also punishes the lazy fix. The error names `skip_on_failure=True`, and adding
it makes the exception go away — but the deprecated API stays, and the project
fails on `DeprecationWarning`:

| Patch | Result |
|---|---|
| as shipped | collection error |
| `@root_validator(skip_on_failure=True)` | **still fails** — deprecated API, warning is fatal |
| `@model_validator(mode="after")` **and** `@field_validator` | 4 passed |

No partial credit is available: until both decorators are migrated the suite does
not collect, so every branch scores zero. That makes this the opposite of
`broken-invoice`: depth cannot help, only breadth — several rival migrations
evaluated from one prepared checkpoint. In practice the lookup does most of the
work: once diagnosis has the migration guide, one patch is usually enough, and
the linear baseline solved it 3/3 as well.
