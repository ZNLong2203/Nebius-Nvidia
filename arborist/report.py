"""Turning a run into something a human reviews.

A coding agent normally hands you a diff and asks you to trust it. The search
produced a great deal more than a diff: every theory it considered, the patch
each one implied, and exactly which tests each patch fixed and broke. That is
the material a reviewer actually wants, and throwing it away at the end would be
the waste.

This module renders a run report as the body of a pull request: the fix, the
evidence it works, and -- folded away but present -- the alternatives, with the
test-level reason each one lost.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

MAX_ALTERNATIVES = 6
MAX_DIFF_CHARS = 20_000

STATUS_MARK = {
    "green": "✓",
    "improved": "↑",
    "neutral": "→",
    "regressed": "↓",
    "invalid": "✗",
    "failed": "○",
}


def load_report(path: str | Path) -> dict[str, Any]:
    """Read a run report written by ``search.write_report``."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "nodes" not in data or "stats" not in data:
        raise ValueError(f"{path} does not look like an Arborist run report")
    return data


# --------------------------------------------------------------------------- #
# tree helpers
# --------------------------------------------------------------------------- #


def index_nodes(report: dict) -> dict[str, dict]:
    return {n["id"]: n for n in report.get("nodes", [])}


def winning_path(report: dict) -> list[dict]:
    """The chain of accepted patches, root first, excluding the baseline."""
    nodes = index_nodes(report)
    current = nodes.get(report.get("winner_id") or "")
    chain: list[dict] = []
    while current is not None:
        if current["depth"] > 0:
            chain.append(current)
        current = nodes.get(current.get("parent_id") or "")
    return list(reversed(chain))


def rejected_branches(report: dict) -> list[dict]:
    """Everything the search tried and did not keep, worst-first by usefulness.

    Ordered so a reviewer reads the informative rejections first: a patch that
    broke a test says more than one that failed to apply.
    """
    kept = {n["id"] for n in winning_path(report)}
    rejects = [
        n
        for n in report.get("nodes", [])
        if n["depth"] > 0 and n["id"] not in kept and n["status"] != "green"
    ]
    rank = {"regressed": 0, "neutral": 1, "improved": 2, "invalid": 3}
    return sorted(rejects, key=lambda n: (rank.get(n["status"], 9), -n.get("score", 0)))


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #


def pr_title(report: dict) -> str:
    baseline = report.get("baseline") or {}
    failing = baseline.get("failed", 0) + baseline.get("errors", 0)
    path = winning_path(report)
    titles = [
        (n.get("hypothesis") or {}).get("title") or n.get("explanation", "")
        for n in path
    ]
    titles = [t.rstrip(".") for t in titles if t]

    # A chain of patches fixed several unrelated things; naming only the last
    # one would misrepresent the change.
    if not titles:
        subject = "repair failing tests"
    elif len(titles) == 1:
        subject = titles[0]
    elif len(titles) == 2:
        subject = f"{titles[0]} + 1 more"
    else:
        subject = f"{titles[0]} + {len(titles) - 1} more"
    prefix = "fix" if report.get("solved") else "wip"
    plural = "s" if failing != 1 else ""
    return f"{prefix}: {subject} ({failing} failing test{plural})"


def _edit_block(edit: dict) -> str:
    if edit.get("new_content") is not None:
        return f"`{edit['path']}` — rewritten"
    search = (edit.get("search") or "").rstrip("\n")
    replace = (edit.get("replace") or "").rstrip("\n")
    lines = [f"-{line}" for line in search.split("\n")]
    lines += [f"+{line}" for line in replace.split("\n")]
    return f"`{edit['path']}`\n\n```diff\n" + "\n".join(lines) + "\n```"


def _tests_line(report_block: dict | None) -> str:
    if not report_block:
        return "—"
    return f"{report_block['passed']}/{report_block['total']}"


