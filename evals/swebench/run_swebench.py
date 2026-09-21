"""SWE-bench Lite on Nebius Sandboxes, inside the benchmark's own evaluation images.

What this measures, precisely -- read it before quoting a number:

* **Test-driven repair, not the leaderboard setting.** The agent is given the
  issue text *and* the failing tests: each instance's test patch is applied
  before the search starts. The SWE-bench leaderboard withholds those tests, so
  nothing here is comparable to it.
* **The tests are protected.** No patch may edit a file the test patch touches;
  such a patch is refused before it reaches the sandbox (``--protect``).
* **Success is SWE-bench's own criterion.** Every FAIL_TO_PASS and PASS_TO_PASS
  test must pass. The command selects exactly those tests; others in the same
  files -- ones SWE-bench itself does not list, typically because they fail in
  its environment too -- are not run, so the agent is never asked to fix what
  the benchmark ignores.
* **Instances are validated before any model is called.** In the sandbox, the
  listed tests must fail without the fix and all pass with the reference fix.
  An instance that does not is excluded and listed with the reason, so an
  environment problem is never scored as an agent failure.
* **Success is re-checked independently.** The diff Arborist reports is applied
  with ``git apply`` to a clean checkout, run again on a fresh checkpoint of the
  official image, and must pass. A solve whose diff does not apply, or does not
  reproduce, is not counted.

The environment comes prebuilt in each image, so there is no setup step and
the setup-reuse argument does not apply here. What is compared is the search.

Usage::

    python evals/swebench/run_swebench.py validate
    python evals/swebench/run_swebench.py run --resume
"""

from __future__ import annotations

import argparse
import faulthandler
import json
import shlex
import shutil
import signal
import statistics
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from arborist.config import load_settings
from arborist.llm import NemotronClient
from arborist.repo import load_repo, parse_junit, parse_pytest_text
from arborist.sandbox import ContreeBackend
from arborist.search import JUNIT_PATH, Arborist, RunConfig
from arborist.tools.tavily import TavilyClient

CACHE = HERE / ".cache"
DATASET = "princeton-nlp/SWE-bench_Lite"

# Chosen for small codebases and fast, offline-friendly suites -- before any
# instance was run, and every Lite instance from each is included.
REPOS = ("pallets/flask", "psf/requests", "mwaskom/seaborn", "pytest-dev/pytest")

WORKDIR = "/testbed"
ENV_BIN = "/opt/miniconda3/envs/testbed/bin"


# --------------------------------------------------------------------------- #
# dataset and checkouts
# --------------------------------------------------------------------------- #


def fetch_dataset() -> list[dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / "swe-bench-lite.json"
    if target.exists():
        return json.loads(target.read_text())
    rows: list[dict] = []
    offset, total = 0, None
    while total is None or offset < total:
        query = urllib.parse.urlencode(
            {"dataset": DATASET, "config": "default", "split": "test", "offset": offset, "length": 100}
        )
        with urllib.request.urlopen(f"https://datasets-server.huggingface.co/rows?{query}", timeout=60) as resp:
            page = json.load(resp)
        rows += [r["row"] for r in page["rows"]]
        total = page["num_rows_total"]
        offset += 100
    target.write_text(json.dumps(rows))
    return rows


def image_for(instance_id: str) -> str:
    return f"docker.io/swebench/sweb.eval.x86_64.{instance_id.replace('__', '_1776_')}:latest"


def patched_paths(patch: str) -> list[str]:
    """Files a unified diff writes to, in order, without deletions."""
    paths = []
    for line in patch.splitlines():
        if line.startswith("+++ ") and not line.startswith("+++ /dev/null"):
            path = line[4:].split("\t")[0].strip()
            paths.append(path.removeprefix("b/"))
    return list(dict.fromkeys(paths))


def _git(cwd: Path, *args: str, stdin: str | None = None) -> str:
    done = subprocess.run(
        ["git", *args], cwd=cwd, input=stdin, capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])} failed: {done.stderr.strip()[:400]}")
    return done.stdout


