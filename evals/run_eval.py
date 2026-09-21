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
import faulthandler
import json
import statistics
import subprocess
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
    "masked-faults": {
        "path": ROOT / "evals" / "cases" / "masked-faults",
        "test": "python -m pytest -q",
        "setup": "pip install -q -r requirements.txt",
        "bugs": 3,
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
    run: int
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
    code: str = ""
    """The commit this run executed, so a resumed sweep that spans a change says so."""


def run_case(
    name: str,
    spec: dict,
    *,
    branching: bool,
    backend_name: str,
    fanout: int,
    max_nodes: int,
    model_set: str = "nemotron",
    repetition: int = 1,
    reports_dir: Path | None = None,
) -> Row:
    # Both arms get the same patch budget.
    #
    # The linear arm evaluates one hypothesis per expansion, so a shared
    # max_depth would cap it at `max_depth` patches however large max_nodes is
    # -- four against the branching arm's twelve, which is not the same budget
    # and was quietly deciding the comparison. Depth is therefore only a
    # constraint on the arm that fans out.
    settings = load_settings(
        backend=backend_name,
        branching=branching,
        fanout=fanout if branching else 1,
        max_nodes=max_nodes,
        max_depth=None if branching else max_nodes,
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
        # The backend is part of the name: a Sandboxes sweep used to overwrite
        # the local sweep's trees, which share every other part of it.
        mode = f"{backend_name}-{model_set}-{'branching' if branching else 'linear'}-{repetition}"
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
        run=repetition,
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
        code=code_version(),
    )


def markdown(rows: list[Row]) -> str:
    head = (
        "| case | models | branching | run | solved | baseline | final | patches | sandbox runs | setup runs "
        "| invalid | wall (s) | nano tok | super tok | ultra tok |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    )
    body = "".join(
        f"| {r.case} | {r.models} | {'on' if r.branching else 'off'} | {r.run} | {'yes' if r.solved else 'no'} "
        f"| {r.baseline_passing} | {r.final_passing} | {r.patches} | {r.sandbox_runs} | {r.setup_runs} "
        f"| {r.invalid_patches} | {r.wall_seconds} | {r.tokens_nano:,} | {r.tokens_super:,} "
        f"| {r.tokens_ultra:,} |\n"
        for r in rows
    )
    return head + body


SLEEP_TOLERANCE = 30.0
"""Seconds a run may lose to the machine sleeping before it stops counting."""


class Awake:
    """How long the machine slept since this was created.

    On macOS time.monotonic() is mach_absolute_time, which stops while the
    machine sleeps; time.time() does not. The gap is the sleep. A run a
    closed lid interrupted is not a measurement: its wall time includes the
    nap, and the connections the nap dropped can change what the search did.
    """

    def __init__(self) -> None:
        self._wall, self._awake = time.time(), time.monotonic()

    def slept(self) -> float:
        return (time.time() - self._wall) - (time.monotonic() - self._awake)


def watch_for_hangs() -> None:
    """Make a stuck sweep say where it is stuck.

    `kill -USR1 <pid>` prints every thread's stack, and a run past
    --run-limit prints them and exits -- results so far are already on disk,
    so `--resume` picks up from the run that hung. The limit is measured on
    the monotonic clock, so it does not count time the machine spent asleep;
    `Awake` catches that case instead.
    """
    import signal

    faulthandler.enable()
    if hasattr(signal, "SIGUSR1"):
        faulthandler.register(signal.SIGUSR1, all_threads=True)


def code_version() -> str:
    """The commit the numbers came from, marked when the tree had local changes.

    A table without it cannot be traced back to the code that produced it, and
    this project changes the search between sweeps.
    """
    try:
        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return f"{head}+local changes" if dirty else head


def _codes(rows: list[Row]) -> str:
    """The commit(s) behind a table: one, or every one when a sweep spans several."""
    codes = sorted({r.code or "unrecorded" for r in rows})
    if len(codes) == 1:
        return f"`{codes[0]}`"
    return "**mixed** (" + ", ".join(f"`{c}`" for c in codes) + " -- see `code` per run in the JSON)"


def write_results(rows: list[Row], out: Path, settings, args) -> None:
    """Persist after every run, not at the end.

    A sweep is hours long and a killed process used to lose all of it. Writing
    as it goes also means `--resume` has something to read.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        f"# Eval results\n\ncode: {_codes(rows)} · "
        f"backend: `{settings.backend}` · fanout: {args.fanout} · "
        f"node cap: {args.max_nodes} · models: `{args.model_set}` "
        f"({', '.join(MODEL_SETS[args.model_set].values())}) · "
        f"{args.repeat} run(s) per configuration\n\n"
        f"## Summary\n\n{summarise(rows)}\n## Every run\n\n{markdown(rows)}\n",
        encoding="utf-8",
    )
    out.with_suffix(".json").write_text(
        json.dumps([asdict(r) for r in rows], indent=2), encoding="utf-8"
    )


def load_previous(out: Path) -> list[Row]:
    """Rows from an earlier, interrupted sweep."""
    path = out.with_suffix(".json")
    if not path.is_file():
        return []
    try:
        return [Row(**r) for r in json.loads(path.read_text())]
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return []


def summarise(rows: list[Row]) -> str:
    """Per configuration, across repetitions.

    A single run of an agent is close to meaningless: the same case and settings
    solve on one attempt and stall on the next. The median is reported rather
    than the mean because a run that stalls skews an average and the interesting
    figure is the typical outcome; the full spread is in the per-run table above.
    """
    groups: dict[tuple, list[Row]] = {}
    for r in rows:
        groups.setdefault((r.case, r.models, r.branching), []).append(r)

    header = (
        "| case | models | branching | solved | patches (median) | wall s (median) | "
        "tokens (median) | wall range |"
    )
    out = [header, "|---|---|---|---|---|---|---|---|"]
    for (case, models, branching), rs in groups.items():
        solved = sum(1 for r in rs if r.solved)
        walls = sorted(r.wall_seconds for r in rs)
        tokens = [r.tokens_nano + r.tokens_super + r.tokens_ultra for r in rs]
        out.append(
            f"| {case} | {models} | {'on' if branching else 'off'} | **{solved}/{len(rs)}** "
            f"| {statistics.median(r.patches for r in rs):.0f} "
            f"| {statistics.median(walls):.0f} "
            f"| {statistics.median(tokens):,.0f} "
            f"| {walls[0]:.0f}–{walls[-1]:.0f} |"
        )
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default="all", help="comma-separated case names, or 'all'")
    parser.add_argument("--backend", default=None, help="contree | local")
    parser.add_argument("--fanout", type=int, default=4)
    parser.add_argument("--max-nodes", type=int, default=12)
    parser.add_argument("--only", choices=["both", "on", "off"], default="both")
    parser.add_argument(
        "--repeat", type=int, default=1, help="runs per configuration; one run proves nothing"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="skip configurations already present in the results file",
    )
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
    parser.add_argument(
        "--run-limit",
        type=float,
        default=45,
        help="minutes one run may take before the sweep dumps every thread's stack and exits; "
        "rerun with --resume to continue",
    )
    args = parser.parse_args()
    watch_for_hangs()

    settings = load_settings(backend=args.backend)
    if not settings.has_llm:
        print("NEBIUS_API_KEY is not set.", file=sys.stderr)
        return 2

    names = list(CASES) if args.cases == "all" else [c.strip() for c in args.cases.split(",")]
    modes = {"both": [True, False], "on": [True], "off": [False]}[args.only]

    out = Path(args.out)
    rows: list[Row] = load_previous(out) if args.resume else []
    done = {(r.case, r.models, r.branching, r.run) for r in rows}
    if rows:
        print(f"resuming: {len(rows)} run(s) already recorded", flush=True)

    for name in names:
        spec = CASES.get(name)
        if spec is None:
            print(f"unknown case: {name}", file=sys.stderr)
            return 2
        for branching in modes:
          for repetition in range(1, args.repeat + 1):
            if (name, args.model_set, branching, repetition) in done:
                continue
            label = "branching on " if branching else "branching off"
            print(f"-> {name} [{args.model_set}] [{label}] run {repetition}/{args.repeat}", flush=True)
            row = None
            for _attempt in range(3):
                clock = Awake()
                faulthandler.dump_traceback_later(args.run_limit * 60, exit=True)
                try:
                    candidate = run_case(
                        name,
                        spec,
                        branching=branching,
                        backend_name=settings.backend,
                        fanout=args.fanout,
                        max_nodes=args.max_nodes,
                        model_set=args.model_set,
                        repetition=repetition,
                        reports_dir=Path(args.reports) if args.reports else None,
                    )
                finally:
                    faulthandler.cancel_dump_traceback_later()
                slept = clock.slept()
                if slept <= SLEEP_TOLERANCE:
                    row = candidate
                    break
                print(f"   the machine slept {slept:.0f}s during this run -- not a measurement, repeating", flush=True)
            if row is None:
                print("   still disturbed after three attempts; left for --resume", flush=True)
                continue
            rows.append(row)
            write_results(rows, out, settings, args)
            print(f"   solved={row.solved} sandbox_runs={row.sandbox_runs} wall={row.wall_seconds}s", flush=True)

    if not rows:
        print("nothing to run", file=sys.stderr)
        return 1

    write_results(rows, out, settings, args)
    print("\n" + summarise(rows) + "\n" + markdown(rows))
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
