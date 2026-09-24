"""Repository IO, patch application and test-result parsing."""

from __future__ import annotations

import ast
import difflib
import fnmatch
import io
import re
import tokenize
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
    fill: bool = True,
) -> dict[str, str]:
    """Pick the files worth putting in a prompt.

    Explicitly named paths win; glob patterns are honoured so a model may ask
    for ``src/billing/*.py``. Anything that does not fit the budget is dropped
    from the end, so the first-named file is always present.

    ``fill`` then spends whatever budget is left on the rest of the repository.
    Without it, a heuristic that names two files silently hides everything else,
    and a model asked to patch a file it was never shown will invent one.
    """
    chosen: dict[str, str] = {}
    used = 0
    for want in wanted:
        want = _normalise_path(want)
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

    if fill:
        remaining = [p for p in sorted(files) if p not in chosen]
        # A repository that fits keeps plain path order, so small projects see
        # exactly the prompt they always did. One that does not fit spends the
        # budget on what is most likely to matter, instead of on whatever sorts
        # first -- which in a real project is .github/, changelog/ and doc/.
        if used + sum(len(files[p]) for p in remaining) > budget_chars:
            remaining = rank_paths(remaining, anchors=list(chosen))
        for path in remaining:
            body = files[path]
            if used + len(body) > budget_chars:
                continue
            chosen[path] = body
            used += len(body)
    return chosen


DOC_SUFFIXES = {".md", ".rst", ".txt", ".html", ".css", ""}
DOC_DIRS = ("doc/", "docs/", "changelog/", "changes/", "examples/", "benchmarks/", "bench/", ".github/")


def _is_doc(path: str) -> bool:
    return Path(path).suffix.lower() in DOC_SUFFIXES or path.startswith(DOC_DIRS)


def _is_test(path: str) -> bool:
    name = Path(path).name
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py" or any(
        part in {"tests", "testing", "test"} for part in Path(path).parts[:-1]
    )


def rank_paths(paths: list[str], anchors: list[str] | tuple[str, ...] = ()) -> list[str]:
    """Most useful first: code near the anchors, other source, tests, then docs."""
    homes = {Path(a).parent for a in anchors}

    def near(path: str) -> bool:
        parent = Path(path).parent
        return any(parent == home or home in parent.parents for home in homes if str(home) != ".")

    return sorted(paths, key=lambda p: (_is_doc(p), not near(p), _is_test(p), len(Path(p).parts), p))


def file_index(paths, limit: int = 200) -> list[str]:
    """The repository listing shown to the model: every path when it fits."""
    ordered = sorted(paths)
    return ordered if len(ordered) <= limit else rank_paths(ordered)[:limit]


def render_context(files: dict[str, str]) -> str:
    """Format source files for a prompt with stable, quotable line markers."""
    blocks = []
    for path, body in files.items():
        blocks.append(f"--- FILE: {path} ---\n{body}\n--- END FILE: {path} ---")
    return "\n\n".join(blocks)


class PatchError(ValueError):
    pass


def apply_edits(
    files: dict[str, str], edits: list[Edit], protected: list[str] | tuple[str, ...] = ()
) -> dict[str, str]:
    """Apply edits to a copy of ``files``.

    Raises :class:`PatchError` when an edit cannot be applied unambiguously.
    That check is deliberately strict and happens *before* we spend a sandbox
    execution: a malformed patch should cost tokens, not wall-clock.

    ``protected`` holds glob patterns for files the patch may not touch --
    typically the tests that define success. A prompt can ask a model not to
    edit the oracle; only a check here can guarantee it.
    """
    if not edits:
        raise PatchError("patch contains no edits")

    updated = dict(files)
    for edit in edits:
        path = _normalise_path(edit.path)
        if not path:
            raise PatchError("edit is missing a path")

        if edit.is_rewrite:
            _refuse_protected(path, protected)
            content = edit.new_content or ""
            if path in updated:
                content = minimise_rewrite(path, updated[path], content)
            updated[path] = content
            continue

        if edit.search is None or edit.replace is None:
            raise PatchError(f"{path}: edit needs either search/replace or new_content")
        if path not in updated:
            resolved = _resolve_path(path, updated)
            if resolved is None:
                raise PatchError(f"{path}: file not found in repository")
            path = resolved
        _refuse_protected(path, protected)

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
        raise PatchError("patch is a no-op (changes that only reformat code are dropped)")

    _reject_broken_syntax(files, updated)
    return updated