def render_pr_body(report: dict, *, repo_url: str = "") -> str:
    """The pull request body: the fix, the evidence, and the road not taken."""
    baseline = report.get("baseline") or {}
    final = report.get("final") or {}
    stats = report.get("stats") or {}
    usage = report.get("usage") or {}
    path = winning_path(report)
    rejects = rejected_branches(report)

    out: list[str] = []

    # -- what and why -------------------------------------------------------
    if report.get("solved"):
        out.append(
            f"Repairs the failing suite: **{_tests_line(baseline)} → {_tests_line(final)} passing**."
        )
    else:
        out.append(
            f"⚠️ **Partial.** {_tests_line(baseline)} → {_tests_line(final)} passing — "
            "the suite is still red. Opened for review rather than merge."
        )
    out.append("")

    diagnosis = next((n.get("diagnosis") for n in path if n.get("diagnosis")), "")
    if diagnosis:
        out.append(f"> {diagnosis}")
        out.append("")

    # -- the fix ------------------------------------------------------------
    if path:
        out.append("## The fix")
        out.append("")
        for i, node in enumerate(path, 1):
            title = (node.get("hypothesis") or {}).get("title") or "patch"
            out.append(f"**{i}. {title}**")
            if node.get("explanation"):
                out.append("")
                out.append(node["explanation"])
            if node.get("fixed"):
                out.append("")
                out.append("Fixed: " + ", ".join(f"`{t}`" for t in node["fixed"]))
            out.append("")

    # -- evidence -----------------------------------------------------------
    out.append("## Evidence")
    out.append("")
    out.append("| | before | after |")
    out.append("|---|---|---|")
    out.append(f"| tests passing | {_tests_line(baseline)} | {_tests_line(final)} |")
    if baseline.get("failed_ids"):
        still = final.get("failed_ids") or []
        fixed = [t for t in baseline["failed_ids"] if t not in still]
        if fixed:
            out.append("")
            out.append("<details><summary>Tests that now pass</summary>")
            out.append("")
            out.extend(f"- `{t}`" for t in fixed)
            out.append("")
            out.append("</details>")
    out.append("")

    # -- how it was found ---------------------------------------------------
    out.append("## How this was found")
    out.append("")
    evaluated = stats.get("patches_evaluated", 0)
    depth = max((n["depth"] for n in report.get("nodes", [])), default=0)
    # Name the backend the run actually used. Claiming Nebius Sandboxes on a
    # run that used directory snapshots would be false in every pull request
    # the tool opens.
    where = (
        "[Nebius Sandboxes](https://docs.tokenfactory.nebius.com/sandboxes/overview)"
        if stats.get("backend") == "contree"
        else "a local snapshot backend"
    )
    out.append(
        f"Searched **{evaluated} candidate patches** across **{depth} levels**, "
        f"each one applied to its own fork of a single prepared checkpoint on "
        f"{where} and scored by the test suite."
    )
    if stats.get("setup_seconds_saved"):
        out.append("")
        out.append(
            f"Environment setup ran **once** ({stats.get('setup_seconds')}s) and was shared by "
            f"every branch — about **{stats['setup_seconds_saved']}s** of repeated installs avoided."
        )
    if stats.get("invalid_patches"):
        out.append("")
        n = stats["invalid_patches"]
        out.append(
            f"{n} proposed {'patch' if n == 1 else 'patches'} did not apply cleanly and "
            f"{'was' if n == 1 else 'were'} rejected before execution."
        )
    if stats.get("tavily_queries"):
        out.append("")
        out.append(
            "External documentation was consulted via Tavily for: "
            + ", ".join(f"`{q}`" for q in stats["tavily_queries"])
        )
    out.append("")

    # -- the alternatives ---------------------------------------------------
    if rejects:
        out.append(f"## Alternatives considered ({len(rejects)})")
        out.append("")
        out.append(
            "These are the theories the search tested and rejected. They are here because "
            "knowing what *didn't* work is half of a review."
        )
        out.append("")
        for node in rejects[:MAX_ALTERNATIVES]:
            out.append(_render_alternative(node))
        if len(rejects) > MAX_ALTERNATIVES:
            out.append(f"_…and {len(rejects) - MAX_ALTERNATIVES} more in the full run report._")
            out.append("")

    # -- provenance ---------------------------------------------------------
    models = usage.get("models") or {}
    by_tier = usage.get("by_tier") or {}
    used = [f"{t} ({by_tier[t]['calls']} calls)" for t in ("nano", "super", "ultra") if by_tier.get(t, {}).get("calls")]
    out.append("---")
    out.append("")
    credit = f"[Arborist]({repo_url})" if repo_url else "Arborist"
    out.append(
        f"<sub>Generated by {credit} · "
        f"NVIDIA Nemotron 3 on Nebius Token Factory — {', '.join(used) or 'no model calls'} · "
        f"{usage.get('total_tokens', 0):,} tokens · "
        f"{stats.get('sandbox_executions', 0)} sandbox executions · "
        f"run `{report.get('run_id', '')}`</sub>"
    )
    if models:
        out.append("")
        out.append("<sub>" + " · ".join(f"`{m}`" for m in sorted(set(models.values()))) + "</sub>")

    return "\n".join(out).rstrip() + "\n"