def ensure_mirror(repo: str) -> Path:
    """A local mirror of ``repo``, cloned once, completely, under a temporary name.

    Cloning straight to the final path let a parallel worker see the directory
    exist mid-clone and check out from a half-written mirror.
    """
    mirror = CACHE / "mirrors" / repo.replace("/", "__")
    if not mirror.exists():
        partial = mirror.with_name(mirror.name + ".partial")
        shutil.rmtree(partial, ignore_errors=True)
        partial.parent.mkdir(parents=True, exist_ok=True)
        _git(CACHE, "clone", "--quiet", "--mirror", f"https://github.com/{repo}.git", str(partial))
        partial.rename(mirror)
    return mirror


def checkout(row: dict) -> Path:
    """A clean tree at the instance's base commit, with its test patch applied."""
    mirror = ensure_mirror(row["repo"])
    work = CACHE / "work" / row["instance_id"]
    shutil.rmtree(work, ignore_errors=True)
    work.parent.mkdir(parents=True, exist_ok=True)
    _git(CACHE, "clone", "--quiet", "--shared", "--no-checkout", str(mirror), str(work))
    _git(work, "checkout", "--quiet", row["base_commit"])
    _git(work, "apply", "--whitespace=nowarn", "-", stdin=row["test_patch"])
    return work


def files_after_patch(work: Path, patch: str) -> dict[str, bytes]:
    """Contents of every file ``patch`` writes, read after applying it, then undone."""
    _git(work, "apply", "--whitespace=nowarn", "-", stdin=patch)
    try:
        return {p: (work / p).read_bytes() for p in patched_paths(patch) if (work / p).is_file()}
    finally:
        _git(work, "apply", "-R", "--whitespace=nowarn", "-", stdin=patch)


def test_files(row: dict) -> list[str]:
    return [p for p in patched_paths(row["test_patch"]) if p.endswith(".py")]


def file_command(row: dict) -> str:
    """pytest over every test in the files the test patch touches."""
    return pytest_command([shlex.quote(t) for t in test_files(row)])


def select_command(nodes: list[str]) -> str:
    """pytest over exactly these node ids.

    Selecting, not deselecting: pytest matches --deselect as a prefix, so
    deselecting `test_route_decorator_custom_endpoint` also removed
    `test_route_decorator_custom_endpoint_with_dots` -- flask-4045's own
    FAIL_TO_PASS test. A node id given as an argument matches exactly.
    """
    return pytest_command([shlex.quote(n) for n in nodes])


def pytest_command(args: list[str]) -> str:
    return f"PATH={ENV_BIN}:$PATH python -m pytest -q " + " ".join(args)


def protected_paths(row: dict) -> list[str]:
    return patched_paths(row["test_patch"])


def seed_files(row: dict, files: dict[str, bytes]) -> dict[str, bytes]:
    """What the image lacks: it holds the project at the base commit already."""
    return {p: files[p] for p in protected_paths(row) if p in files}


def junit_id(node: str) -> str:
    """A pytest node id as ``parse_junit`` names it: ``pkg.module.Class::test``.

    pytest's junit classname is the node id's path with ``/`` as ``.`` and the
    ``.py`` dropped, followed by any classes; the test name comes after ``::``.
    """
    path, *rest = node.split("::")
    module = path.removesuffix(".py").replace("/", ".")
    if not rest:
        return module
    *classes, name = rest
    return f"{'.'.join([module, *classes])}::{name}"


def node_id(test: str, files: list[str]) -> str | None:
    """The inverse of ``junit_id``, given the files the test must come from."""
    classname, _, name = test.partition("::")
    best: tuple[str, str] | None = None
    for f in files:
        module = f.removesuffix(".py").replace("/", ".")
        if (classname == module or classname.startswith(module + ".")) and (
            best is None or len(module) > len(best[1])
        ):
            best = (f, module)
    if best is None:
        return None
    f, module = best
    classes = classname[len(module) + 1 :].split(".") if classname != module else []
    return "::".join([f, *classes, name])


