# HTTP API

Served by [`arborist/server.py`](../arborist/server.py). Start it with
`arborist serve` (default `http://127.0.0.1:8000`).

A run executes on its own thread. Events are fanned out to every subscriber and
**replayed from the beginning** for late ones, so a browser that connects
mid-search still draws the whole tree.

---

## `POST /api/runs`

Start a search. Returns immediately.

```json
{
  "repo_path": "examples/broken-invoice",
  "test_command": "python -m pytest -q",
  "setup_command": "pip install -q -r requirements.txt",
  "image": "python:3.12-slim",
  "backend": "contree",
  "fanout": 4,
  "max_nodes": 24,
  "max_depth": 4,
  "branching": true,
  "context_files": ["src/billing/*.py"]
}
```

Only `repo_path` is required; everything else falls back to the environment
defaults in [`config.py`](../arborist/config.py).

```json
{ "run_id": "run-19a3f0c81b2" }
```

`400` if `repo_path` is not a directory.

## `GET /api/runs`

```json
{ "runs": [ { "run_id": "…", "repo": "…", "done": true,
              "started_at": 1758273661.2, "solved": true } ] }
```

Newest first. In-memory only — restarting the server clears it. Persisted reports
live in `runs/`.

## `GET /api/runs/{run_id}`

The full state: every event so far, and the report once finished.

```json
{
  "run_id": "run-19a3f0c81b2",
  "done": true,
  "error": "",
  "result": { "solved": true, "winner_id": "n-c2ea3ea5", "diff": "…",
              "baseline": {…}, "final": {…}, "nodes": [ … ],
              "stats": {…}, "usage": {…} },
  "events": [ … ]
}
```

`404` for an unknown id. `result` is `null` while running or if the run failed;
`error` carries the reason.

A run from an earlier process is still readable: if the id is not in memory, the
matching report in `ARBORIST_RUNS_DIR` is served with `"recorded": true` and an
empty `events` list.

## `GET /api/runs/{run_id}/events`

Server-sent events. Replays history, then streams live, and closes after `done`.
A `: keepalive` comment is emitted every 30 seconds of silence.

```
data: {"type":"run_started","at":1758273661.2,"run_id":"…","repo":"…"}

data: {"type":"checkpoint","stage":"setup","checkpoint":"9f2c…","seconds":41.3}

data: {"type":"node","node":{"id":"n-40781331","status":"improved","score":0.67,…}}

data: {"type":"done","at":1758273712.9}
```

Event types are documented in [run-flow.md](run-flow.md#events). Two consumer
notes:

- **`node` is an upsert.** The same id is emitted again when the node becomes the
  next fork point (`expanded: true`).
- **`done` always arrives**, including when the run failed, so a client can close
  its stream unconditionally.

## `GET /api/demo`

The run to show when the page opens.

```json
{ "available": true, "source": "run-db0cfb8b.json",
  "recorded_at": 1789824536.9, "run": { … } }
```

A deployed demo has no credentials and no repository to point at, so an empty
tree would teach a visitor nothing. This serves a real, finished search instead,
which the UI labels as **recorded** — never presented as live.

Which run: `ARBORIST_DEMO_RUN` if set, otherwise the best report in
`ARBORIST_RUNS_DIR`, preferring one that went green and has the largest tree. The
newest file is a poor default on its own; it is often a one-node experiment. A
corrupt report is skipped rather than taking the endpoint down.

`{"available": false, …}` when nothing has been recorded.

## `GET /api/health`

```json
{ "ok": true, "llm_configured": true, "tavily_configured": false,
  "can_run": true, "saved_runs": 3, "backend": "contree",
  "models": { "nano": "nvidia/nemotron-3-nano-30b-a3b", … } }
```

Reports whether keys are present. It never reveals them. `can_run` is what the UI
uses to disable the Run button, with a banner explaining why, so a demo deployed
without a key is still fully explorable instead of merely broken.

## `GET /`

Serves [`ui/index.html`](../ui/index.html) — one file, no build step, no CDN.

---

## The UI

The page is a client for the event stream above and holds no logic of its own.

- **Tree** — depth on the x-axis, so the search reads left to right. Nodes are
  laid out with a tidy-tree pass: leaves take sequential rows, a parent centres on
  its children. Status is carried by a colour bar *and* an icon *and* a label,
  never colour alone.
- **Detail panel** — click any node for its hypothesis, rationale, patch,
  fixed/broken test names, and test output.
- **Stat tiles** — baseline, best branch, branches evaluated, sandbox runs, setup
  time saved by forking, Nemotron tokens by tier.
- **Table view** — the same data as rows, for keyboard and screen-reader use.
- **Recorded-run banner** — when the page is showing a finished run from disk
  rather than a live search, it says so.
- **Theme** — follows the OS, with a manual override.

## Deploying

```bash
uvicorn arborist.server:app --host 0.0.0.0 --port 8000
```

Two things to know before exposing it:

- `repo_path` is a **server-side path**. A public deployment should restrict it to
  a known set of demo repositories.
- A run costs tokens. Put the demo behind whatever rate limiting the host offers.

Nebius Serverless Endpoints is a natural fit and keeps the whole stack on one
platform.