RATIONALE_LIMIT = 280


def _concise(text: str, limit: int = RATIONALE_LIMIT) -> str:
    """A rationale short enough to belong in a pull request, or nothing.

    A model occasionally reasons aloud inside the field -- "...is odd?
    Actually, 2.675 is exactly halfway... Wait:" -- and a reviewer should not
    have to read that. Short rationales pass through; a long one is cut to its
    first sentence when that sentence is a plain statement, and dropped
    otherwise. The patch's own explanation, which follows, still says what
    was tried, and the run report keeps every word.
    """
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    return first if first.endswith(".") and len(first) <= limit else ""


def _render_alternative(node: dict) -> str:
    mark = STATUS_MARK.get(node["status"], "•")
    title = (node.get("hypothesis") or {}).get("title") or node.get("note") or "patch"

    report_block = node.get("report") or {}
    passing = f"{report_block['passed']}/{report_block['total']}" if report_block else "?"

    if node["status"] == "regressed":
        reason = "broke " + ", ".join(f"`{t}`" for t in node.get("regressions", []))
    elif node["status"] == "invalid":
        reason = node.get("note") or "patch could not be applied"
    elif node["status"] == "neutral":
        reason = "no test changed state"
    else:
        # An improved branch that is not on the winning path was a real
        # candidate -- often tied with the one that was kept. Saying it "scored
        # lower" would be untrue.
        reason = f"reached {passing} but its branch did not get to green"

    block = [f"<details><summary>{mark} <b>{title}</b> — {reason}</summary>", ""]
    rationale = _concise((node.get("hypothesis") or {}).get("rationale") or "")
    if rationale:
        block.append(f"_{rationale}_")
        block.append("")
    if node.get("explanation"):
        block.append(node["explanation"])
        block.append("")
    for edit in node.get("edits", []):
        block.append(_edit_block(edit))
        block.append("")
    if node.get("fixed"):
        block.append("Did fix: " + ", ".join(f"`{t}`" for t in node["fixed"]))
        block.append("")
    block.append("</details>")
    block.append("")
    return "\n".join(block)


def render_markdown_summary(report: dict) -> str:
    """A short status line for a CI comment or a terminal."""
    baseline = report.get("baseline") or {}
    final = report.get("final") or {}
    verdict = "green" if report.get("solved") else "still red"
    return (
        f"Arborist: {_tests_line(baseline)} → {_tests_line(final)} passing ({verdict}), "
        f"{(report.get('stats') or {}).get('patches_evaluated', 0)} branches explored."
    )
