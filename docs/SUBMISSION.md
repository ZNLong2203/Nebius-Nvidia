# Devpost submission kit

Working draft of everything the submission form asks for. Fill the `[ ]` gaps,
paste the rest.

---

## Track

**Coding and Agentic Engineering.** Secondary eligibility: **Best Use of Tavily**
(the diagnosis step makes a functional runtime call to the Tavily API whenever a
failure originates outside the repository).

City: **Da Nang** — the Builders & Brews city list includes it, and the
Resources page states every eligible submission associated with a participating
city is considered for the $500 City Winner Award.

---

## Elevator pitch (≤ 200 characters)

> Coding agents fix bugs in a straight line. Arborist searches a tree of forked
> sandbox states — rival theories tested in parallel, regressions abandoned for free.

---

## Inspiration

Every coding agent available today shares one shape: edit, run, read the error,
edit again. Watching them work, three costs keep showing up and none of them are
about the model.

When attempt #3 makes things worse, the agent has to *undo* — and until it
finishes undoing, it is reasoning on top of a repository it has already damaged.
Most agents do not even try; they carry the damage forward. Second, the
expensive part — clone, install, build, warm the cache — gets repeated for every
candidate patch, because each attempt starts from a fresh container. Third, and
worst: a bug usually has two or three plausible explanations, and a linear agent
picks one, commits, and never learns that the second was right.

Then Nebius Sandboxes turned out to have Git-like branching over container
execution state. Every command produces a new immutable filesystem version, and
you can fork from any of them. All three costs stop being costs.

## What it does

Arborist takes a repository whose tests fail and returns a patch that makes them
pass — by searching a tree of repository states rather than walking a line of
edits.

It runs the setup once and keeps that checkpoint. Then it asks Nemotron 3 Super
to diagnose the failure and produce several *genuinely different* theories of
it. Each theory becomes a patch written by Nemotron 3 Nano, applied to its own
fork of the same checkpoint, and tested independently. The tests score every
fork; the best one becomes the next fork point; anything that regresses is
abandoned at zero cost, because nothing was ever mutated.

What comes out is a patch **and the record of what was rejected** — every branch
explored, the tests each one fixed and broke, and the diffs that were discarded.
That is the thing a reviewer actually wants, and no coding agent ships it today.

## How I built it

- **Nemotron 3 Nano** writes every candidate patch — one call per branch, the
  widest step in the system. Most branches get thrown away, so the discarded
  work has to be the cheap work.
- **Nemotron 3 Super** diagnoses each node and produces the hypotheses the
  search branches on. This is the reasoning that shapes the tree.
- **Nemotron 3 Ultra** is only woken when the search stalls twice with no
  improvement, or when two branches score *identically*. That second case is
  the interesting one: when the tests cannot separate two patches, the suite has
  stopped being informative — which is exactly when one of them is gaming it.
  Ultra is asked specifically to catch a patch that passes by weakening an
  assertion or swallowing an exception, and to flag it rather than let the score
  stand.
- **Nebius Sandboxes (ConTree)** is every execution. `base()` builds the
  expensive prefix, `run()` forks from any checkpoint, `read()` pulls the JUnit
  report back out of one specific state.
- **Tavily** is called only when diagnosis decides the failure originates
  outside the repo — inside a third-party package, a changed API, a deprecation.
  Those are the bugs a repo-local agent cannot reason its way out of, because
  the answer was never in its context window.
- Scoring uses JUnit XML, not stdout scraping, so "fixed" and "broke" are lists
  of named tests. That is what lets the search see a *trade* — fixed two, broke
  one — and refuse to follow it.
- A patch that does not apply cleanly is rejected before execution: it costs
  tokens, never wall-clock.

## Challenges

The honest one: making hypotheses actually *differ*. Branching buys nothing if
the model returns four rephrasings of the same idea. The prompt pushes hard
against it, and every branch is told what its siblings already tried, but this
remains the real ceiling on search quality.

The second: scoring. Pass-rate alone calls "fixed two, broke one" progress. It
took switching to per-test identities, compared against the parent state, before
the search stopped chasing trades.

## Accomplishments

The `regression-trap` eval case: a TTL cache where the obvious fix for one test
silently breaks another. A linear agent takes the bait. Arborist sees the named
regression, marks the branch, and returns to its sibling with the earlier
partial repair still intact.

## What I learned

That the interesting constraint in agent design is often infrastructural, not
model-shaped. Nothing here needs a smarter model — it needs execution state you
can fork.

