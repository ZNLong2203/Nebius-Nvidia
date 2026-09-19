# Models: Nemotron tiering

All inference goes through **Nebius Token Factory**'s OpenAI-compatible endpoint
at `https://api.tokenfactory.nebius.com/v1/`. Implemented in
[`arborist/llm.py`](../arborist/llm.py); prompts live in
[`arborist/agent.py`](../arborist/agent.py).

## The three tiers

| Tier | Model id | Calls per iteration | Job |
|---|---|---|---|
| `nano` | `nvidia/nemotron-3-nano-30b-a3b` | **k** (one per candidate patch) | Write one minimal patch for one assigned hypothesis |
| `super` | `nvidia/nemotron-3-super-120b-a12b` | 1 | Diagnose the failure, produce *distinct* hypotheses |
| `ultra` | `nvidia/nemotron-3-ultra-550b-a55b` | 0 in the normal case | Escalated diagnosis when stalled; tie adjudication |

With the default `k = 4`, a normal iteration is **one Super call and four Nano
calls**. The tiering is not decorative — it is the cost argument:

> Most branches are thrown away. The work that gets discarded must be the cheap
> work.

Change the mapping in one place, [`arborist/config.py`](../arborist/config.py):

```python
MODEL_NANO  = "nvidia/nemotron-3-nano-30b-a3b"
MODEL_SUPER = "nvidia/nemotron-3-super-120b-a12b"
MODEL_ULTRA = "nvidia/nemotron-3-ultra-550b-a55b"
```

## When Ultra wakes up

Two triggers, both earned rather than scheduled.

**Stall.** Two consecutive expansions with no improvement in the best score
(`STALL_LIMIT = 2`) escalate the next diagnosis from Super to Ultra. Any
improvement resets the counter.

**Tie.** If the run ends without a green node and the leading branches are within
`TIE_EPSILON` of each other, Ultra adjudicates.

The tie case is the interesting one. When the test suite cannot separate two
patches, it has stopped being informative — and that is precisely the situation
where a patch might be *gaming* it. The adjudication prompt says so explicitly:

> A patch that makes tests pass by weakening an assertion, catching and swallowing
> an exception, or special-casing the test input is WORSE than a failing patch:
> say so.

Its verdict returns a winner, a reason, and a list of `suspicious` node ids, which
are annotated in the report rather than silently dropped.

## The three prompts

### `DIAGNOSE_SYSTEM` — Super (or Ultra)

Produces root cause plus up to `k` hypotheses. The prompt is built around one
constraint that most agent prompts do not have:

> Two hypotheses that would produce the same edit are wasted branches — make them
> genuinely different theories of the bug.

It also receives `parent_attempts`: what this branch has already tried and how
each attempt scored, so expansions do not loop.

Additional guards: never invent a file or symbol it has not seen; prefer fixing
the source over the test unless the output proves the test is wrong; request more
files via `request_files` rather than guessing.

Schema: `root_cause`, `confidence`, `needs_external_docs`, `search_query`,
`request_files[]`, `hypotheses[{title, rationale, target_files[], strategy}]`.

### `PATCH_SYSTEM` — Nano

One hypothesis in, one patch out.

```json
{"explanation": "...",
 "edits": [{"path": "...", "search": "...", "replace": "..."}]}
```

`search` must be copied character-for-character and must appear **exactly once**
in the file. Whole-file rewrites via `new_content` are allowed for short files.
The prompt forbids reformatting, renaming, explanatory comments, and touching
anything outside the assigned hypothesis — sibling branches must stay comparable.

### `ADJUDICATE_SYSTEM` — Ultra

Candidates with their hypothesis, explanation, score, fixed/broken lists and
diff. Judged on correctness of reasoning, blast radius, and whether the change
would survive code review.

## Structured output

Every call uses Token Factory's structured output:

```python
response_format = {"type": "json_schema",
                   "json_schema": {"name": "arborist_response",
                                   "strict": False, "schema": schema}}
```

with a retry at `{"type": "json_object"}` if the strict form is refused, and
`llm.parse_json` behind both. That parser unwraps fenced blocks, skips
surrounding prose, and scans brace-balanced candidates while respecting string
escapes — a reasoning model wrapping its answer in commentary should not cost a
whole branch.

The schema is also restated in the prompt text, which the Token Factory docs
recommend and which measurably helps.

## Budget accounting

`Usage` tracks calls, prompt tokens and completion tokens **per tier**. Exceeding
`ARBORIST_TOKEN_BUDGET` (default 1.5M) raises `BudgetExceeded`, which stops the
loop and returns the partial tree rather than failing the run.

Both the CLI and the run report print the per-tier table, which is what keeps the
cost claim checkable:

```
tier    model                              calls   tokens
nano    nvidia/nemotron-3-nano-30b-a3b        12   41,204
super   nvidia/nemotron-3-super-120b-a12b      3   18,551
ultra   nvidia/nemotron-3-ultra-550b-a55b      0        0
```

## Tavily

Implemented in [`arborist/tools/tavily.py`](../arborist/tools/tavily.py). It is
the **only** part of the search that touches the network beyond Nebius.

Diagnosis decides for itself when to use it, by setting `needs_external_docs` and
emitting a `search_query`. The instruction is narrow:

> Set `needs_external_docs` only when the failure originates inside a third-party
> package and the repository cannot tell you why.

That is the class of bug a repo-local agent cannot reason its way out of — a
changed API, a deprecation, behaviour inside a dependency — because the answer was
never in the context window. When it fires, diagnosis runs **once more** with the
retrieved evidence appended, and the evidence is carried into the patch prompts
for that expansion.

Results are cached per query within a run, and any failure degrades to "no
evidence" rather than raising: search is an optimisation, never a dependency.

## Offline substitute

`ScriptedLLM` implements the same two methods (`json`, `text`) and pops
pre-programmed responses per tier. It is what lets `tests/` exercise the entire
search with no credentials — see [development.md](development.md).
