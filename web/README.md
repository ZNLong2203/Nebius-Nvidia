# Arborist — web interface

A Next.js app that watches a search happen. It holds no logic of its own: every
number on screen comes from the run report, and it consumes the same event
stream the CLI renders to a terminal.

```bash
npm install
npm run dev     # http://localhost:3000, proxies /api to the service on :8000
npm run build   # static export into out/, which the FastAPI service serves
```

Run the backend alongside it:

```bash
cd .. && arborist serve      # http://127.0.0.1:8000
```

## Why a static export

`output: "export"` produces plain files with no Node runtime. FastAPI serves
them itself, so there is **one process, one URL and no CORS** — and an unbuilt
checkout still works, because the service falls back to the dependency-free
`ui/index.html`.

## What the interface is trying to say

The hard part of this project is not a number, it is a shape: *a search over
states*. Three decisions follow from that.

**Depth reads left to right.** Moving right means a patch was applied on top of
the one before it. Cards stacked vertically are rival theories of the same
failure, tested from the identical checkpoint — which is the only reason their
scores are comparable. Hovering a card lights its ancestry, so "what this state
was built on" is one gesture away.

**Green is reserved.** Progress is blue, a dead end is red, a patch that never
applied is grey and dashed. Only the branch that got the whole suite green is
green, so the one node that matters is the one node that stands out. Status is
always an icon *and* a word as well as a colour.

**The cost argument is a picture.** The spend strip fills per tier as the run
goes: Nano wide and cheap, Super focused, Ultra usually empty. That is the
architecture's whole claim, visible without reading a table.

## Structure

| Path | What it does |
|---|---|
| `app/page.tsx` | Assembles the four regions: command bar, tree, inspector, spend |
| `lib/useRun.ts` | Boot, the SSE subscription, and the event reducer |
| `lib/tree.ts` | Tidy-tree layout, ancestry, status vocabulary |
| `lib/api.ts` | The five endpoints and the event stream |
| `components/SearchTree.tsx` | The tree: SVG, enter animations, hover ancestry |
| `components/Inspector.tsx` | One node in full — patch, tests fixed, tests broken |
| `components/SpendStrip.tsx` | Tokens per tier, branches, sandbox runs, time saved |
| `components/ActivityFeed.tsx` | What the agent is doing, with the tier that did it |

## Linkable runs

Starting a search puts `?run=<id>` in the URL, and opening that link attaches to
the run — live if it is still going, replayed from its report if it finished.