class Listed:
    """The tests SWE-bench scores an instance on.

    Some ids in the dataset were cut at the first space inside a parameter --
    ``test_x[a`` for ``test_x[a b]`` -- so an unclosed bracket matches as a prefix.
    """

    def __init__(self, row: dict) -> None:
        self.fail_to_pass = {junit_id(t) for t in json.loads(row["FAIL_TO_PASS"])}
        every = self.fail_to_pass | {junit_id(t) for t in json.loads(row["PASS_TO_PASS"])}
        self._every = every
        self._prefixes = [t for t in every if "[" in t and not t.endswith("]")]

    def __contains__(self, test: str) -> bool:
        return test in self._every or any(test.startswith(p) for p in self._prefixes)

    def fails_to_pass(self, test: str) -> bool:
        return test in self.fail_to_pass or any(
            test.startswith(p) for p in self._prefixes if p in self.fail_to_pass
        )


def instances(names: list[str] | None = None) -> list[dict]:
    rows = [r for r in fetch_dataset() if r["repo"] in REPOS]
    if names:
        wanted = set(names)
        rows = [r for r in rows if r["instance_id"] in wanted]
    return sorted(rows, key=lambda r: (REPOS.index(r["repo"]), r["instance_id"]))


# --------------------------------------------------------------------------- #
# sandbox helpers
# --------------------------------------------------------------------------- #


def backend() -> ContreeBackend:
    s = load_settings()
    return ContreeBackend(
        s.nebius_api_key, s.contree_base_url, s.nebius_project_id, timeout=1800.0, workdir=WORKDIR
    )


# The slowest validated suite takes about two minutes; a run past this is hung,
# usually on a test waiting for a network reply that never comes.
SUITE_LIMIT = 600


def run_suite(sandbox: ContreeBackend, checkpoint, command: str, files: dict[str, bytes] | None = None):
    """The same instrumented command Arborist runs, so both judge alike."""
    started = time.time()
    result = sandbox.run(
        checkpoint, f"rm -f {JUNIT_PATH} ; {command} --junitxml={JUNIT_PATH}", files=files, timeout=SUITE_LIMIT
    )
    report = None
    if not result.error:
        xml = sandbox.read(result.checkpoint, JUNIT_PATH)
        report = parse_junit(xml) if xml else None
        if report is None:
            report = parse_pytest_text(result.stdout, result.stderr, result.exit_code)
    return report, result, time.time() - started


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #


@dataclass
class Validation:
    instance_id: str
    repo: str
    valid: bool
    reason: str = ""
    base_seconds: float = 0.0
    suite_seconds: float = 0.0
    tests: int = 0
    failing_before: int = 0
    deselected: int = 0
    command: str = ""


def validate_one(row: dict) -> Validation:
    v = Validation(instance_id=row["instance_id"], repo=row["repo"], valid=False)
    try:
        work = checkout(row)
        files = load_repo(work)
        gold = files_after_patch(work, row["patch"])
        listed = Listed(row)
        test_paths = test_files(row)

        sandbox = backend()
        t = time.time()
        base = sandbox.base(seed_files(row, files), image_for(row["instance_id"]))
        v.base_seconds = round(time.time() - t, 1)

        # 1. The whole test files with the reference fix applied: every test
        #    collects there, so this is where exact names come from --
        #    parametrised ids included, which the dataset sometimes truncates.
        fixed, result, seconds = run_suite(sandbox, base, file_command(row), files=gold)
        v.suite_seconds = round(seconds, 1)
        if result.error or fixed is None or fixed.total == 0:
            v.reason = f"suite did not run with the reference fix: {(result.error or 'no results')[:200]}"
            return v
        seen = fixed.passed_ids | fixed.failed_ids
        chosen = sorted(t for t in seen if t in listed)
        nodes = [n for n in (node_id(t, test_paths) for t in chosen) if n]
        if not nodes:
            v.reason = "no listed test was found in the test files"
            return v
        v.command = select_command(nodes)
        v.tests = len(nodes)
        v.deselected = len(seen) - len(nodes)

        # 2. With the reference fix, exactly the listed tests: green, twice.
        for attempt in (1, 2):
            after, result, _ = run_suite(sandbox, base, v.command, files=gold)
            if result.error or after is None:
                v.reason = f"suite did not run with the reference fix: {(result.error or '')[:200]}"
                return v
            if not after.green:
                bad = sorted(after.failed_ids)[:3]
                word = "leaves" if attempt == 1 else "is nondeterministic, its second run leaves"
                v.reason = f"reference fix {word} {after.failed + after.errors} failing: {bad}"
                return v

        # 3. Without the fix: red, and red the same way twice. A failure no
        #    test file owns counts -- pytest-7168's bug crashes pytest itself,
        #    so none of its tests ever reports failed.
        def blocking(report) -> set[str]:
            return {t for t in report.failed_ids if t in listed or node_id(t, test_paths) is None}

        red = []
        for _ in (1, 2):
            before, result, _ = run_suite(sandbox, base, v.command)
            if result.error or before is None:
                v.reason = f"suite did not run without the fix: {(result.error or 'no results')[:200]}"
                return v
            red.append(blocking(before) or ({"<exit>"} if not before.green else set()))
        v.failing_before = len(red[0])
        if not red[0]:
            v.reason = "nothing listed fails without the fix"
            return v
        if red[0] != red[1]:
            v.reason = f"nondeterministic without the fix: {sorted(red[0] ^ red[1])[:3]}"
            return v
        v.valid = True
        return v
    except Exception as exc:  # noqa: BLE001 - one broken instance must not stop the rest
        v.reason = f"{type(exc).__name__}: {str(exc)[:240]}"
        return v


