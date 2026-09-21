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
| `sandboxes-first-run.json` | The first search ever executed on real Sandboxes, before rewrite minimisation existed — its diff shows the quote-restyling noise that motivated it | 21 Sep 2026 |

**How the demo was chosen.** The three `demo-*` files are every recording made
for it, not a selection from more. All three solved. The one the page opens on
was picked because it shows the most of the idea at once — branches that
regressed and were abandoned, and depth — and all three are here to compare.

To open one locally: `arborist report evals/evidence/<file>` prints the pull
request body it would produce, and `arborist serve` opens on the demo entry
when `runs/` is empty.
