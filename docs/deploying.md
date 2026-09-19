# Deploying the demo

The agent executes nothing locally — every command it runs happens inside Nebius
Sandboxes. The deployed service therefore only serves HTTP and calls Token
Factory, which makes it small and stateless apart from one volume of recorded
runs.

## What a visitor should see

Someone who opens the URL has no API key and no repository to point at. An empty
tree teaches them nothing, so the page opens on a **real, finished run**, clearly
labelled as recorded:

```
● Recorded run — a real search that already finished. Every branch below is what
  the agent actually explored.            Press Run to start a live one.
```

Record it before deploying:

```bash
arborist fix examples/broken-invoice \
  --setup "pip install -q -r requirements.txt" -k 4
# -> runs/run-xxxxxxxx.json
```

Ship that file with the image or mount it, and point at it explicitly so a later
run cannot displace it:

```
ARBORIST_DEMO_RUN=/data/runs/run-xxxxxxxx.json
```

With no `ARBORIST_DEMO_RUN`, the server picks the best saved report it can find —
preferring one that went green and has the largest tree, since the newest file is
often a one-node experiment.

## Docker

```bash
docker build -t arborist .
docker run --rm -p 8000:8000 \
  -e NEBIUS_API_KEY=… \
  -e TAVILY_API_KEY=… \
  -v "$PWD/runs:/data/runs" \
  arborist
```

Without `NEBIUS_API_KEY` the service still starts and still replays recorded
runs; the Run button is disabled and says why. That is the right behaviour for a
public demo where live runs would cost tokens.

## Nebius Serverless Endpoints

Keeps the whole stack on one platform, which is worth a line in the write-up.
Deploy the image above, set `NEBIUS_API_KEY` (and `TAVILY_API_KEY`) as secrets,
and expose port 8000. The health check at `/api/health` is already wired.

## Before you expose it publicly

| Concern | What to do |
|---|---|
| `repo_path` is a **server-side path** | Restrict it to a known set of demo repositories, or leave live runs disabled and serve only recorded ones |
| A live run costs tokens | Rate limit, or run the public demo with no `NEBIUS_API_KEY` at all |
| Sandboxes quota | `ARBORIST_MAX_NODES` caps executions per run; lower it for a public instance |

The safest public configuration is **no API key**: recorded runs replay in full,
the tree is fully explorable, and nothing can be spent.
