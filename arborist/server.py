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
from pydantic import BaseModel

from .config import load_settings
from .llm import NemotronClient
from .sandbox import build_backend
from .search import Arborist, RunConfig, write_report
from .tools.tavily import TavilyClient

UI_DIR = Path(__file__).resolve().parents[1] / "ui"
RUNS_DIR = Path("runs")

app = FastAPI(title="Arborist", version="0.1.0")


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
        self.result: dict[str, Any] | None = None
        self.error: str = ""
        self.started_at = time.time()

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
        write_report(result, RUNS_DIR)
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


@app.get("/api/runs")
def list_runs() -> dict:
    return {
        "runs": [
            {
                "run_id": r.id,
                "repo": r.request.repo_path,
                "done": r.done.is_set(),
                "started_at": r.started_at,
                "solved": (r.result or {}).get("solved"),
            }
            for r in sorted(_RUNS.values(), key=lambda r: r.started_at, reverse=True)
        ]
    }


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    run = _RUNS.get(run_id)
    if run is None:
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


@app.get("/api/health")
def health() -> dict:
    settings = load_settings()
    return {
        "ok": True,
        "llm_configured": settings.has_llm,
        "tavily_configured": settings.has_tavily,
        "backend": settings.backend,
        "models": settings.models,
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(UI_DIR / "index.html")