def minimise_rewrite(path: str, before: str, after: str) -> str:
    """Undo the parts of a whole-file rewrite that change nothing but formatting.

    A model sending a whole file restyles it on the way through -- triple quotes
    swapped to dodge JSON escaping, blank lines moved -- and every one of those
    lands in the diff a reviewer has to read. Each changed region is put back
    to the original if, and only if, the file still parses to the same syntax
    tree and keeps the same comments with it reverted. What remains is exactly
    the part of the rewrite that means something.
    """
    if not path.endswith(".py") or before == after:
        return after
    try:
        target = _fingerprint(after)
    except (SyntaxError, ValueError, tokenize.TokenError):
        return after  # the syntax gate will say why

    # Quotes first. A multi-line docstring's opening and closing quotes land in
    # different changed regions, and reverting either one alone does not parse,
    # so the region pass below cannot undo a quote swap by itself.
    requoted = _restore_string_spelling(before, after)
    if requoted != after:
        try:
            if _fingerprint(requoted) == target:
                after = requoted
        except (SyntaxError, ValueError, tokenize.TokenError):
            pass

    old = before.splitlines(keepends=True)
    current = after.splitlines(keepends=True)
    opcodes = difflib.SequenceMatcher(a=old, b=current, autojunk=False).get_opcodes()
    # From the end, so reverting one region never shifts the ones before it.
    for tag, i1, i2, j1, j2 in reversed(opcodes):
        if tag == "equal":
            continue
        candidate = current[:j1] + old[i1:i2] + current[j2:]
        try:
            if _fingerprint("".join(candidate)) == target:
                current = candidate
        except (SyntaxError, ValueError, tokenize.TokenError):
            continue
    return "".join(current)


