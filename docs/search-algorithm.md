# The search algorithm

Implemented in [`arborist/search.py`](../arborist/search.py).

## The problem being solved

A failing test suite has an unknown cause and several plausible explanations.
Each explanation implies a different patch. You cannot tell which one is right
without running the tests — and running the tests is the expensive part.

A linear agent picks one explanation, applies it, runs the tests, and reasons
from whatever happened. If the patch made things worse, everything it does next
is built on a damaged repository.

Arborist treats this as **best-first search over immutable repository states**.

## The loop

```
root = repo with dependencies installed and the suite run once
frontier = [root]

while budget remains:
    node       = select(frontier)                 # highest score, shallowest first
    hypotheses = diagnose(node)                   # Super, or Ultra if stalled
    patches    = [propose(h) for h in hypotheses] # Nano, in parallel
    children   = [evaluate(p) for p in patches]   # each on its own fork of node

    if any child is green:  return it
    frontier += children that improved or held steady
    frontier -= node
```

Every step below is one function in `search.py`.

---

## 1. Select — `_select`

Among unexpanded nodes below the depth cap, take the highest score; ties go to
the **shallowest** node.

```python
max(live, key=lambda nid: (score(nid), -depth(nid)))
```

Why shallow first: breadth is cheaper than depth. Siblings at depth 1 are
independent theories of the same failure, evaluated from a checkpoint that
already exists. Going deeper means committing to a theory. Spend the cheap,
independent options before the expensive, committed ones.

## 2. Diagnose — `_expand` → `agent.diagnose`

One call, tier chosen adaptively:

```python
tier = "ultra" if self._stalls >= STALL_LIMIT else "super"   # STALL_LIMIT = 2
```

A *stall* is an expansion that produced no new best score. Two in a row means the
cheaper model has stopped making progress, so the next diagnosis is escalated.
Any improvement resets the counter.

The prompt asks for **distinct** hypotheses, and is given `parent_attempts` —
what this branch already tried and how it went — so expansions do not loop.

The model may also set `needs_external_docs` with a `search_query`, which is the
only path to the network. See [models.md](models.md#tavily).

## 3. Propose — `agent.propose_patch`

One Nano call per hypothesis, run in a `ThreadPoolExecutor` (at most 8 workers).
Each call implements **only its assigned hypothesis**; overlapping edits would
make the sibling comparison meaningless.

Output is a list of `Edit`s, each preferring an exact `search`/`replace` pair
over a whole-file rewrite — small models reproduce a quoted snippet more reliably
than they regenerate a file.

## 4. Validate before executing — `repo.apply_edits`

The patch is applied to the parent's in-memory files first. It is rejected if:

- the `search` block does not appear in the file,
- it appears **more than once** (ambiguous),
- the file does not exist,
- it edits a **protected** file (`--protect`, typically the tests: the oracle
  must not be rewritten to agree with the code),
- it leaves a Python file that no longer parses,
- the patch changes nothing — including a rewrite that only restyles code.

A whole-file rewrite is **minimised** first: every changed region is reverted
to the original if the file still parses to the same syntax tree and keeps the
same comments without it. Models restyle files they resend — quote swaps,
moved blank lines — and none of that belongs in a diff someone has to review.

A rejected patch gets **one** repair attempt, with the rejection reason fed back
to the model; only if that fails too does it become a node with status `invalid`.

An invalid node **never reaches the sandbox**. It cost tokens, not wall-clock,
and the tree keeps it so the report shows what was attempted.

One concession: if a `search` block matches on stripped lines and that match is
unique, the real offsets are recovered (`_relaxed_find`). Models occasionally
normalise indentation. Ambiguous matches get no such mercy.

## 5. Evaluate — `_evaluate`

```python
checkpoint, report, … = backend.run(parent.checkpoint,
                                    test_command + " --junitxml=.arborist/report.xml",
                                    files=only_the_changed_files)
report = parse_junit(backend.read(checkpoint, ".arborist/report.xml"))
```

Only changed files are uploaded. The JUnit path is workspace-relative on purpose:
an absolute `/tmp` path would be shared between branches running in parallel, and
each branch must report on its own state alone.

## 6. Score — `Arborist.score`

```python
if report.green:            return 1.0
rate        = report.passed / report.total
regressions = parent.passed_ids - report.passed_ids       # by test identity
fixed       = report.passed_ids - parent.passed_ids
score       = rate - 0.6 * (len(regressions) / parent.total)
```

`REGRESSION_WEIGHT = 0.6`. A collection error or a suite that collected nothing
scores `0.0`.

**Why identities and not counts.** Consider a parent at 2/4 and a child at 2/4:

| | parent passing | child passing | pass rate | verdict |
|---|---|---|---|---|
| trade | `a, b` | `a, c` | unchanged | **regression** — `b` broke |
| progress | `a, b` | `a, b, c` | up | improvement |

Pass rate alone calls the first row "no change" and would happily fork from it.
Comparing identities exposes it as a trade and the penalty pushes it below its
own parent, so the search will not follow it. This is the single most important
line in the file, and the `regression-trap` eval case exists to prove it.

## 7. Classify and prune

| Status | Condition | Enters the frontier? |
|---|---|---|
| `green` | suite passes | run ends immediately |
| `improved` | score above the parent | yes |
| `neutral` | score equal to the parent | yes |
| `regressed` | any test that passed at the parent now fails | **no** |
| `invalid` | patch did not apply, or the sandbox errored | **no** |

Pruned nodes stay in the tree and in the report. They are the record of what was
rejected — see [run-flow.md](run-flow.md#the-report).

## 8. Terminate

The loop ends on the first of:

- a green child,
- `max_nodes` sandbox evaluations (default 24),
- no selectable node — everything is expanded, pruned, or at `max_depth`,
- `BudgetExceeded` from the token accountant,
- any unexpected exception.

Every path returns the partial tree. A run never throws away what it learned.

## 9. Break a tie — `_resolve_tie`

If the run ends without a green node, the best branch may be tied with others
within `TIE_EPSILON`. Ties are where the test suite has run out of information —
which is exactly where a patch may be *gaming* it. Ultra is asked to choose, and
specifically to flag any candidate that passes by weakening an assertion,
swallowing an exception, or special-casing the test input. Flagged nodes get a
note in the report; if adjudication fails for any reason, the test-based winner
stands.

---

## The baseline mode

`--no-branching` (`settings.branching = False`) makes three changes, and nothing
else:

1. only the first hypothesis per expansion is used,
2. evaluations fork from the **pre-setup base**, not the parent,
3. the setup command is prepended to every test run.

That is a faithful container-per-attempt agent: same models, same prompts, same
budget, no checkpoint reuse. It is what `evals/run_eval.py` compares against.

## Worked example — `examples/broken-invoice`

Three unrelated bugs, nine tests, four red at the start.

```
baseline 5/9  score 0.56
   ├── A  rounding         6/9  improved   0.67   ◄─ best, becomes fork point
   ├── B  coupon order     5/9  neutral    0.56
   ├── C  "fix" the test   5/9  regressed  0.29   ◄─ broke line_total, pruned
   └── D  bad search block  --  invalid     --    ◄─ never reached the sandbox
            │
            ├── A→B  coupon order   7/9  improved  0.78   ◄─ new fork point
            └── A→E  off-by-one     6/9  neutral   0.67
                     │
                     └── A→B→E  off-by-one  9/9  GREEN
```

The final diff is `unified_diff(original_files, winning_node.files)` — the
accumulated effect of the whole winning path, not the last patch alone.
