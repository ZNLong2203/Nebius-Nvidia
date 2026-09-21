# SWE-bench Lite on Nebius Sandboxes

The hand-built cases in [`evals/cases`](../cases) were designed to test a
search, which makes them easy to suspect of being designed to *flatter* one.
This runs Arborist on real issues from real projects instead: instances from
[SWE-bench Lite](https://www.swebench.com), inside the benchmark's own
evaluation images, on Nebius Sandboxes.

## What is measured — read before quoting a number

**This is test-driven repair, not the SWE-bench leaderboard setting.** The
agent is given the issue text *and* the failing tests: each instance's test
patch is applied before the search starts. The leaderboard withholds those
tests. The numbers here are therefore **not comparable to any leaderboard
figure** and should never be quoted next to one.

It is the setting Arborist is built for — a red suite and a request to make it
green — and it is a fair comparison of the two search strategies, which is what
it is for: both arms get the same instance, models, prompts, budget and tests.

| | |
|---|---|
| Instances | Every SWE-bench Lite instance from `pallets/flask`, `psf/requests`, `mwaskom/seaborn` and `pytest-dev/pytest` — 30 in all. The four repositories were chosen for small codebases and fast suites before anything was run; no instance was picked individually |
| Environment | The official image for each instance, `swebench/sweb.eval.x86_64.<id>`, imported into Sandboxes. The project is already installed at `/testbed`, so there is no setup step and the setup-reuse argument does not apply here |
| What the agent sees | The issue text (`--goal`), the failing output, and the source |
| What it may not do | Edit any file the test patch touches (`--protect`). Such a patch is refused before it reaches the sandbox |
| Budget | Fan-out 3, 12 nodes, identical for both arms. Linear means one hypothesis at a time with no depth cap, exactly as in [`run_eval.py`](../run_eval.py) |
| Success | The test files the test patch touches pass **in full**, confirmed by an independent re-check (below) |

### Validation — before any model is called

An instance whose environment is broken would be scored as an agent failure.
So every instance is first run twice in the sandbox, with no model involved:

1. with the test patch only — the test files must **fail**;
2. with the test patch and the reference fix — they must **pass in full**.

An instance failing either check is excluded, and listed in
`validation.json` with the reason. The reference fix is used for nothing
else; the agent never sees it.

### The independent re-check

A search reporting green is not taken on trust. The diff it reports is applied
with `git apply` to a clean checkout, uploaded to a *fresh* checkpoint of the
official image with the test patch, and the test files run again. A solve
counts only if that passes. This also tests the diff itself: a patch that the
search evaluated but that does not survive `git apply` would be useless as a
pull request, and is counted as a failure.

"Test files pass in full" is at least as strict as SWE-bench's own criterion
(every FAIL_TO_PASS and PASS_TO_PASS test passes), since those tests are a
subset of the files, and validation guarantees the reference fix meets it.

## Running it

```bash
python evals/swebench/run_swebench.py validate            # sandbox only, no model calls
python evals/swebench/run_swebench.py run --resume --reports
```

Needs `ARBORIST_BACKEND=contree` credentials in `.env`. Results are written
after every run, so `--resume` continues an interrupted sweep. Repository
mirrors and checkouts are cached under `.cache/`.

## Results

See [`results.md`](results.md) once a sweep has run.