def validate(args) -> int:
    rows = instances(args.instances)
    print(f"validating {len(rows)} instances from {', '.join(REPOS)}", flush=True)
    # Mirrors first, one at a time; only then fan out over instances.
    for repo in dict.fromkeys(r["repo"] for r in rows):
        ensure_mirror(repo)
    results: list[Validation] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for v in pool.map(validate_one, rows):
            results.append(v)
            mark = "ok  " if v.valid else "SKIP"
            print(
                f"  {mark} {v.instance_id:28} tests={v.tests:4} suite={v.suite_seconds:6.1f}s  {v.reason}",
                flush=True,
            )
    out = HERE / "validation.json"
    out.write_text(json.dumps([asdict(v) for v in results], indent=2))
    print(f"{sum(v.valid for v in results)}/{len(results)} valid -> {out.relative_to(ROOT)}")
    return 0


# --------------------------------------------------------------------------- #
# the agent runs
# --------------------------------------------------------------------------- #


@dataclass
class Row:
    instance_id: str
    repo: str
    branching: bool
    run: int
    solved: bool = False
    verified: bool = False
    verify_note: str = ""
    patches: int = 0
    invalid_patches: int = 0
    sandbox_runs: int = 0
    wall_seconds: float = 0.0
    tokens_nano: int = 0
    tokens_super: int = 0
    tokens_ultra: int = 0
    tavily_queries: int = 0
    error: str = ""
    touched: list[str] = field(default_factory=list)


def verify(row: dict, diff: str, command: str) -> tuple[bool, str, list[str]]:
    """Apply the reported diff to a clean checkout and re-run the suite from scratch."""
    touched = patched_paths(diff)
    guarded = set(protected_paths(row))
    if any(p in guarded for p in touched):
        return False, "diff edits a protected test file", touched
    work = checkout(row)
    try:
        files = files_after_patch(work, diff)
    except RuntimeError as exc:
        return False, f"reported diff does not apply: {exc}", touched
    sandbox = backend()
    base = sandbox.base(seed_files(row, load_repo(work)), image_for(row["instance_id"]))
    report, result, _ = run_suite(sandbox, base, command, files=files)
    if result.error or report is None:
        return False, "suite did not run on re-check", touched
    if not report.green:
        return False, f"re-check: {report.failed + report.errors} failing", touched
    return True, "", touched


