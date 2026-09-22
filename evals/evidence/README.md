# Evidence

Run reports that back specific claims in the README, checked in so anyone can
inspect them without running anything. Each file is the complete JSON report a
run writes to `runs/`: every node, its hypothesis, its patch, which tests it
fixed and broke, and the token and sandbox accounting.

They are also what the public demo shows. `manifest.json` lists them; the entry
named by `demo` is what the page opens on, and every entry is reachable at
`?run=<run_id>`.

| File | What it shows | Recorded |
|---|---|---|
| `demo-broken-invoice.json` | **The demo.** `examples/broken-invoice` on Nebius Sandboxes, fan-out 4, tests protected: rival fixes forked from one checkpoint, two branches that broke passing tests abandoned, green at depth 2. 207 s, of which 15 s in the sandbox. The diff is the three real fixes and nothing else | 21 Sep 2026 |
| `demo-broken-invoice-alt-1.json` | The same configuration recorded again: three patches refused before they reached the sandbox, green at depth 3 | 21 Sep 2026 |
| `demo-broken-invoice-alt-2.json` | And a third time: one patch fixed all three bugs, green at depth 1 | 21 Sep 2026 |
| `masked-faults-branching.json` | The case built to need a search, solved by branching: rival repairs on one checkpoint, setup run once. From the final measurement (commit `7b11e3d`) | 21 Sep 2026 |
| `masked-faults-linear.json` | The same case, linear baseline, same budget: twelve patches, setup run eleven times, not solved | 21 Sep 2026 |
| `tavily-outside-knowledge.json` | A runtime Tavily call: diagnosis attributes the failure to Pydantic v2, looks up the migration, and the next patch solves it | 21 Sep 2026 |
| `tavily-swebench-pytest-7373.json` | A Tavily call during a **real** repository repair — SWE-bench Lite `pytest-7373`, resolved and independently re-verified | 21 Sep 2026 |
| `sandboxes-first-run.json` | The first search ever executed on real Sandboxes, before rewrite minimisation existed — its diff shows the quote-restyling noise that motivated it | 21 Sep 2026 |

**How the demo was chosen.** The three `demo-*` files are every recording made
for it, not a selection from more. All three solved. The one the page opens on
was picked because it shows the most of the idea at once — branches that
regressed and were abandoned, and depth — and all three are here to compare.

To open one locally: `arborist report evals/evidence/<file>` prints the pull
request body it would produce, and `arborist serve` opens on the demo entry
when `runs/` is empty.