## What's next

Opening the pull request directly, with the rejected alternatives in the body.
Language runners beyond pytest. Reusing a scored branch tree across runs on the
same repo.

## Built with

`nebius-token-factory` `nebius-sandboxes` `nvidia-nemotron-3-nano`
`nvidia-nemotron-3-super` `nvidia-nemotron-3-ultra` `tavily` `python` `fastapi`
`typer` `server-sent-events`

---

## Demo video script (2:45)

| Time | On screen | Said |
|---|---|---|
| 0:00–0:15 | `examples/broken-invoice`, `pytest` running, **4 failed, 5 passed** | "This billing module has three unrelated bugs. Rounding, order of operations, and an off-by-one. Four red tests." |
| 0:15–0:35 | Terminal: `arborist fix …`; tree starts drawing in the browser | "A normal coding agent would now start guessing, one edit at a time. Arborist does something else." |
| 0:35–1:05 | Tree: one checkpoint, four branches opening at once | "It installs dependencies **once** and keeps that checkpoint. Nemotron 3 Super reads the failure and produces four different theories. Nemotron 3 Nano writes a patch for each — and every one is tested on its **own fork** of the same state, in parallel. On Nebius Sandboxes a fork is free." |
| 1:05–1:30 | Click the red branch → panel shows named broken tests | "This one fixed a test and broke another. Because scoring compares actual test identities against the parent, that shows up as a regression — not as progress. The branch is abandoned. Nothing was mutated, so there's nothing to undo." |
| 1:30–2:00 | Tree deepens; green node appears | "The winning branch becomes the next fork point, so partial repairs are kept and built on. Three levels down: nine of nine passing." |
| 2:00–2:20 | Token table: nano / super / ultra | "Nano did the wide, disposable work. Super did the reasoning. Ultra was only woken to break a tie — and when it's woken, it's asked whether a patch is passing the tests by *gaming* them." |
| 2:20–2:45 | `--no-branching` result side by side | "Same models, same prompts, same budget, no forking: the setup command runs again on every attempt, and it follows the first theory it picked. That's the difference branching makes." |

Record at 1440p or larger. Show the *browser tree* for the middle minute — that
is the shot that explains the idea without words.

---

## Feedback section (worth $100 + swag, 10 awards — write it properly)

Points worth making, all of them encountered during the build:

- **Sandboxes SDK versus its docs.** The published Python guides describe
  `Contree(api_client)` taking a pre-built `contree_client` instance, but the
  current stable release on PyPI (`contree-sdk` 0.3.6) exposes
  `ContreeSync(token=…, base_url=…)` instead; the client-injection API is only
  on the 0.4.0 dev releases. The mini-swe-agent integration page documents its
  own breakage against the same change. Pinning the docs to the released
  version, or labelling the version each page targets, would save a first-time
  user an hour.
- **Sandboxes is genuinely differentiated and under-sold.** Branching container
  state is the most interesting primitive in the platform and it is filed under
  "Sandboxes / Overview" as a beta feature. A worked example of *search over
  execution state* — not just "run untrusted code" — would show what it is for.
- **Nemotron tiering deserves a sizing guide.** The hackathon brief says to use
  Ultra for hard reasoning and Nano for everyday calls, which is right, but
  there is no guidance on where the boundary actually falls. A published
  cost/quality comparison on a concrete agentic task would be the single most
  useful doc.
- **`json_schema` response format**: worked reliably across all three tiers.
  Worth stating explicitly on the model cards which models support strict
  schema mode, since the docs say to look for a "JSON mode" tag.
- **Credits versus the workload.** $50 goes fast on a search that fans out.
  Anything that makes prompt caching or reuse visible in the observability view
  would help people stay inside the budget.

[ ] Rewrite in your own voice before submitting — judged on completeness,
viability and potential impact.

---

## Pre-submission checklist

- [ ] Repo public, MIT license **visible in the GitHub About box**
- [ ] README highlights Nemotron usage, Token Factory, Sandboxes, Tavily — done
- [ ] Public demo URL, free, no login, live until 15 Dec 2026
- [ ] YouTube video public, **≤ 3 min**, audio names Token Factory + Nemotron
- [ ] `evals/results.md` committed with real numbers from a real run
- [ ] Track selected: Coding and Agentic Engineering
- [ ] City selected: Da Nang
- [ ] Feedback section completed
- [ ] Submitted ≥ 12 hours before 30 Oct 2026, 10:00 PT — and then not touched
