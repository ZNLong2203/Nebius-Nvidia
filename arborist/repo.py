"""Repository IO, patch application and test-result parsing."""

from __future__ import annotations

import difflib
import fnmatch
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .models import Edit, TestReport

SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    "node_modules", ".venv", "venv", "dist", "build", ".tox", ".idea", ".vscode", "runs",
}
TEXT_SUFFIXES = {
    ".py", ".pyi", ".txt", ".md", ".toml", ".cfg", ".ini", ".json", ".yaml", ".yml",
    ".js", ".ts", ".tsx", ".jsx", ".sh", ".sql", ".html", ".css", "",
}
MAX_FILE_BYTES = 400_000


def load_repo(root: str | Path, max_bytes: int = MAX_FILE_BYTES) -> dict[str, bytes]:
    """Read a working tree into ``{relative_path: bytes}``."""
    root = Path(root).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"{root} is not a directory")

    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        try:
            if path.stat().st_size > max_bytes:
                continue
            files[str(path.relative_to(root))] = path.read_bytes()
        except OSError:
            continue
    return files


def text_files(files: dict[str, bytes]) -> dict[str, str]:
    """The subset a model can usefully read, decoded."""
    out: dict[str, str] = {}
    for rel, data in files.items():
        if Path(rel).suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            out[rel] = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
    return out


def select_context(
    files: dict[str, str],
    wanted: list[str],
    *,
    budget_chars: int = 60_000,
) -> dict[str, str]:
    """Pick the files worth putting in a prompt.

    Explicitly named paths win; glob patterns are honoured so a model may ask
    for ``src/billing/*.py``. Anything that does not fit the budget is dropped
    from the end, so the first-named file is always present.
    """
    chosen: dict[str, str] = {}
    used = 0
    for want in wanted:
        want = want.strip().lstrip("./")
        if not want:
            continue
        matches = [want] if want in files else sorted(
            p for p in files if fnmatch.fnmatch(p, want) or p.endswith("/" + want) or p == want
        )
        for path in matches:
            if path in chosen or path not in files:
                continue
            body = files[path]
            if used + len(body) > budget_chars:
                continue
            chosen[path] = body
            used += len(body)
    return chosen


def render_context(files: dict[str, str]) -> str:
    """Format source files for a prompt with stable, quotable line markers."""
    blocks = []
    for path, body in files.items():
        blocks.append(f"--- FILE: {path} ---\n{body}\n--- END FILE: {path} ---")
    return "\n\n".join(blocks)


class PatchError(ValueError):
    pass


def apply_edits(files: dict[str, str], edits: list[Edit]) -> dict[str, str]:
    """Apply edits to a copy of ``files``.

    Raises :class:`PatchError` when an edit cannot be applied unambiguously.
    That check is deliberately strict and happens *before* we spend a sandbox
    execution: a malformed patch should cost tokens, not wall-clock.
    """
    if not edits:
        raise PatchError("patch contains no edits")

    updated = dict(files)
    for edit in edits:
        path = edit.path.strip().lstrip("./")
        if not path:
            raise PatchError("edit is missing a path")

        if edit.is_rewrite:
            updated[path] = edit.new_content or ""
            continue

        if edit.search is None or edit.replace is None:
            raise PatchError(f"{path}: edit needs either search/replace or new_content")
        if path not in updated:
            raise PatchError(f"{path}: file not found in repository")

        body = updated[path]
        occurrences = body.count(edit.search)
        if occurrences == 0:
            relaxed = _relaxed_find(body, edit.search)
            if relaxed is None:
                raise PatchError(f"{path}: search block not found")
            start, end = relaxed
            updated[path] = body[:start] + edit.replace + body[end:]
            continue
        if occurrences > 1:
            raise PatchError(f"{path}: search block matches {occurrences} times, needs to be unique")
        updated[path] = body.replace(edit.search, edit.replace, 1)

    if updated == files:
        raise PatchError("patch is a no-op")
    return updated


def _relaxed_find(body: str, needle: str) -> tuple[int, int] | None:
    """Second chance for a search block whose indentation drifted.

    Models reproduce code almost exactly but occasionally normalise leading
    whitespace. Match on stripped lines and map back to real offsets.
    """
    needle_lines = [line.strip() for line in needle.strip("\n").split("\n") if line.strip()]
    if not needle_lines:
        return None
    body_lines = body.split("\n")
    stripped = [line.strip() for line in body_lines]

    hits = []
    for i in range(len(stripped) - len(needle_lines) + 1):
        if stripped[i : i + len(needle_lines)] == needle_lines:
            hits.append(i)
    if len(hits) != 1:
        return None

    start_line = hits[0]
    end_line = start_line + len(needle_lines)
    start = sum(len(line) + 1 for line in body_lines[:start_line])
    end = sum(len(line) + 1 for line in body_lines[:end_line])
    return start, min(end, len(body))


def changed_files(before: dict[str, str], after: dict[str, str]) -> dict[str, str]:
    return {p: body for p, body in after.items() if before.get(p) != body}


def unified_diff(before: dict[str, str], after: dict[str, str]) -> str:
    """A git-style diff of everything the winning branch changed."""
    chunks: list[str] = []
    for path in sorted(set(before) | set(after)):
        old = before.get(path, "")
        new = after.get(path, "")
        if old == new:
            continue
        diff = difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=3,
        )
        chunks.append("".join(diff))
    return "".join(chunks)


# --------------------------------------------------------------------------- #
# Test result parsing
# --------------------------------------------------------------------------- #

_SUMMARY = re.compile(
    r"(?:^|\s)(\d+)\s+(passed|failed|error|errors|skipped|xfailed|xpassed)\b", re.I
)
_FAILED_LINE = re.compile(r"^(?:FAILED|ERROR)\s+(\S+)", re.M)


def parse_junit(xml_bytes: bytes) -> TestReport | None:
    """Parse a pytest ``--junitxml`` report.

    Preferred over scraping stdout because it yields *per-test identities*,
    which is what lets the scorer tell a real improvement from a trade: a patch
    that fixes two tests and breaks one is not progress.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None

    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    report = TestReport()
    for suite in suites:
        for case in suite.iter("testcase"):
            classname = (case.get("classname") or "").strip()
            name = (case.get("name") or "").strip()
            test_id = f"{classname}::{name}" if classname else name
            report.total += 1
            if case.find("failure") is not None:
                report.failed += 1
                report.failed_ids.add(test_id)
            elif case.find("error") is not None:
                report.errors += 1
                report.failed_ids.add(test_id)
            elif case.find("skipped") is not None:
                report.skipped += 1
            else:
                report.passed += 1
                report.passed_ids.add(test_id)
    if report.total == 0:
        return None
    return report


def parse_pytest_text(stdout: str, stderr: str = "", exit_code: int = 1) -> TestReport:
    """Fallback parser for when no junit file was produced."""
    blob = f"{stdout}\n{stderr}"
    report = TestReport(raw_tail=blob[-4000:])

    for count, kind in _SUMMARY.findall(blob):
        n = int(count)
        kind = kind.lower()
        if kind == "passed":
            report.passed = n
        elif kind == "failed":
            report.failed = n
        elif kind in {"error", "errors"}:
            report.errors = n
        elif kind == "skipped":
            report.skipped = n

    report.failed_ids = set(_FAILED_LINE.findall(blob))
    report.total = report.passed + report.failed + report.errors + report.skipped

    if "error" in blob.lower() and report.total == 0:
        report.collection_error = True
    if report.total == 0 and exit_code == 0:
        report.collection_error = True
    return report
