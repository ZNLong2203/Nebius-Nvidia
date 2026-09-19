"""The search.

A conventional coding agent is a straight line: edit, run, read the failure,
edit again. When an attempt makes things worse it has to walk back by *undoing*
-- re-cloning, re-installing, re-running everything it had already run -- and it
carries the damage forward in the meantime.

Arborist treats repair as a search over immutable repository states. The
expensive prefix (dependencies installed, caches warm) is one checkpoint. Every
candidate patch is a fork of that checkpoint, evaluated independently and in
parallel. The tests score each fork, the best one becomes the next fork point,
and a branch that regresses is abandoned by simply never being forked from
again -- at no cost, because nothing was mutated.

That turns two things a linear agent cannot do into ordinary operations:

* **breadth** -- four rival theories of one bug, all tested against the same
  starting state, so their scores are actually comparable;
* **depth with backtracking** -- a partial fix that repairs two of three
  failures becomes the base for the next attempt, and if that attempt regresses
  the partial fix is still sitting there, untouched.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .agent import adjudicate, diagnose, propose_patch
from .config import Settings
from .llm import LLM, BudgetExceeded
from .models import Node, TestReport, new_id
from .repo import (
    PatchError,
    apply_edits,
    changed_files,
    load_repo,
    parse_junit,
    parse_pytest_text,
    select_context,
    text_files,
    unified_diff,
)
from .sandbox import Backend, Checkpoint
from .tools.tavily import TavilyClient

# Relative to the workspace on purpose: an absolute /tmp path would be shared
# between branches evaluated in parallel, and each branch must report only on
# its own state.
JUNIT_PATH = ".arborist/report.xml"
REGRESSION_WEIGHT = 0.6
TIE_EPSILON = 1e-6
STALL_LIMIT = 2


@dataclass
class RunConfig:
    repo_path: str
    test_command: str = "python -m pytest -q"
    setup_command: str = ""
    image: str = "python:3.12-slim"
    context_files: list[str] = field(default_factory=list)
    goal: str = ""

    @property
    def instrumented_test_command(self) -> str:
        """Add a junit report so scoring sees test identities, not just counts."""
        if "--junitxml" in self.test_command:
            return self.test_command
        return f"{self.test_command} --junitxml={JUNIT_PATH}"


@dataclass
class RunResult:
    run_id: str
    solved: bool
    nodes: list[Node]
    winner: Node | None
    diff: str
    baseline: TestReport | None
    final: TestReport | None
    stats: dict[str, Any]
    usage: dict[str, Any]
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "solved": self.solved,
            "winner_id": self.winner.id if self.winner else None,
            "diff": self.diff,
            "baseline": self.baseline.to_dict() if self.baseline else None,
            "final": self.final.to_dict() if self.final else None,
            "nodes": [n.to_dict() for n in self.nodes],
            "stats": self.stats,
            "usage": self.usage,
            "error": self.error,
        }


@dataclass
class _NodeState:
    """Everything about a node the search needs but the UI does not."""

    node: Node
    checkpoint: Checkpoint | None
    files: dict[str, str]
    report: TestReport | None
    stdout: str = ""
    stderr: str = ""
    tried: list[str] = field(default_factory=list)


class Arborist:
    def __init__(
        self,
        settings: Settings,
        backend: Backend,
        llm: LLM,
        tavily: TavilyClient | None = None,
        on_event: Callable[[dict], None] | None = None,
    ) -> None:
        self.settings = settings
        self.backend = backend
        self.llm = llm
        self.tavily = tavily
        self._on_event = on_event or (lambda _e: None)

        self.nodes: list[Node] = []
        self._states: dict[str, _NodeState] = {}
        self._sandbox_runs = 0
        self._sandbox_seconds = 0.0
        self._setup_seconds = 0.0
        self._invalid_patches = 0
        self._stalls = 0

    # -- plumbing -----------------------------------------------------------
    def _emit(self, kind: str, **payload) -> None:
        try:
            self._on_event({"type": kind, "at": time.time(), **payload})
        except Exception:  # noqa: BLE001, S110 - a broken listener must not kill a run
            pass

    def _register(self, node: Node, state: _NodeState) -> None:
        self.nodes.append(node)
        self._states[node.id] = state
        self._emit("node", node=node.to_dict())

    def _update(self, node: Node) -> None:
        self._emit("node", node=node.to_dict())

    # -- scoring ------------------------------------------------------------
    @staticmethod
    def score(parent: TestReport | None, report: TestReport | None) -> tuple[float, list[str], list[str]]:
        """Score a state, and name what it fixed and what it broke.

        Pass rate alone rewards a patch that trades one failure for another.
        Comparing *test identities* against the parent is what makes a trade
        visible, and regressions are weighted hard enough that the search will
        not follow one.
        """
        if report is None:
            return 0.0, [], []
        if report.collection_error or report.total == 0:
            return 0.0, [], []
        if report.green:
            fixed = sorted(report.passed_ids - parent.passed_ids) if parent else sorted(report.passed_ids)
            return 1.0, fixed, []

        rate = report.passed / max(report.total, 1)
        if parent is None:
            return rate, [], []

        regressions = sorted(parent.passed_ids - report.passed_ids)
        fixed = sorted(report.passed_ids - parent.passed_ids)
        penalty = REGRESSION_WEIGHT * (len(regressions) / max(parent.total, 1))
        return max(0.0, rate - penalty), fixed, regressions

    # -- sandbox ------------------------------------------------------------
    def _run_tests(
        self,
        checkpoint: Checkpoint,
        cfg: RunConfig,
        files: dict[str, bytes] | None = None,
        prefix: str = "",
    ) -> tuple[Checkpoint, TestReport | None, str, str, float]:
        command = cfg.instrumented_test_command
        if prefix:
            command = f"{prefix} ; {command}"
        result = self.backend.run(checkpoint, command, files=files)
        self._sandbox_runs += 1
        self._sandbox_seconds += result.seconds

        if result.error:
            return result.checkpoint, None, result.stdout, result.error, result.seconds

        report = None
        xml = self.backend.read(result.checkpoint, JUNIT_PATH)
        if xml:
            report = parse_junit(xml)
        if report is None:
            report = parse_pytest_text(result.stdout, result.stderr, result.exit_code)
        report.raw_tail = (result.stdout or "")[-4000:]
        return result.checkpoint, report, result.stdout, result.stderr, result.seconds

    # -- main ---------------------------------------------------------------
    def run(self, cfg: RunConfig) -> RunResult:
        run_id = new_id("run")
        started = time.time()
        self._emit("run_started", run_id=run_id, repo=cfg.repo_path, test_command=cfg.test_command)

        raw_files = load_repo(cfg.repo_path)
        sources = text_files(raw_files)

        base_cp = self.backend.base(raw_files, cfg.image)
        self._emit("checkpoint", stage="base", checkpoint=base_cp.id)

        # The expensive prefix, paid exactly once for the entire search.
        if cfg.setup_command:
            t0 = time.time()
            setup = self.backend.run(base_cp, cfg.setup_command)
            self._setup_seconds = time.time() - t0
            self._sandbox_runs += 1
            if setup.error:
                return self._bail(run_id, f"setup failed: {setup.error}", started)
            base_cp = setup.checkpoint
            self._emit(
                "checkpoint", stage="setup", checkpoint=base_cp.id, seconds=round(self._setup_seconds, 2)
            )

        root_cp, baseline, stdout, stderr, _ = self._run_tests(base_cp, cfg)
        if baseline is None:
            return self._bail(run_id, f"baseline test run failed: {stderr[:500]}", started)

        root = Node(id=new_id("n"), parent_id=None, depth=0, checkpoint_id=root_cp.id)
        root.report = baseline
        root.score, _, _ = self.score(None, baseline)
        root.status = "green" if baseline.green else "failed"
        root.stdout_tail = stdout[-4000:]
        root.note = "baseline"
        self._register(root, _NodeState(root, root_cp, sources, baseline, stdout, stderr))

        if baseline.green:
            return self._finish(run_id, cfg, root, sources, started, already_green=True)

        # The point every branch forks from when branching is disabled, so the
        # baseline agent pays the setup cost again on every single attempt.
        linear_base = base_cp

        frontier: list[str] = [root.id]
        best_id = root.id
        error = ""

        try:
            while len(self.nodes) - 1 < self.settings.max_nodes:
                candidate_id = self._select(frontier)
                if candidate_id is None:
                    break
                parent_state = self._states[candidate_id]
                parent_state.node.expanded = True
                self._update(parent_state.node)

                children = self._expand(cfg, parent_state, linear_base)
                if not children:
                    frontier = [nid for nid in frontier if nid != candidate_id]
                    continue

                improved = False
                for child_id in children:
                    child = self._states[child_id].node
                    if child.status == "green":
                        return self._finish(run_id, cfg, child, sources, started)
                    if child.score > self._states[best_id].node.score + TIE_EPSILON:
                        best_id = child_id
                        improved = True
                    if child.status in {"improved", "neutral"}:
                        frontier.append(child_id)

                frontier = [nid for nid in frontier if nid != candidate_id]
                self._stalls = 0 if improved else self._stalls + 1
                self._emit("progress", best_score=self._states[best_id].node.score, stalls=self._stalls)

        except BudgetExceeded as exc:
            error = str(exc)
            self._emit("budget_exceeded", message=error)
        except Exception as exc:  # noqa: BLE001 - always return the partial tree
            error = f"{type(exc).__name__}: {exc}"
            self._emit("error", message=error)

        winner = self._states[best_id].node
        if winner.id == root.id:
            winner_node = None
        else:
            winner_node = self._resolve_tie(cfg, best_id)
        return self._finish(run_id, cfg, winner_node, sources, started, error=error)

    # -- selection ----------------------------------------------------------
    def _select(self, frontier: list[str]) -> str | None:
        """Best-first with a shallow-depth tiebreak.

        Depth is only worth paying for once breadth has stopped helping, so
        among equal scores the shallower node wins: its siblings are cheaper to
        reach and more likely to be independent theories rather than
        refinements of one.
        """
        live = [
            nid
            for nid in dict.fromkeys(frontier)
            if not self._states[nid].node.expanded
            and self._states[nid].node.depth < self.settings.max_depth
        ]
        if not live:
            return None
        return max(live, key=lambda nid: (self._states[nid].node.score, -self._states[nid].node.depth))

    # -- expansion ----------------------------------------------------------
    def _expand(self, cfg: RunConfig, parent: _NodeState, linear_base: Checkpoint) -> list[str]:
        node = parent.node
        # Escalate to Ultra only once the cheaper tier has stopped making
        # progress -- adaptive routing, not a fixed ladder.
        tier = "ultra" if self._stalls >= STALL_LIMIT else "super"
        wanted = list(cfg.context_files)
        if node.hypothesis:
            wanted += node.hypothesis.target_files
        wanted += _guess_files(parent.report, parent.files)
        context = select_context(parent.files, wanted or sorted(parent.files))

        self._emit("diagnosing", node_id=node.id, tier=tier)
        hypotheses, meta = diagnose(
            self.llm,
            tier=tier,
            test_command=cfg.test_command,
            report=parent.report,
            stdout=parent.stdout,
            stderr=parent.stderr,
            sources=context,
            file_index=sorted(parent.files),
            tavily=self.tavily,
            parent_attempts=parent.tried,
            fanout=self.settings.fanout,
        )
        self._emit(
            "diagnosed",
            node_id=node.id,
            tier=tier,
            root_cause=meta.get("root_cause", ""),
            searched=meta.get("searched", False),
            search_query=meta.get("search_query", ""),
            hypotheses=[h.to_dict() for h in hypotheses],
        )
        if not hypotheses:
            node.note = "no hypotheses produced"
            self._update(node)
            return []

        if meta.get("request_files"):
            context = {**context, **select_context(parent.files, meta["request_files"])}

        # Without branching there is one line of attack and the checkpoint is
        # thrown away, which is exactly the baseline the evals compare against.
        if not self.settings.branching:
            hypotheses = hypotheses[:1]

        budget_left = self.settings.max_nodes - (len(self.nodes) - 1)
        hypotheses = hypotheses[: max(1, min(len(hypotheses), budget_left))]

        def build(hypothesis):
            return self._evaluate(cfg, parent, hypothesis, context, meta, linear_base)

        if len(hypotheses) == 1:
            results = [build(hypotheses[0])]
        else:
            with ThreadPoolExecutor(max_workers=min(len(hypotheses), 8)) as pool:
                results = list(pool.map(build, hypotheses))

        return [nid for nid in results if nid]

    def _evaluate(self, cfg, parent: _NodeState, hypothesis, context, meta, linear_base) -> str | None:
        """Propose a patch, apply it to a fork of the parent, score the result."""
        node = Node(
            id=new_id("n"),
            parent_id=parent.node.id,
            depth=parent.node.depth + 1,
            hypothesis=hypothesis,
            diagnosis=meta.get("root_cause", ""),
            model_tier="nano",
        )
        started = time.time()

        try:
            edits, explanation = propose_patch(
                self.llm,
                tier="nano",
                hypothesis=hypothesis,
                root_cause=meta.get("root_cause", ""),
                test_command=cfg.test_command,
                report=parent.report,
                stdout=parent.stdout,
                stderr=parent.stderr,
                sources=context,
                evidence=meta.get("evidence", ""),
            )
        except BudgetExceeded:
            raise
        except Exception as exc:  # noqa: BLE001
            node.status = "invalid"
            node.note = f"patch generation failed: {type(exc).__name__}"
            node.wall_seconds = time.time() - started
            self._register(node, _NodeState(node, None, parent.files, None))
            return None

        node.edits = edits
        node.explanation = explanation

        # Validate before spending a sandbox execution: a patch that cannot be
        # applied costs tokens, never wall-clock.
        try:
            patched = apply_edits(parent.files, edits)
        except PatchError as exc:
            self._invalid_patches += 1
            node.status = "invalid"
            node.note = str(exc)
            node.wall_seconds = time.time() - started
            parent.tried.append(f"{hypothesis.title} (patch did not apply: {exc})")
            self._register(node, _NodeState(node, None, parent.files, None))
            return None

        payload = {p: body.encode("utf-8") for p, body in changed_files(parent.files, patched).items()}

        if self.settings.branching:
            fork_from = parent.checkpoint
            prefix = ""
        else:
            # No checkpoint reuse: rebuild the environment for every attempt.
            fork_from = linear_base
            prefix = cfg.setup_command or ""

        checkpoint, report, stdout, stderr, _elapsed = self._run_tests(
            fork_from, cfg, files=payload, prefix=prefix
        )

        score, fixed, regressions = self.score(parent.report, report)
        node.checkpoint_id = checkpoint.id
        node.report = report
        node.score = score
        node.fixed = fixed
        node.regressions = regressions
        node.stdout_tail = (stdout or "")[-4000:]
        node.wall_seconds = time.time() - started

        if report is None:
            node.status = "invalid"
            node.note = stderr[:300] or "sandbox execution failed"
        elif report.green:
            node.status = "green"
        elif regressions:
            node.status = "regressed"
        elif score > parent.node.score + TIE_EPSILON:
            node.status = "improved"
        else:
            node.status = "neutral"

        parent.tried.append(f"{hypothesis.title} -> {node.status} (score {score:.2f})")
        self._register(
            node,
            _NodeState(node, checkpoint, patched, report, stdout, stderr, tried=list(parent.tried)),
        )
        return node.id

    # -- tie breaking -------------------------------------------------------
    def _resolve_tie(self, cfg: RunConfig, best_id: str) -> Node:
        """When the tests cannot separate the leaders, ask Ultra to.

        Only reached when two branches score identically, which is precisely the
        case where a test suite has stopped being informative -- often because
        one of the patches is gaming it.
        """
        best = self._states[best_id].node
        tied = [
            s.node
            for s in self._states.values()
            if s.node.id != best_id
            and s.node.report is not None
            and abs(s.node.score - best.score) <= TIE_EPSILON
            and s.node.status in {"improved", "neutral", "green"}
        ]
        if not tied:
            return best

        candidates = []
        for node in [best, *tied[:3]]:
            state = self._states[node.id]
            parent_state = self._states.get(node.parent_id or "")
            base_files = parent_state.files if parent_state else {}
            candidates.append(
                {
                    "id": node.id,
                    "hypothesis": node.hypothesis.title if node.hypothesis else "",
                    "explanation": node.explanation,
                    "score": round(node.score, 3),
                    "fixed": node.fixed,
                    "regressions": node.regressions,
                    "diff": unified_diff(base_files, state.files),
                }
            )

        try:
            verdict = adjudicate(self.llm, candidates=candidates, test_command=cfg.test_command)
        except Exception:  # noqa: BLE001 - a failed tiebreak keeps the test-based winner
            return best

        self._emit("adjudicated", verdict=verdict)
        winner_id = str(verdict.get("winner") or "")
        for node in [best, *tied]:
            if node.id in verdict.get("suspicious", []) or []:
                node.note = (node.note + " | flagged by Ultra: gaming the suite").strip(" |")
                self._update(node)
        if winner_id in self._states:
            chosen = self._states[winner_id].node
            chosen.note = (chosen.note + " | chosen by Ultra tiebreak").strip(" |")
            self._update(chosen)
            return chosen
        return best

    # -- finishing ----------------------------------------------------------
    def _stats(self, started: float) -> dict[str, Any]:
        evaluated = [n for n in self.nodes if n.depth > 0]
        return {
            "backend": self.backend.name,
            "branching": self.settings.branching,
            "wall_seconds": round(time.time() - started, 2),
            "sandbox_executions": self._sandbox_runs,
            "sandbox_seconds": round(self._sandbox_seconds, 2),
            "setup_seconds": round(self._setup_seconds, 2),
            "setup_runs": 1 if self.settings.branching else max(1, len(evaluated)),
            "setup_seconds_saved": round(
                self._setup_seconds * max(0, len(evaluated) - 1) if self.settings.branching else 0.0, 2
            ),
            "nodes": len(self.nodes),
            "patches_evaluated": len(evaluated),
            "invalid_patches": self._invalid_patches,
            "forks": getattr(self.backend, "fork_count", None),
            "tavily_queries": list(self.tavily.queries) if self.tavily else [],
        }

    def _bail(self, run_id: str, message: str, started: float) -> RunResult:
        self._emit("error", message=message)
        return RunResult(
            run_id=run_id,
            solved=False,
            nodes=self.nodes,
            winner=None,
            diff="",
            baseline=None,
            final=None,
            stats=self._stats(started),
            usage=self.llm.usage_report(),
            error=message,
        )

    def _finish(
        self,
        run_id: str,
        cfg: RunConfig,
        winner: Node | None,
        original: dict[str, str],
        started: float,
        *,
        already_green: bool = False,
        error: str = "",
    ) -> RunResult:
        diff = ""
        final_report = None
        if winner is not None:
            state = self._states[winner.id]
            final_report = state.report
            diff = unified_diff(original, state.files)

        result = RunResult(
            run_id=run_id,
            solved=bool(winner and winner.report and winner.report.green) or already_green,
            nodes=self.nodes,
            winner=winner,
            diff=diff,
            baseline=self.nodes[0].report if self.nodes else None,
            final=final_report,
            stats=self._stats(started),
            usage=self.llm.usage_report(),
            error=error,
        )
        self._emit("run_finished", result=result.to_dict())
        return result


def _guess_files(report: TestReport | None, files: dict[str, str]) -> list[str]:
    """Cheap heuristic: file paths mentioned in the failure output are relevant."""
    if not report:
        return []
    blob = report.raw_tail + " " + " ".join(report.failed_ids)
    hits = []
    for path in files:
        stem = Path(path).name
        if stem and stem in blob:
            hits.append(path)
    return hits


def write_report(result: RunResult, directory: str | Path) -> Path:
    """Persist a run so the UI (and a PR body) can be rebuilt from disk."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{result.run_id}.json"
    path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    if result.diff:
        (directory / f"{result.run_id}.patch").write_text(result.diff, encoding="utf-8")
    return path
