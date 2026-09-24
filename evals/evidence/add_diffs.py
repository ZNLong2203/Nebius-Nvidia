"""Add per-node diffs to run reports recorded before nodes carried one.

Each node's diff is rebuilt by replaying the edits the run recorded, from the
case's own source through every ancestor, with the same `apply_edits` the
search uses. Nothing is re-run and no model is called: the edits are the
record, and the diff is only a readable view of them. A node whose edits do not
apply -- an invalid patch, which never reached the sandbox -- gets no diff.

    python evals/evidence/add_diffs.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from arborist.models import Edit
from arborist.repo import (
    PatchError,
    apply_edits,
    changed_files,
    load_repo,
    text_files,
    unified_diff,
)

SOURCES = {
    "demo-broken-invoice.json": ROOT / "examples" / "broken-invoice",
    "demo-broken-invoice-alt-1.json": ROOT / "examples" / "broken-invoice",
    "demo-broken-invoice-alt-2.json": ROOT / "examples" / "broken-invoice",
    "sandboxes-first-run.json": ROOT / "examples" / "broken-invoice",
    "masked-faults-branching.json": ROOT / "evals" / "cases" / "masked-faults",
    "masked-faults-linear.json": ROOT / "evals" / "cases" / "masked-faults",
    "tavily-outside-knowledge.json": ROOT / "evals" / "cases" / "outside-knowledge",
}
SWEBENCH = {"tavily-swebench-pytest-7373.json": "pytest-dev__pytest-7373"}


def source_files(name: str) -> dict[str, str]:
    if name in SOURCES:
        return text_files(load_repo(SOURCES[name]))
    sys.path.insert(0, str(ROOT / "evals" / "swebench"))
    from run_swebench import checkout, instances

    row = next(r for r in instances([SWEBENCH[name]]))
    return text_files(load_repo(checkout(row)))


def add_diffs(report: dict, files: dict[str, str]) -> int:
    states = {report["nodes"][0]["id"]: files}
    added = 0
    for node in sorted(report["nodes"], key=lambda n: n["depth"]):
        parent = states.get(node.get("parent_id") or "")
        if parent is None or not node.get("edits"):
            continue
        edits = [Edit(**{k: e.get(k) for k in ("path", "search", "replace", "new_content")}) for e in node["edits"]]
        try:
            patched = apply_edits(parent, edits)
        except PatchError:
            continue
        states[node["id"]] = patched
        changed = changed_files(parent, patched)
        node["diff"] = unified_diff({p: parent.get(p, "") for p in changed}, changed)
        added += 1
    return added


def main() -> int:
    for name in [*SOURCES, *SWEBENCH]:
        path = HERE / name
        report = json.loads(path.read_text())
        count = add_diffs(report, source_files(name))
        path.write_text(json.dumps(report, indent=2) + "\n")
        print(f"{name}: {count} of {len(report['nodes']) - 1} nodes given a diff")
    return 0


if __name__ == "__main__":
    sys.exit(main())