def run_one(row: dict, command: str, branching: bool, repetition: int, args) -> Row:
    out = Row(instance_id=row["instance_id"], repo=row["repo"], branching=branching, run=repetition)
    settings = load_settings(
        backend="contree",
        # Linear means one hypothesis at a time, exactly as in evals/run_eval.py.
        fanout=args.fanout if branching else 1,
        max_nodes=args.max_nodes,
        # The same rule as evals/run_eval.py: a depth cap would stop the linear
        # arm, which can only go deeper, long before its node budget.
        max_depth=None if branching else args.max_nodes,
        branching=branching,
        workdir=WORKDIR,
    )
    work = checkout(row)
    agent = Arborist(
        settings,
        backend(),
        NemotronClient(settings),
        TavilyClient(api_key=settings.tavily_api_key) if settings.has_tavily else None,
    )
    started = time.time()
    try:
        result = agent.run(
            RunConfig(
                repo_path=str(work),
                test_command=command,
                image=image_for(row["instance_id"]),
                goal=row["problem_statement"],
                protected=protected_paths(row),
                upload_only=protected_paths(row),
            )
        )
    except Exception as exc:  # noqa: BLE001
        out.error = f"{type(exc).__name__}: {str(exc)[:300]}"
        out.wall_seconds = round(time.time() - started, 1)
        return out

    stats = result.stats
    tiers = (result.usage or {}).get("by_tier", {})
    out.solved = bool(result.solved)
    out.patches = stats.get("patches_evaluated", 0)
    out.invalid_patches = stats.get("invalid_patches", 0)
    out.sandbox_runs = stats.get("sandbox_executions", 0)
    out.wall_seconds = round(stats.get("wall_seconds", time.time() - started), 1)
    out.tavily_queries = len(stats.get("tavily_queries") or [])
    out.error = result.error or ""
    for tier in ("nano", "super", "ultra"):
        setattr(out, f"tokens_{tier}", int((tiers.get(tier) or {}).get("total_tokens", 0)))

    if args.reports:
        reports = HERE / "reports"
        reports.mkdir(exist_ok=True)
        stem = f"{row['instance_id']}-{'branching' if branching else 'linear'}-{repetition}"
        (reports / f"{stem}.json").write_text(json.dumps(result.to_dict(), indent=2))

    if out.solved:
        out.verified, out.verify_note, out.touched = verify(row, result.diff, command)
    return out


def load_rows(path: Path) -> list[Row]:
    if not path.exists():
        return []
    return [Row(**r) for r in json.loads(path.read_text())]


def write(rows: list[Row], out: Path) -> None:
    out.with_suffix(".json").write_text(json.dumps([asdict(r) for r in rows], indent=2))
    out.write_text(markdown(rows))


def code_version() -> str:
    """The commit the numbers came from, marked when the tree had local changes."""
    try:
        head = _git(ROOT, "rev-parse", "--short", "HEAD").strip()
        dirty = _git(ROOT, "status", "--porcelain", "--untracked-files=no").strip()
    except (OSError, RuntimeError):
        return "unknown"
    return f"{head}+local changes" if dirty else head