def _restore_string_spelling(before: str, after: str) -> str:
    """Give each string literal in ``after`` its spelling in ``before`` when the value is the same.

    Token streams are aligned with string literals compared by value, so a
    docstring whose triple quotes were swapped still matches the original;
    where it does and only the spelling differs, the original spelling is put
    back. Nothing else is touched.
    """
    try:
        old_tokens = list(tokenize.generate_tokens(io.StringIO(before).readline))
        new_tokens = list(tokenize.generate_tokens(io.StringIO(after).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return after

    def key(token: tokenize.TokenInfo) -> tuple[int, str]:
        if token.type == tokenize.STRING:
            try:
                return token.type, repr(ast.literal_eval(token.string))
            except (ValueError, SyntaxError):
                return token.type, token.string
        if token.type in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
            return token.type, ""
        return token.type, token.string

    matcher = difflib.SequenceMatcher(
        a=[key(t) for t in old_tokens], b=[key(t) for t in new_tokens], autojunk=False
    )
    swaps: list[tuple[tuple[int, int], tuple[int, int], str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for step in range(j2 - j1):
                original, rewritten = old_tokens[i1 + step], new_tokens[j1 + step]
                if rewritten.type == tokenize.STRING and original.string != rewritten.string:
                    swaps.append((rewritten.start, rewritten.end, original.string))
        elif tag == "replace":
            # A changed region with as many strings on each side: pair them in
            # order. The words may have changed; the quotes need not have. (The
            # region can hold other tokens too -- an import inserted under a
            # docstring lands in the same one.)
            old_strings = [t for t in old_tokens[i1:i2] if t.type == tokenize.STRING]
            new_strings = [t for t in new_tokens[j1:j2] if t.type == tokenize.STRING]
            if len(old_strings) == len(new_strings):
                for original, rewritten in zip(old_strings, new_strings):
                    respelled = _respell(original.string, rewritten.string)
                    if respelled is not None:
                        swaps.append((rewritten.start, rewritten.end, respelled))
    if not swaps:
        return after

    starts = [0]
    for line in after.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))

    def offset(position: tuple[int, int]) -> int:
        return starts[position[0] - 1] + position[1]

    out = after
    for start, end, text in sorted(swaps, key=lambda swap: swap[0], reverse=True):
        out = out[: offset(start)] + text + out[offset(end) :]
    return out


def _respell(original: str, rewritten: str) -> str | None:
    """``rewritten``'s value in ``original``'s quotes, when that is safe to do.

    A docstring whose words changed still should not have its quotes changed
    as well. Only plain delimiters are swapped, only when the prefix is the
    same, and only if the result evaluates to exactly the rewritten value.
    """
    def split(token: str) -> tuple[str, str, str] | None:
        prefix = token[: len(token) - len(token.lstrip("rRbBuU"))]
        rest = token[len(prefix) :]
        for quote in ('"""', "'''", '"', "'"):
            if rest.startswith(quote) and rest.endswith(quote) and len(rest) >= 2 * len(quote):
                return prefix, quote, rest[len(quote) : -len(quote)]
        return None

    old, new = split(original), split(rewritten)
    if not old or not new or old[0].lower() != new[0].lower() or old[1] == new[1]:
        return None
    candidate = new[0] + old[1] + new[2] + old[1]
    try:
        return candidate if ast.literal_eval(candidate) == ast.literal_eval(rewritten) else None
    except (ValueError, SyntaxError):
        return None


def _fingerprint(source: str) -> tuple[str, tuple[str, ...]]:
    """What Python sees (the tree, positions ignored) plus what a reader sees and it does not."""
    comments = tuple(
        token.string
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT
    )
    return ast.dump(ast.parse(source)), comments


def _normalise_path(raw: str) -> str:
    """``./a/b`` and ``/a/b`` mean ``a/b``; ``.coveragerc`` stays ``.coveragerc``.

    ``str.lstrip("./")`` strips a character *set*, which quietly turned every
    dotfile into a different, new file.
    """
    path = raw.strip()
    while path.startswith("./"):
        path = path[2:]
    return path.lstrip("/")


def is_protected(path: str, protected: list[str] | tuple[str, ...]) -> bool:
    """Match like .gitignore: a pattern without a slash matches any basename."""
    name = path.rsplit("/", 1)[-1]
    for pattern in protected:
        pattern = _normalise_path(pattern)
        if fnmatch.fnmatch(path, pattern) or ("/" not in pattern and fnmatch.fnmatch(name, pattern)):
            return True
    return False


def _refuse_protected(path: str, protected: list[str] | tuple[str, ...]) -> None:
    if protected and is_protected(path, protected):
        raise PatchError(
            f"{path}: this file is protected -- it defines what a correct repair is. "
            "Change the code under test, not the test."
        )


def _reject_broken_syntax(before: dict[str, str], after: dict[str, str]) -> None:
    """Refuse a patch that leaves a Python file unparseable.

    A model asked to restate a whole file sometimes mangles the escaping or
    truncates it. Without this check the agent then spends its remaining budget
    repairing damage it caused itself -- one observed run burned six patches on
    exactly that, having started from a file that merely needed a decorator
    changed. Catching it here costs tokens; catching it after execution costs a
    sandbox run and a poisoned branch.
    """
    for path, body in after.items():
        if not path.endswith(".py") or before.get(path) == body:
            continue
        try:
            ast.parse(body)
        except SyntaxError as exc:
            was_valid = True
            if path in before:
                try:
                    ast.parse(before[path])
                except SyntaxError:
                    was_valid = False
            if was_valid:
                raise PatchError(
                    f"{path}: the patched file is not valid Python "
                    f"(line {exc.lineno}: {exc.msg}). Send the file again, complete and unescaped."
                ) from exc


def _resolve_path(path: str, files: dict[str, str]) -> str | None:
    """Match a path the model shortened, when exactly one file can be meant.

    Models drop a source root -- ``billing/money.py`` for ``src/billing/money.py``
    -- often enough to be worth recovering. Only an unambiguous match counts; a
    guess that could mean two files is worse than a rejected patch.
    """
    candidates = [p for p in files if p.endswith("/" + path)]
    if len(candidates) == 1:
        return candidates[0]
    tail = path.rsplit("/", 1)[-1]
    candidates = [p for p in files if p.rsplit("/", 1)[-1] == tail]
    return candidates[0] if len(candidates) == 1 else None


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
    r"(?:^|\s)(\d+)\s+(passed|failed|error|errors|skipped|xfailed|xpassed)\b", re.IGNORECASE
)
_FAILED_LINE = re.compile(r"^(?:FAILED|ERROR)\s+(\S+)", re.MULTILINE)


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
