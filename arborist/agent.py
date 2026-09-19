"""The model-facing half: diagnosis, patch proposal and adjudication.

Each function maps one-to-one onto a Nemotron tier, and every one of them
returns plain dataclasses so the search never handles raw model output.
"""

from __future__ import annotations

from .llm import LLM
from .models import Edit, Hypothesis, TestReport, new_id
from .repo import render_context
from .tools.tavily import TavilyClient

DIAGNOSE_SCHEMA = {
    "type": "object",
    "properties": {
        "root_cause": {"type": "string"},
        "confidence": {
            "type": "number",
            "description": "0-1, or 0-100; how sure you are of the root cause",
        },
        "needs_external_docs": {"type": "boolean"},
        "external_package": {
            "type": "string",
            "description": "the third-party package the failure originates in, or empty",
        },
        "search_query": {"type": "string"},
        "request_files": {"type": "array", "items": {"type": "string"}},
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "rationale": {"type": "string"},
                    "target_files": {"type": "array", "items": {"type": "string"}},
                    "strategy": {"type": "string"},
                },
                "required": ["title", "strategy"],
            },
        },
    },
    # These three drive the lookup policy, and a field that is merely optional
    # is a field the model omits: asked with only root_cause and hypotheses
    # required, Nemotron returned exactly those two and nothing else, so the
    # policy could never fire.
    "required": ["root_cause", "confidence", "needs_external_docs", "external_package", "hypotheses"],
}

PATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "explanation": {"type": "string"},
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "search": {"type": "string"},
                    "replace": {"type": "string"},
                    "new_content": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    },
    "required": ["edits"],
}

DIAGNOSE_SYSTEM = """You are a senior engineer triaging a red test suite.

You do not write code in this step. You produce DISTINCT hypotheses that are
worth exploring in parallel, because each one will be turned into a patch and
run in its own sandbox branch. Two hypotheses that would produce the same edit
are wasted branches -- make them genuinely different theories of the bug.

Rules:
- The SOURCE you are shown is the CURRENT state of the repository, including
  every patch already applied on this branch. Read it before theorising: a fix
  that is already present is not a hypothesis, and re-applying one breaks
  working code.
- Ground every claim in the failure output or the source you were shown. Never
  invent a file, symbol or line you have not seen.
- Prefer fixing the source under test, not the test, unless the failure output
  proves the test encodes a wrong expectation.
- Name the third-party package in external_package whenever the failure
  originates inside one, even if you believe you already know the fix. Your
  knowledge of a library is a snapshot of when you were trained; the pin in this
  repository may be newer.
- Set needs_external_docs when the repository genuinely cannot tell you why.
- Whenever either applies, give a precise search_query naming the library, the
  version and the symbol.
- If you need to see a file you were not given, list it in request_files.

Reply with JSON only."""

PATCH_SYSTEM = """You are implementing ONE specific hypothesis as a minimal patch.

Output format, strictly:
{"explanation": "...", "edits": [{"path": "...", "search": "...", "replace": "..."}]}

- `search` must be copied character-for-character from the file you were shown,
  including indentation, and must appear EXACTLY ONCE in that file. Include
  enough surrounding lines to make it unique.
- `replace` is what those lines become.
- When a file is SHORT (you will be told which ones), do not quote a snippet at
  all -- send {"path": "...", "new_content": "<the entire file>"} instead.
  Reproducing a whole short file is more reliable than reproducing an exact
  fragment of it, and a fragment that does not match costs the branch.
- Change as little as possible. Do not reformat, do not rename, do not add
  comments explaining the fix, do not touch unrelated code.
- Implement only the hypothesis you were given. Another branch is handling the
  other theories; overlapping edits make the comparison meaningless.

Reply with JSON only."""

ADJUDICATE_SYSTEM = """You are choosing between candidate repairs that the test
suite could not separate -- they scored identically.

Judge on: correctness of the underlying reasoning, blast radius, and whether the
change would survive code review. A patch that makes tests pass by weakening an
assertion, catching and swallowing an exception, or special-casing the test
input is WORSE than a failing patch: say so.

Reply with JSON only:
{"winner": "<node id>", "reason": "...", "suspicious": ["<node id>", ...]}"""


def _failure_digest(report: TestReport | None, stdout: str, stderr: str, limit: int = 6000) -> str:
    head = ""
    if report:
        head = (
            f"{report.passed}/{report.total} passing, {report.failed} failed, "
            f"{report.errors} errored.\nFailing tests: "
            + (", ".join(sorted(report.failed_ids)[:25]) or "(not identified)")
            + "\n\n"
        )
    body = (stdout or "") + ("\n" + stderr if stderr else "")
    return head + body[-limit:]


