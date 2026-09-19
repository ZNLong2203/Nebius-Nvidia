#!/usr/bin/env python
"""Benchmark: what does branching actually buy?

Runs every case twice with an identical budget -- once with checkpoint forking
on, once with it off -- and prints the two columns side by side. The off column
is a faithful linear agent: one hypothesis at a time, and because it cannot fork
a warm checkpoint it re-runs the setup command on every attempt, which is what a
container-per-attempt agent really does.

    python evals/run_eval.py --cases all
    python evals/run_eval.py --cases broken-invoice --backend local

Requires NEBIUS_API_KEY. `--backend local` skips Nebius Sandboxes and uses
directory snapshots instead, which keeps the agent logic identical but measures
nothing about the sandbox.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arborist.config import load_settings
from arborist.llm import NemotronClient
from arborist.sandbox import build_backend
from arborist.search import Arborist, RunConfig
from arborist.tools.tavily import TavilyClient

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "broken-invoice": {
        "path": ROOT / "examples" / "broken-invoice",
        "test": "python -m pytest -q",
        "setup": "pip install -q -r requirements.txt",
        "bugs": 3,
    },
    "regression-trap": {
        "path": ROOT / "evals" / "cases" / "regression-trap",
        "test": "python -m pytest -q",
        "setup": "pip install -q pytest",
        "bugs": 2,
    },
}


@dataclass
class Row:
    case: str
    branching: bool
    solved: bool
    baseline_passing: str
    final_passing: str
    patches: int
    sandbox_runs: int
    setup_runs: int
    invalid_patches: int
    wall_seconds: float
    tokens_nano: int
    tokens_super: int
    tokens_ultra: int
    error: str = ""


def run_case(name: str, spec: dict, *, branching: bool, backend_name: str, fanout: int, max_nodes: int) -> Row:
    settings = load_settings(
        backend=backend_name, branching=branching, fanout=fanout if branching else 1, max_nodes=max_nodes
    )
    llm = NemotronClient(settings)
    backend = build_backend(settings)
    tavily = TavilyClient(api_key=settings.tavily_api_key) if settings.has_tavily else None
    agent = Arborist(settings, backend, llm, tavily)

    started = time.time()
    try:
        result = agent.run(
            RunConfig(
                repo_path=str(spec["path"]),
                test_command=spec["test"],
                setup_command=spec["setup"],
            )
        )
    finally:
        backend.close()

    tiers = result.usage.get("by_tier", {})
    base, final = result.baseline, result.final
    return Row(
        case=name,
        branching=branching,
        solved=result.solved,
        baseline_passing=f"{base.passed}/{base.total}" if base else "-",
        final_passing=f"{final.passed}/{final.total}" if final else "-",
        patches=result.stats["patches_evaluated"],
        sandbox_runs=result.stats["sandbox_executions"],
        setup_runs=result.stats["setup_runs"],
        invalid_patches=result.stats["invalid_patches"],
        wall_seconds=round(time.time() - started, 1),
        tokens_nano=tiers.get("nano", {}).get("total_tokens", 0),
        tokens_super=tiers.get("super", {}).get("total_tokens", 0),
        tokens_ultra=tiers.get("ultra", {}).get("total_tokens", 0),
        error=result.error,
    )


def markdown(rows: list[Row]) -> str:
    head = (
        "| case | branching | solved | baseline | final | patches | sandbox runs | setup runs "
        "| invalid | wall (s) | nano tok | super tok | ultra tok |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    )
    body = "".join(
        f"| {r.case} | {'on' if r.branching else 'off'} | {'yes' if r.solved else 'no'} "
        f"| {r.baseline_passing} | {r.final_passing} | {r.patches} | {r.sandbox_runs} | {r.setup_runs} "
        f"| {r.invalid_patches} | {r.wall_seconds} | {r.tokens_nano:,} | {r.tokens_super:,} "
        f"| {r.tokens_ultra:,} |\n"
        for r in rows
    )
    return head + body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default="all", help="comma-separated case names, or 'all'")
    parser.add_argument("--backend", default=None, help="contree | local")
    parser.add_argument("--fanout", type=int, default=4)
    parser.add_argument("--max-nodes", type=int, default=12)
    parser.add_argument("--only", choices=["both", "on", "off"], default="both")
    parser.add_argument("--out", default="evals/results.md")
    args = parser.parse_args()

    settings = load_settings(backend=args.backend)
    if not settings.has_llm:
        print("NEBIUS_API_KEY is not set.", file=sys.stderr)
        return 2

    names = list(CASES) if args.cases == "all" else [c.strip() for c in args.cases.split(",")]
    modes = {"both": [True, False], "on": [True], "off": [False]}[args.only]

    rows: list[Row] = []
    for name in names:
        spec = CASES.get(name)
        if spec is None:
            print(f"unknown case: {name}", file=sys.stderr)
            return 2
        for branching in modes:
            label = "branching on " if branching else "branching off"
            print(f"-> {name} [{label}]", flush=True)
            row = run_case(
                name,
                spec,
                branching=branching,
                backend_name=settings.backend,
                fanout=args.fanout,
                max_nodes=args.max_nodes,
            )
            rows.append(row)
            print(f"   solved={row.solved} sandbox_runs={row.sandbox_runs} wall={row.wall_seconds}s", flush=True)

    table = markdown(rows)
    print("\n" + table)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        f"# Eval results\n\nbackend: `{settings.backend}` · fanout: {args.fanout} · "
        f"node cap: {args.max_nodes}\n\n{table}\n",
        encoding="utf-8",
    )
    Path(out.with_suffix(".json")).write_text(
        json.dumps([asdict(r) for r in rows], indent=2), encoding="utf-8"
    )
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
