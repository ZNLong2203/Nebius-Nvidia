"""HTTP API and web UI.

One run streams as server-sent events so the tree draws itself while the search
is still going -- which is the only honest way to show a search: you watch
branches open, score, and get abandoned.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import load_settings
from .llm import NemotronClient
from .report import load_report
from .sandbox import build_backend
from .search import Arborist, RunConfig, write_report
from .tools.tavily import TavilyClient

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "ui"
WEB_DIR = ROOT / "web" / "out"

app = FastAPI(title="Arborist", version="0.1.0")


def _runs_dir() -> Path:
    return Path(load_settings().runs_dir)


def _saved_reports() -> list[Path]:
    """Finished run reports on disk, newest first."""
    directory = _runs_dir()
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


class StartRun(BaseModel):
    repo_path: str
    test_command: str = "python -m pytest -q"
    setup_command: str = ""
    image: str = "python:3.12-slim"
    backend: str | None = None
    fanout: int | None = None
    max_nodes: int | None = None
    max_depth: int | None = None
    branching: bool | None = None
    context_files: list[str] = []


class _Run:
    """One search, its event queue, and its final report."""

    def __init__(self, run_id: str, request: StartRun) -> None:
        self.id = run_id
        self.request = request
        self.events: list[dict] = []
        self.subscribers: list[queue.Queue] = []
        self.done = threading.Event()
        self.stop_requested = False
        self.result: dict[str, Any] | None = None
        self.error: str = ""
        self.started_at = time.time()
        self.agent: Arborist | None = None

    def publish(self, event: dict) -> None:
        self.events.append(event)
        for sub in list(self.subscribers):
            sub.put(event)

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        for event in self.events:  # replay so a late viewer sees the whole tree
            q.put(event)
        self.subscribers.append(q)
        return q


_RUNS: dict[str, _Run] = {}
_LOCK = threading.Lock()


def _execute(run: _Run) -> None:
    req = run.request
    settings = load_settings(
        backend=req.backend,
        fanout=req.fanout,
        max_nodes=req.max_nodes,
        max_depth=req.max_depth,
        branching=req.branching,
    )
    backend = None
    try:
        if not settings.has_llm:
            raise RuntimeError("NEBIUS_API_KEY is not set on the server")
        llm = NemotronClient(settings)
        backend = build_backend(settings)
        tavily = TavilyClient(api_key=settings.tavily_api_key) if settings.has_tavily else None
        agent = Arborist(settings, backend, llm, tavily, on_event=run.publish)
        # Published before the run starts so a stop arriving mid-setup is not
        # dropped on the floor.
        run.agent = agent
        if run.stop_requested:
            agent.cancel()
        result = agent.run(
            RunConfig(
                repo_path=req.repo_path,
                test_command=req.test_command,
                setup_command=req.setup_command,
                image=req.image,
                context_files=req.context_files,
            )
        )
        run.result = result.to_dict()
        write_report(result, _runs_dir())
    except Exception as exc:  # noqa: BLE001 - reported to the client, never crashes the server
        run.error = f"{type(exc).__name__}: {exc}"
        run.publish({"type": "error", "message": run.error, "at": time.time()})
    finally:
        if backend is not None:
            backend.close()
        run.publish({"type": "done", "at": time.time()})
        run.done.set()


@app.post("/api/runs")
def start_run(request: StartRun) -> dict:
    if not Path(request.repo_path).is_dir():
        raise HTTPException(status_code=400, detail=f"{request.repo_path} is not a directory")
    run_id = f"run-{int(time.time() * 1000):x}"
    run = _Run(run_id, request)
    with _LOCK:
        _RUNS[run_id] = run
    threading.Thread(target=_execute, args=(run,), daemon=True).start()
    return {"run_id": run_id}


@app.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: str) -> dict:
    """Stop a run.

    Closing the event stream only stops watching; the search would carry on
    spending tokens on work nobody is waiting for. This asks it to stop at its
    next boundary, which is at most one model call away.
    """
    run = _RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown run")
    run.stop_requested = True
    if run.agent is not None:
        run.agent.cancel()
    return {"run_id": run_id, "cancelling": not run.done.is_set()}


@app.get("/api/runs")
def list_runs() -> dict:
    live = [
        {
            "run_id": r.id,
            "repo": r.request.repo_path,
            "done": r.done.is_set(),
            "started_at": r.started_at,
            "solved": (r.result or {}).get("solved"),
            "recorded": False,
        }
        for r in sorted(_RUNS.values(), key=lambda r: r.started_at, reverse=True)
    ]
    seen = {row["run_id"] for row in live}
    saved = [
        {
            "run_id": path.stem,
            "repo": "",
            "done": True,
            "started_at": path.stat().st_mtime,
            "solved": None,
            "recorded": True,
        }
        for path in _saved_reports()
        if path.stem not in seen
    ]
    return {"runs": live + saved}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    run = _RUNS.get(run_id)
    if run is None:
        # A run from an earlier process is still readable from its report.
        for path in _saved_reports():
            if path.stem == run_id:
                return {"run_id": run_id, "done": True, "error": "",
                        "result": load_report(path), "events": [], "recorded": True}
        raise HTTPException(status_code=404, detail="unknown run")
    return {
        "run_id": run.id,
        "done": run.done.is_set(),
        "error": run.error,
        "result": run.result,
        "events": run.events,
    }


@app.get("/api/runs/{run_id}/events")
async def stream_events(run_id: str) -> StreamingResponse:
    run = _RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown run")

    subscription = run.subscribe()

    async def generator():
        loop = asyncio.get_running_loop()
        while True:
            try:
                event = await loop.run_in_executor(None, subscription.get, True, 30)
            except queue.Empty:
                yield ": keepalive\n\n"
                if run.done.is_set():
                    break
                continue
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("type") == "done":
                break

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/demo")
def demo_run() -> dict:
    """The run to show when the page opens.

    A deployed demo has no credentials and no repository to point at, so an
    empty tree would teach a visitor nothing. This serves a real, finished
    search instead -- clearly labelled as recorded, never presented as live.
    """
    settings = load_settings()
    if settings.demo_run:
        # A relative path is written against the working tree, but in a
        # container the reports live on a mounted volume. Fall back to the same
        # file inside runs_dir rather than silently showing nothing.
        chosen = Path(settings.demo_run)
        candidates = [chosen, _runs_dir() / chosen.name]
    else:
        # Newest-first is the wrong default on its own: the last thing written
        # is often a one-node experiment. Prefer a run that actually finished
        # green and has a tree worth looking at.
        loaded = []
        for path in _saved_reports():
            try:
                loaded.append((path, load_report(path)))
            except (OSError, ValueError):
                continue
        loaded.sort(key=lambda pair: (bool(pair[1].get("solved")), len(pair[1].get("nodes", []))), reverse=True)
        candidates = [path for path, _ in loaded]

    for path in candidates:
        try:
            return {
                "available": True,
                "source": path.name,
                "recorded_at": path.stat().st_mtime,
                "run": load_report(path),
            }
        except (OSError, ValueError):
            continue
    return {"available": False, "source": "", "recorded_at": None, "run": None}


@app.get("/api/health")
def health() -> dict:
    settings = load_settings()
    return {
        "ok": True,
        "llm_configured": settings.has_llm,
        "tavily_configured": settings.has_tavily,
        "can_run": settings.has_llm,
        "backend": settings.backend,
        "models": settings.models,
        "saved_runs": len(_saved_reports()),
    }


@app.get("/")
def index() -> FileResponse:
    """Serve the built Next.js UI, falling back to the dependency-free one.

    The polished interface needs `npm run build` in `web/`. Someone who has
    cloned the repository and only wants to see it work gets `ui/index.html`
    instead: one file, no build step, same API.
    """
    built = WEB_DIR / "index.html"
    return FileResponse(built if built.is_file() else UI_DIR / "index.html")


if (WEB_DIR / "_next").is_dir():
    # Mounted only when the export exists, so an unbuilt checkout still starts.
    app.mount("/_next", StaticFiles(directory=WEB_DIR / "_next"), name="next-assets")
