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
| `sandboxes-broken-invoice.json` | The first search executed on real Nebius Sandboxes: `examples/broken-invoice` solved at depth 3, six patches, eight forked executions, 18 of 182 seconds spent in the sandbox | 21 Sep 2026 |

To open one locally: `arborist report evals/evidence/<file>` prints the pull
request body it would produce, and `arborist serve` opens on the demo entry
when `runs/` is empty.
