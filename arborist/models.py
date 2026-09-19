"""Plain data carried between the sandbox, the models and the UI."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class Edit:
    """One file change.

    Two forms are accepted, because small models are much better at one of them
    than the other. ``search``/``replace`` is the default: the model quotes an
    exact snippet and its replacement, which we can verify before spending a
    sandbox execution on it. ``new_content`` rewrites a whole file and is only
    worth it for short files.
    """

    path: str
    search: str | None = None
    replace: str | None = None
    new_content: str | None = None

    @property
    def is_rewrite(self) -> bool:
        return self.new_content is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "search": self.search,
            "replace": self.replace,
            "new_content": self.new_content,
        }


@dataclass
class Hypothesis:
    """A guess at why the suite is red, and a strategy for fixing it."""

    id: str
    title: str
    rationale: str = ""
    target_files: list[str] = field(default_factory=list)
    strategy: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "rationale": self.rationale,
            "target_files": self.target_files,
            "strategy": self.strategy,
        }


@dataclass
class TestReport:
    """Normalised result of one test run."""

    __test__ = False  # not a pytest test class, despite the name

    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    failed_ids: set[str] = field(default_factory=set)
    passed_ids: set[str] = field(default_factory=set)
    collection_error: bool = False
    raw_tail: str = ""

    @property
    def green(self) -> bool:
        return self.total > 0 and self.failed == 0 and self.errors == 0 and not self.collection_error

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "skipped": self.skipped,
            "failed_ids": sorted(self.failed_ids),
            "collection_error": self.collection_error,
            "green": self.green,
        }


NodeStatus = Literal["running", "improved", "neutral", "regressed", "invalid", "green", "failed"]


@dataclass
class Node:
    """One state in the search tree: a checkpoint plus how good it is."""

    id: str
    parent_id: str | None
    depth: int
    checkpoint_id: str | None = None
    hypothesis: Hypothesis | None = None
    edits: list[Edit] = field(default_factory=list)
    explanation: str = ""
    report: TestReport | None = None
    score: float = 0.0
    status: NodeStatus = "running"
    regressions: list[str] = field(default_factory=list)
    fixed: list[str] = field(default_factory=list)
    stdout_tail: str = ""
    model_tier: str = ""
    wall_seconds: float = 0.0
    created_at: float = field(default_factory=time.time)
    expanded: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "depth": self.depth,
            "checkpoint_id": self.checkpoint_id,
            "hypothesis": self.hypothesis.to_dict() if self.hypothesis else None,
            "edits": [e.to_dict() for e in self.edits],
            "explanation": self.explanation,
            "report": self.report.to_dict() if self.report else None,
            "score": round(self.score, 4),
            "status": self.status,
            "regressions": self.regressions,
            "fixed": self.fixed,
            "stdout_tail": self.stdout_tail,
            "model_tier": self.model_tier,
            "wall_seconds": round(self.wall_seconds, 2),
            "expanded": self.expanded,
            "note": self.note,
        }


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"