def markdown(rows: list[Row]) -> str:
    lines = [
        "# SWE-bench Lite on Nebius Sandboxes",
        "",
        f"code: `{code_version()}`",
        "",
        "Test-driven setting: the agent sees the issue **and** the failing tests, which are",
        "protected from edits. Not comparable to the SWE-bench leaderboard. Method and",
        "exclusions: [README.md](README.md).",
        "",
        "## Summary",
        "",
        "| arm | resolved (verified) | reported solved | patches (median) | wall s (median) | tokens (median) |",
        "|---|---|---|---|---|---|",
    ]
    for branching in (True, False):
        arm = [r for r in rows if r.branching == branching]
        if not arm:
            continue
        tokens = [r.tokens_nano + r.tokens_super + r.tokens_ultra for r in arm]
        lines.append(
            f"| {'branching' if branching else 'linear'} | **{sum(r.verified for r in arm)}/{len(arm)}** "
            f"| {sum(r.solved for r in arm)}/{len(arm)} | {statistics.median([r.patches for r in arm]):g} "
            f"| {statistics.median([r.wall_seconds for r in arm]):.0f} | {statistics.median(tokens):,.0f} |"
        )
    both = _paired(rows)
    if both:
        only_b = sum(1 for b, lin in both if b and not lin)
        only_l = sum(1 for b, lin in both if lin and not b)
        lines += [
            "",
            (
                f"Paired by instance: branching alone resolved **{only_b}**, linear alone "
                f"resolved **{only_l}**, of {len(both)} instances run in both arms."
            ),
        ]
    lines += [
        "",
        "## Every run",
        "",
        "| instance | arm | run | solved | verified | patches | invalid | sandbox runs | wall s | tokens | tavily | note |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        note = r.verify_note or r.error
        lines.append(
            f"| {r.instance_id} | {'branching' if r.branching else 'linear'} | {r.run} "
            f"| {'yes' if r.solved else 'no'} | {'yes' if r.verified else ('-' if not r.solved else 'NO')} "
            f"| {r.patches} | {r.invalid_patches} | {r.sandbox_runs} | {r.wall_seconds:.0f} "
            f"| {r.tokens_nano + r.tokens_super + r.tokens_ultra:,} | {r.tavily_queries} | {note[:80]} |"
        )
    return "\n".join(lines) + "\n"


def _paired(rows: list[Row]) -> list[tuple[bool, bool]]:
    by: dict[str, dict[bool, bool]] = {}
    for r in rows:
        by.setdefault(r.instance_id, {})[r.branching] = by.get(r.instance_id, {}).get(r.branching, False) or r.verified
    return [(v[True], v[False]) for v in by.values() if True in v and False in v]


def run(args) -> int:
    validation = HERE / "validation.json"
    if not validation.exists():
        print("run `validate` first: instances are only scored once the environment is known good", file=sys.stderr)
        return 2
    # The run uses the exact command validation proved: the same test selection.
    valid = {v["instance_id"]: v["command"] for v in json.loads(validation.read_text()) if v["valid"]}
    rows_in = [r for r in instances(args.instances) if r["instance_id"] in valid]
    modes = {"on": [True], "off": [False]}.get(args.only, [True, False])

    out = Path(args.out)
    done_rows = load_rows(out.with_suffix(".json")) if args.resume else []
    done = {(r.instance_id, r.branching, r.run) for r in done_rows}
    rows = list(done_rows)
    print(f"{len(rows_in)} valid instances x {len(modes)} arm(s) x {args.repeat}", flush=True)

    for row in rows_in:
        for branching in modes:
            for repetition in range(1, args.repeat + 1):
                if (row["instance_id"], branching, repetition) in done:
                    continue
                label = "branching" if branching else "linear   "
                print(f"-> {row['instance_id']} [{label}] run {repetition}", flush=True)
                # A hung run dumps every thread's stack and exits; results so
                # far are on disk, and --resume continues from here.
                result = None
                for _attempt in range(3):
                    wall, awake = time.time(), time.monotonic()
                    faulthandler.dump_traceback_later(args.run_limit * 60, exit=True)
                    try:
                        candidate = run_one(row, valid[row["instance_id"]], branching, repetition, args)
                    finally:
                        faulthandler.cancel_dump_traceback_later()
                    # On macOS the monotonic clock stops while the machine
                    # sleeps; a run a closed lid interrupted is not counted.
                    slept = (time.time() - wall) - (time.monotonic() - awake)
                    if slept <= 30:
                        result = candidate
                        break
                    print(f"   the machine slept {slept:.0f}s during this run -- repeating", flush=True)
                if result is None:
                    print("   still disturbed after three attempts; left for --resume", flush=True)
                    continue
                rows.append(result)
                write(rows, out)
                print(
                    f"   solved={result.solved} verified={result.verified} patches={result.patches} "
                    f"wall={result.wall_seconds}s {result.verify_note or result.error}",
                    flush=True,
                )
    write(rows, out)
    print(markdown(rows))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="phase", required=True)

    v = sub.add_parser("validate", help="check every instance in the sandbox, no model calls")
    v.add_argument("--instances", nargs="*", help="limit to these instance ids")
    v.add_argument("--workers", type=int, default=4)

    r = sub.add_parser("run", help="run Arborist on every validated instance")
    r.add_argument("--instances", nargs="*", help="limit to these instance ids")
    r.add_argument("--only", choices=["on", "off"], help="one arm only")
    r.add_argument("--repeat", type=int, default=1)
    r.add_argument("--fanout", type=int, default=3)
    r.add_argument("--max-nodes", type=int, default=12)
    r.add_argument("--out", default=str(HERE / "results.md"))
    r.add_argument("--resume", action="store_true")
    r.add_argument("--reports", action="store_true", help="save every run's full tree")
    r.add_argument("--run-limit", type=float, default=60, help="minutes before a stuck run is abandoned")

    args = parser.parse_args()
    faulthandler.enable()
    if hasattr(signal, "SIGUSR1"):
        faulthandler.register(signal.SIGUSR1, all_threads=True)
    return validate(args) if args.phase == "validate" else run(args)


if __name__ == "__main__":
    sys.exit(main())
