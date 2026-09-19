# Evals

```bash
python evals/run_eval.py --cases all
```

Every case runs twice under an identical budget — branching on and off — and the
results land in `results.md`: solved yes/no, tests passing before and after,
patches evaluated, sandbox executions, **how many times setup had to run**,
invalid patches, wall time, and tokens per tier.

## What these cases do and do not measure

As of the last run, **none of the three discriminates**: Nemotron 3 solves each
of them in one or two patches, and a case that one patch solves cannot measure a
search. The table they produce is still worth having — it caught a patch-
application bug that was losing three of five branches — but it is not evidence
that branching beats a linear baseline, and this file will not pretend otherwise
until a case exists that can show it.

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

### `outside-knowledge` — knowing when to look it up

An order model written against Pydantic 1.x, in a project whose pin has moved to
2.x. Nothing in the tree records what `@root_validator` and `@validator` became;
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
`broken-invoice` — the only thing that helps is **breadth**, several rival
migrations evaluated from one prepared checkpoint.
