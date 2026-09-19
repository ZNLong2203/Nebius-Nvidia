# Arborist

**A coding agent that repairs a failing repository by searching a tree of sandbox states instead of walking one line of attempts.**

Built for the [Nebius x NVIDIA Global AI Hackathon](https://nebiusglobalaihackathon.devpost.com/) — *Coding and Agentic Engineering* track. Runs on **Nebius Token Factory**: NVIDIA **Nemotron 3** for every model call, **Nebius Sandboxes** for every execution.

---

## The problem

Every coding agent shipping today is a straight line:

```
edit → run tests → read the failure → edit again → run tests → …
```

That shape has three costs that nobody talks about:

1. **Backtracking is destructive.** When attempt #3 makes things worse, the agent has to *undo* — and in the meantime it has been reasoning on top of a repository it already damaged. Most agents simply carry the damage forward.
2. **The expensive prefix is paid over and over.** Clone, `pip install`, build, warm the cache — a container-per-attempt agent repeats all of it for every single candidate patch.
3. **Rival theories are never compared.** A bug usually has two or three plausible explanations. A linear agent picks one, commits to it, and never finds out that the second one was right.

## The idea

Treat repair as **search over immutable repository states**.

Nebius Sandboxes gives every executed command a new, immutable filesystem version, and lets you **fork from any of them** — Git branching, but for container execution state. That single primitive turns all three costs into non-problems:

```
    [ repo + deps installed + tests run ]     ← the expensive prefix, paid ONCE
                     │
      ┌──────────────┼──────────────┬──────────────┐
      ▼              ▼              ▼              ▼
  hypothesis A   hypothesis B   hypothesis C   hypothesis D     ← forked in parallel
  5/9 passing    7/9 passing    5/9 · BROKE 2  patch invalid
      ✗              ★               ✗           (never ran)
                     │
          ┌──────────┴──────────┐
          ▼                     ▼                              ← the winner becomes
   next hypothesis       next hypothesis                          the next fork point
     9/9 ✓ green            7/9 neutral
```

- **Breadth**: four rival theories of one bug, each tested from *the same* starting state — so their scores are genuinely comparable.
- **Depth with free backtracking**: a partial fix that repairs two of three failures becomes the base for the next attempt. If that attempt regresses, the partial fix is still sitting there untouched, because nothing was ever mutated.
- **Cost**: with `k=4` candidates across 3 levels, a container-per-attempt agent pays the setup cost 12 times. Arborist pays it once.

## What it produces

Not just a patch — **a patch plus the record of what was rejected and why**. The run report contains every branch that was explored, the tests each one fixed and broke, and the diff that was discarded. That is the thing a human reviewer actually wants and no coding agent gives them today.

---

## How NVIDIA Nemotron is used

Three tiers, chosen by what each step is worth. This is the core cost argument, and the run report prints the token counts so it stays checkable.

| Tier | Model | Called | Why this tier |
|---|---|---|---|
| **Nano** | `nvidia/nemotron-3-nano-30b-a3b` | Once **per candidate patch** — the widest step in the whole system | Most branches are thrown away. The work that gets discarded must be the cheap work. |
| **Super** | `nvidia/nemotron-3-super-120b-a12b` | Once **per node**, to diagnose the failure and produce *distinct* hypotheses worth branching on | This is the reasoning that shapes the search. Getting hypotheses that genuinely differ is what makes breadth worth paying for. |
| **Ultra** | `nvidia/nemotron-3-ultra-550b-a55b` | Only when the search **stalls** (two expansions with no improvement), or when two branches score **identically** | Expensive, so it is earned, not scheduled. |

The Ultra tie-break is the interesting one. When the tests cannot separate two branches, the suite has stopped being informative — and that is exactly the situation where one of the patches is *gaming* it. Ultra is asked specifically to catch a patch that passes by weakening an assertion, swallowing an exception, or special-casing the test input, and to flag it rather than let the score stand. See [`arborist/agent.py`](arborist/agent.py) (`ADJUDICATE_SYSTEM`).

All three are served through **Nebius Token Factory**'s OpenAI-compatible endpoint, with `response_format: json_schema` for every structured step.

## How Nebius Token Factory and Sandboxes are used

| Service | Where |
|---|---|
| **Token Factory — inference** | Every Nemotron call, via `https://api.tokenfactory.nebius.com/v1/`. One base URL, three models, no per-model plumbing — swapping a tier is a one-line change in [`arborist/config.py`](arborist/config.py). |
| **Token Factory — structured output** | `json_schema` response format on diagnosis, patch generation and adjudication, with a lenient recovery parser behind it ([`arborist/llm.py`](arborist/llm.py)). |
| **Token Factory — Sandboxes (ConTree)** | Every command execution. The Git-like branching *is* the product: `base()` builds the prefix, `run()` forks from any checkpoint, `read()` pulls the JUnit report back out of a specific state. See [`arborist/sandbox.py`](arborist/sandbox.py). |
| **Tavily** | Diagnosis decides for itself when the failure originates *outside* the repository — inside a third-party package, a changed API, a deprecation — and only then emits a query. Those are precisely the bugs a repo-local agent cannot reason its way out of, because the answer was never in the context window. Nothing else in the search touches the network. See [`arborist/tools/tavily.py`](arborist/tools/tavily.py). |

### Where Token Factory accelerated the build

- **One endpoint, three model sizes.** The tier experiment — which step can drop to Nano, which needs Ultra — was a config edit, not an integration. That experiment *is* the project; on a single-model provider it would not have been affordable to run.
- **Sandboxes removed the part that usually eats the whole build.** Safe execution of model-written code with forkable state is normally weeks of container plumbing. It is four method calls here.
- **`json_schema` output removed the parsing layer.** Patch edits arrive as validated objects, so a malformed patch costs tokens and never a sandbox execution.

---

## Quick start

```bash
git clone <this repo> && cd arborist
python -m venv .venv && source .venv/bin/activate
pip install -e ".[contree,dev]"

cp .env.example .env     # add NEBIUS_API_KEY (and TAVILY_API_KEY if you have one)
```

Get a key at [tokenfactory.nebius.com](https://tokenfactory.nebius.com). Hackathon participants get $25 in credits with the code `NEBIUS-DEVPOST-GLOBAL26`.

### Repair the bundled broken repository

`examples/broken-invoice` is a billing module with **three unrelated bugs** across three files and **four red tests** — rounding, order of operations, and an off-by-one:

```bash
arborist fix examples/broken-invoice \
  --test "python -m pytest -q" \
  --setup "pip install -q -r requirements.txt" \
  -k 4
```

You get a live tree in the terminal, then the winning diff, the token spend per tier, and a JSON report in `runs/`.

### Watch it search

```bash
arborist serve      # http://127.0.0.1:8000
```

The tree draws itself over server-sent events while the search runs: branches open, score, and get abandoned in real time. Click any node for its hypothesis, its patch, which tests it fixed, and which it broke.

### Compare against a linear agent

```bash
arborist fix examples/broken-invoice --no-branching --setup "pip install -q -r requirements.txt"
```

Same models, same prompts, same budget — one hypothesis at a time, and no checkpoint to fork, so the setup command runs again on every attempt. That is the baseline.

---

## Measuring it

```bash
python evals/run_eval.py --cases all
```

Runs every case twice under an identical budget, branching on and off, and writes `evals/results.md` with: solved yes/no, tests passing before and after, patches evaluated, sandbox executions, **how many times setup had to run**, invalid patches, wall time, and tokens per tier.

Two cases ship:

- **`broken-invoice`** — three independent bugs. Tests whether the search can *deepen*: keep a partial repair and build the next fix on top of it.
- **`regression-trap`** — a TTL cache where the obvious fix for test A silently breaks test B. Tests whether the search notices a *trade* and refuses to follow it.

The second case is the one that matters. Scoring on pass-rate alone calls "fixed two, broke one" progress. Arborist scores against the parent's **test identities**, so a trade shows up as a regression, the branch is marked and abandoned, and the search returns to the sibling. See `Arborist.score` in [`arborist/search.py`](arborist/search.py).

> Results in `evals/results.md` are whatever your own run produces. Numbers are not checked in, because a benchmark table you cannot reproduce is worth nothing.

---

## How it works

```
arborist/
  config.py       model tiers, budgets, settings
  llm.py          Token Factory client, per-tier token accounting, JSON recovery
  sandbox.py      Backend contract · ContreeBackend (Nebius) · LocalBackend (offline)
  agent.py        the three prompts: diagnose → propose → adjudicate
  search.py       selection, scoring, expansion, backtracking
  repo.py         repo IO, patch application, JUnit parsing, diffing
  tools/tavily.py external-knowledge lookup
  server.py       HTTP API + SSE event stream
  cli.py          terminal interface
ui/index.html     the live tree (no build step, no CDN)
```

The loop, once per iteration:

1. **Select** the highest-scoring unexpanded node, shallowest first — breadth is cheaper than depth, so it is spent first.
2. **Diagnose** with Super (or Ultra if the search has stalled): root cause plus up to `k` *distinct* hypotheses. If the failure points outside the repo, Tavily is called and diagnosis re-runs with the evidence.
3. **Propose** one patch per hypothesis with Nano, in parallel.
4. **Validate before executing.** Each edit quotes an exact snippet that must appear exactly once in the file. A patch that does not apply is marked invalid and **never reaches the sandbox** — it costs tokens, not wall-clock. (Reindented snippets get one relaxed second chance; ambiguous ones do not.)
5. **Evaluate**: fork the parent checkpoint, upload only the changed files, run the suite with `--junitxml`, read the report back out of that state.
6. **Score** against the parent's test identities: pass rate, minus a hard penalty for every test that used to pass and no longer does.
7. **Branch, prune, repeat.** Green ends the run. Regressions are recorded in the tree and never forked from.

Scoring uses JUnit XML rather than scraping stdout, so `fixed` and `broke` are lists of named tests, not counts.

### Two backends, one contract

`LocalBackend` implements the same four operations with directory snapshots. It has no isolation and no credentials, and it exists so the search, the scoring, the patch validation and the whole test suite can be exercised offline — which is how the 56 tests in this repo run without touching Nebius. `ContreeBackend` is the real one.

---

## Tests

```bash
pytest -q
```

56 tests, no network and no credentials required: a scripted model stands in for Nemotron and `LocalBackend` for Sandboxes, so the selection, scoring, patch validation, backtracking, API and CLI all genuinely execute. The end-to-end case repairs all three bugs in `examples/broken-invoice` at depth 3 and asserts the agent never edited the tests.

---

## Limitations

Worth stating plainly:

- **Python/pytest first.** The scorer parses JUnit XML, so any runner that emits it works, but only pytest has been exercised.
- **Search quality is bounded by hypothesis diversity.** If Super returns four rephrasings of one idea, breadth buys nothing. The prompt pushes hard against this and `parent_attempts` is fed back, but it is the real ceiling.
- **The suite is the oracle.** A bug with no failing test is invisible, and a weak suite can be satisfied by a bad patch — which is why Ultra is asked to flag suite-gaming rather than trusting the score outright.
- **Sandboxes is in Beta.** Occasional execution failures are handled as node-level outcomes, not crashes, but they do cost a branch.
- **No PR opening yet.** The run report and diff are written to `runs/`; wiring them to a GitHub App is the obvious next step and is not built.

## Documentation

| Page | Read it for |
|---|---|
| [docs/architecture.md](docs/architecture.md) | The pieces, what each owns, how they fit |
| [docs/search-algorithm.md](docs/search-algorithm.md) | Selection, scoring, pruning, termination — with a worked example |
| [docs/run-flow.md](docs/run-flow.md) | One run end to end, and every event it emits |
| [docs/models.md](docs/models.md) | Nemotron tiering, the three prompts, budget accounting |
| [docs/sandboxes.md](docs/sandboxes.md) | The Nebius Sandboxes integration and the backend contract |
| [docs/api.md](docs/api.md) | HTTP endpoints and the SSE event stream |
| [docs/development.md](docs/development.md) | Setup, tests, adding a backend or an eval case |

## License

MIT — see [LICENSE](LICENSE).