def diagnose(
    llm: LLM,
    *,
    tier: str,
    test_command: str,
    report: TestReport | None,
    stdout: str,
    stderr: str,
    sources: dict[str, str],
    file_index: list[str],
    tavily: TavilyClient | None = None,
    parent_attempts: list[str] | None = None,
    fanout: int = 4,
) -> tuple[list[Hypothesis], dict]:
    """Ask a model why the suite is red and how the repair could branch."""
    attempts = ""
    if parent_attempts:
        # Ahead of the source, not buried after it: this is the context most
        # likely to stop the model re-proposing a change that is already applied.
        attempts = (
            "ALREADY TRIED ON THIS BRANCH -- these changes are already in the source "
            "below, or were rejected. Do not propose any of them again:\n"
            + "\n".join(f"- {a}" for a in parent_attempts)
            + "\n\n"
        )

    user = f"""Test command: `{test_command}`

FAILURE OUTPUT
{_failure_digest(report, stdout, stderr)}

REPOSITORY FILES
{", ".join(file_index[:200])}

{attempts}SOURCE (current state of the branch)
{render_context(sources)}

Produce at most {fanout} hypotheses, ordered most to least likely.
Each one must address a failure that is STILL failing in the output above."""

    data = llm.json(
        "super" if tier == "super" else tier, DIAGNOSE_SYSTEM, user, DIAGNOSE_SCHEMA, max_tokens=6000
    )

    # When to look something up.
    #
    # Asking only when the model volunteers "I don't know" is too narrow: a model
    # is confidently wrong about a library exactly when its training snapshot
    # predates the version in the repository, and that is the case worth
    # catching. So the lookup also fires when the failure is attributed to a
    # third-party package at all, or when the model's own stated confidence in
    # its diagnosis is low. One cheap search is worth less than one wrong patch
    # and the sandbox execution behind it.
    evidence = ""
    # Nemotron answers this on a 0-100 scale despite the field being described as
    # a probability, so accept either and normalise.
    raw_confidence = data.get("confidence")
    confidence = None
    if isinstance(raw_confidence, (int, float)) and not isinstance(raw_confidence, bool):
        confidence = raw_confidence / 100 if raw_confidence > 1 else float(raw_confidence)
    low_confidence = confidence is not None and confidence < 0.6
    reason = (
        "model asked"
        if data.get("needs_external_docs")
        else "third-party package implicated"
        if (data.get("external_package") or "").strip()
        else "low confidence in the diagnosis"
        if low_confidence
        else ""
    )
    if tavily and tavily.enabled and reason:
        query = (data.get("search_query") or "").strip()
        if not query and (data.get("external_package") or "").strip():
            query = f"{data['external_package']} {data.get('root_cause', '')}".strip()[:200]
        if query:
            answer, hits = tavily.search(query)
            evidence = tavily.render(answer, hits)
            if evidence:
                # Re-run diagnosis once, now with the missing outside knowledge.
                data = llm.json(
                    "super" if tier == "super" else tier,
                    DIAGNOSE_SYSTEM,
                    user + f"\n\nEXTERNAL DOCUMENTATION (retrieved for: {query})\n{evidence[:6000]}",
                    DIAGNOSE_SCHEMA,
                    max_tokens=6000,
                )

    hypotheses = _read_hypotheses(data, fanout)
    attempts = 1

    if not hypotheses:
        # A diagnosis that yields nothing ends the expansion and, at the root,
        # the whole run -- having already paid for the call. One retry at a
        # higher temperature is far cheaper than the run it rescues.
        attempts = 2
        data = llm.json(
            "super" if tier == "super" else tier,
            DIAGNOSE_SYSTEM,
            user
            + "\n\nYour previous reply contained no usable hypotheses. Return at least one, "
            "as a JSON object with a non-empty `hypotheses` array. Each entry needs `title` "
            "and `strategy`.",
            DIAGNOSE_SCHEMA,
            temperature=0.6,
            max_tokens=6000,
        )
        hypotheses = _read_hypotheses(data, fanout)

    meta = {
        "root_cause": (data.get("root_cause") or "").strip(),
        "confidence": confidence,
        "request_files": [str(p) for p in (data.get("request_files") or []) if p],
        "searched": bool(evidence),
        "search_reason": reason if evidence else "",
        "external_package": (data.get("external_package") or "").strip(),
        "search_query": (data.get("search_query") or "").strip(),
        "evidence": evidence[:4000],
        "attempts": attempts,
        # Enough to tell "the model answered something unexpected" from "the
        # model answered nothing at all", without storing its prose.
        "reply_keys": sorted(data) if isinstance(data, dict) else [],
    }
    return hypotheses, meta


