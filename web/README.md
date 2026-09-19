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

## Layout

The panel takes a third of the width above `lg`, because it holds code and 400px
of it wraps badly. Prose inside is capped at 68 characters separately, so a wide
screen buys the diff room without turning paragraphs into a single long line.

Below `lg` the two stack. Both halves are `min-h-0` inside an `overflow-hidden`
parent — without that the panel grows to its content height and pushes straight
through the spend strip.

## Structure

| Path | What it does |
|---|---|
| `app/page.tsx` | Assembles the four regions: command bar, tree, inspector, spend |
| `lib/useRun.ts` | Boot, the SSE subscription, and the event reducer |
| `lib/tree.ts` | Tidy-tree layout, ancestry, status vocabulary |
| `lib/viewport.ts` | Pan, zoom, auto-fit, and the drag-versus-click threshold |
| `lib/replay.ts` | Reconstructing the order branches were created in |
| `components/ReplayBar.tsx` | Transport, per-branch scrub track, speed |
| `lib/api.ts` | The five endpoints and the event stream |
| `components/SearchTree.tsx` | The tree: SVG, enter animations, hover ancestry |
| `components/Inspector.tsx` | One node in full — patch, tests fixed, tests broken |
| `components/Code.tsx` | Highlighted diffs, files and pytest output, with copy buttons |
| `lib/highlight.ts` | The highlighter: ~150 lines, no dependency |
| `components/SpendStrip.tsx` | Tokens per tier, branches, sandbox runs, time saved |
| `components/ActivityFeed.tsx` | What the agent is doing, with the tier that did it |

## Moving around the tree

A scroll container was fine while trees were four nodes wide. A search that goes
deep stops fitting, and the shape is the point — so the canvas is a real
viewport:

| Gesture | Does |
|---|---|
| drag | pan |
| scroll / two-finger | pan |
| ⌘ or ctrl + scroll, trackpad pinch | zoom at the pointer |
| arrow keys (shift for bigger steps) | pan |
| `+` / `-` | zoom |
| `0`, or the ⤢ button | fit everything on screen |

It **auto-fits until the first deliberate interaction**, so a run that grows
while you watch stays entirely visible without anyone touching it — and stops
the moment someone takes control. The fit button hands control back.

Below 45% zoom the cards drop their text and become their shape: status colour
and how much of the suite passes. Zoomed out you are reading the search, not the
patches, and unreadable 5px type is noise. Strokes use `non-scaling-stroke`, so
borders and edges stay crisp at any scale.

A drag that travels more than four pixels suppresses the click, so panning
across a card never selects it by accident.

## Replaying a finished run

A recorded run arrives as a finished tree, which shows the answer but not the
search. The replay bar reconstructs the order the branches were created in and
plays them back, so the thing this project is actually about is visible without
waiting several minutes for a live run — which is what a demo video needs.

The order is breadth-first by depth, because that is the order the search
expands in: every sibling of a level is evaluated before the winner of that
level is forked. The track is not a progress bar — each tick is one branch,
coloured by how it turned out, so a row of blue with two red in it already tells
you what happened before you press anything.

It only appears for a finished run. A live one is already happening.

## Reading a patch

Diffs are syntax-highlighted by a **150-line tokeniser in `lib/highlight.ts`**,
not a grammar engine. A full highlighter is hundreds of kilobytes for something
that only ever renders short patches; this covers Python properly — including
docstrings that span lines, which every patch here has — and degrades sensibly
for anything C-like.

The lines carry a red or green tint for their side of the change *and* keep
their token colours, because solid red and green tells you where the change is
and nothing about what it says. Token colours are stepped per theme and checked
against the code surface: the thinnest is 4.56:1 in light mode and 4.59:1 in
dark.

## Linkable runs

Starting a search puts `?run=<id>` in the URL, and selecting a branch adds
`?node=<id>`. Opening that link attaches to the run — live if it is still going,
replayed from its report if it finished — with that branch already open. So a
link can point at one specific rejected patch and the tests it broke.
