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
from arborist.search import Arborist, RunConfig, write_report
from arborist.tools.tavily import TavilyClient

ROOT = Path(__file__).resolve().parents[1]

# Model sets, so the same harness can answer "how does Nemotron compare?" with
# numbers instead of an impression. The baseline is matched by size and class on
# the same Token Factory account -- Qwen3 30B A3B against Nemotron 3 Nano 30B
# A3B, gpt-oss 120B against Nemotron 3 Super 120B -- so what differs is the
# model, not the platform, the harness, the prompts or the case.
MODEL_SETS = {
    "nemotron": {
        "nano": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
        "super": "nvidia/nemotron-3-super-120b-a12b",
        "ultra": "nvidia/Nemotron-3-Ultra-550b-a55b",
    },
    "matched-baseline": {
        "nano": "Qwen/Qwen3-30B-A3B-Instruct-2507",
        "super": "openai/gpt-oss-120b",
        "ultra": "Qwen/Qwen3-235B-A22B-Instruct-2507",
    },
}
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
    "outside-knowledge": {
        "path": ROOT / "evals" / "cases" / "outside-knowledge",
        "test": "python -m pytest -q",
        "setup": "pip install -q -r requirements.txt",
        "bugs": 2,
    },
}


@dataclass
class Row:
    case: str
    models: str
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


def run_case(
    name: str,
    spec: dict,
    *,
    branching: bool,
    backend_name: str,
    fanout: int,
    max_nodes: int,
    model_set: str = "nemotron",
    reports_dir: Path | None = None,
) -> Row:
    settings = load_settings(
        backend=backend_name,
        branching=branching,
        fanout=fanout if branching else 1,
        max_nodes=max_nodes,
        models=dict(MODEL_SETS[model_set]),
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

    # Keep the tree. A table says which mode did better; only the tree says why
    # -- and "the linear agent ran out of frontier" is not visible in a number.
    if reports_dir is not None:
        mode = f"{model_set}-{'branching' if branching else 'linear'}"
        path = write_report(result, reports_dir)
        path.rename(path.with_name(f"{name}-{mode}.json"))
        patch = path.with_suffix(".patch")
        if patch.exists():
            patch.rename(patch.with_name(f"{name}-{mode}.patch"))

    tiers = result.usage.get("by_tier", {})
    base, final = result.baseline, result.final
    return Row(
        case=name,
        models=model_set,
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
        "| case | models | branching | solved | baseline | final | patches | sandbox runs | setup runs "
        "| invalid | wall (s) | nano tok | super tok | ultra tok |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    )
    body = "".join(
        f"| {r.case} | {r.models} | {'on' if r.branching else 'off'} | {'yes' if r.solved else 'no'} "
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
    parser.add_argument(
        "--model-set",
        choices=sorted(MODEL_SETS),
        default="nemotron",
        help="which models fill the three tiers; 'matched-baseline' is the size-matched comparison",
    )
    parser.add_argument("--out", default="evals/results.md")
    parser.add_argument(
        "--reports", default="evals/reports", help="where to keep each run's full tree"
    )
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
            print(f"-> {name} [{args.model_set}] [{label}]", flush=True)
            row = run_case(
                name,
                spec,
                branching=branching,
                backend_name=settings.backend,
                fanout=args.fanout,
                max_nodes=args.max_nodes,
                model_set=args.model_set,
                reports_dir=Path(args.reports) if args.reports else None,
            )
            rows.append(row)
            print(f"   solved={row.solved} sandbox_runs={row.sandbox_runs} wall={row.wall_seconds}s", flush=True)

    table = markdown(rows)
    print("\n" + table)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        f"# Eval results\n\nbackend: `{settings.backend}` · fanout: {args.fanout} · "
        f"node cap: {args.max_nodes} · models: `{args.model_set}` "
        f"({', '.join(MODEL_SETS[args.model_set].values())})\n\n{table}\n",
        encoding="utf-8",
    )
    Path(out.with_suffix(".json")).write_text(
        json.dumps([asdict(r) for r in rows], indent=2), encoding="utf-8"
    )
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