def _read_hypotheses(data: dict, fanout: int) -> list[Hypothesis]:
    hypotheses: list[Hypothesis] = []
    for raw in (data.get("hypotheses") or [])[:fanout]:
        if not isinstance(raw, dict):
            continue
        title = (raw.get("title") or "").strip()
        strategy = (raw.get("strategy") or "").strip()
        if not title and not strategy:
            continue
        hypotheses.append(
            Hypothesis(
                id=new_id("h"),
                title=title or strategy[:80],
                rationale=(raw.get("rationale") or "").strip(),
                target_files=[str(p) for p in (raw.get("target_files") or []) if p],
                strategy=strategy,
            )
        )
    return hypotheses


REWRITE_LINE_LIMIT = 80


def propose_patch(
    llm: LLM,
    *,
    tier: str,
    hypothesis: Hypothesis,
    root_cause: str,
    test_command: str,
    report: TestReport | None,
    stdout: str,
    stderr: str,
    sources: dict[str, str],
    evidence: str = "",
    retry_note: str = "",
) -> tuple[list[Edit], str]:
    """Turn one hypothesis into one concrete patch.

    ``retry_note`` carries back the reason a previous attempt could not be
    applied. A patch that does not apply teaches the search nothing and the next
    expansion cheerfully repeats it, so the reason has to come back to the
    model rather than only into the report.
    """
    extra = f"\n\nEXTERNAL DOCUMENTATION\n{evidence[:4000]}" if evidence else ""

    short = [p for p, body in sources.items() if len(body.splitlines()) <= REWRITE_LINE_LIMIT]
    rewrite_hint = (
        "\n\nSHORT FILES -- for these, send `new_content` with the whole file rather "
        "than a search/replace pair:\n" + "\n".join(f"- {p}" for p in short)
        if short
        else ""
    )
    repair = f"\n\nA PREVIOUS ATTEMPT FAILED TO APPLY: {retry_note}\nDo not repeat it." if retry_note else ""
    user = f"""Test command: `{test_command}`

DIAGNOSIS
{root_cause}

YOUR ASSIGNED HYPOTHESIS
Title: {hypothesis.title}
Rationale: {hypothesis.rationale}
Strategy: {hypothesis.strategy}
Files to touch: {", ".join(hypothesis.target_files) or "(decide from the source below)"}

FAILURE OUTPUT
{_failure_digest(report, stdout, stderr, limit=3500)}

SOURCE
{render_context(sources)}{extra}{rewrite_hint}{repair}

Write the minimal patch that implements this hypothesis."""

    data = llm.json(tier, PATCH_SYSTEM, user, PATCH_SCHEMA, temperature=0.35, max_tokens=8000)

    edits: list[Edit] = []
    for raw in data.get("edits") or []:
        if not isinstance(raw, dict):
            continue
        path = (raw.get("path") or "").strip()
        if not path:
            continue
        new_content = raw.get("new_content")
        search = raw.get("search")
        replace = raw.get("replace")
        # A `search` with no `replace` is ambiguous: it could be a deletion, or a
        # reply that was cut off. Dropping it costs one branch; acting on it
        # could delete working code.
        if new_content is None and (search is None or replace is None):
            continue
        edits.append(Edit(path=path, search=search, replace=replace, new_content=new_content))
    return edits, (data.get("explanation") or "").strip()


def adjudicate(llm: LLM, *, candidates: list[dict], test_command: str) -> dict:
    """Break a tie between branches the tests scored the same.

    This is the only place Ultra is used on the happy path, and only when the
    objective signal has run out.
    """
    rendered = []
    for c in candidates:
        rendered.append(
            f"""### Candidate {c['id']}
Hypothesis: {c['hypothesis']}
Explanation: {c['explanation']}
Score: {c['score']}  (fixed: {c['fixed']}, regressions: {c['regressions']})
Diff:
{c['diff'][:4000]}"""
        )
    user = f"Test command: `{test_command}`\n\n" + "\n\n".join(rendered)
    return llm.json("ultra", ADJUDICATE_SYSTEM, user, temperature=0.1, max_tokens=4000)
