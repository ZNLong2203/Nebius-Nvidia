import textwrap

import pytest

from arborist.models import Edit, TestReport
from arborist.repo import (
    PatchError,
    apply_edits,
    changed_files,
    is_protected,
    parse_junit,
    parse_pytest_text,
    select_context,
    text_files,
    unified_diff,
)

SAMPLE = textwrap.dedent(
    """\
    def add(a, b):
        return a - b


    def mul(a, b):
        return a * b
    """
)


def test_apply_edits_replaces_a_unique_block():
    out = apply_edits({"m.py": SAMPLE}, [Edit(path="m.py", search="    return a - b", replace="    return a + b")])
    assert "return a + b" in out["m.py"]
    assert "return a * b" in out["m.py"]


def test_apply_edits_rejects_an_ambiguous_block():
    body = "x = 1\nx = 1\n"
    with pytest.raises(PatchError, match="matches 2 times"):
        apply_edits({"m.py": body}, [Edit(path="m.py", search="x = 1", replace="x = 2")])


def test_apply_edits_rejects_a_missing_block():
    with pytest.raises(PatchError, match="not found"):
        apply_edits({"m.py": SAMPLE}, [Edit(path="m.py", search="return a / b", replace="pass")])


def test_apply_edits_rejects_a_missing_file():
    with pytest.raises(PatchError, match="file not found"):
        apply_edits({"m.py": SAMPLE}, [Edit(path="other.py", search="a", replace="b")])


def test_apply_edits_rejects_a_noop():
    with pytest.raises(PatchError, match="no-op"):
        apply_edits({"m.py": SAMPLE}, [Edit(path="m.py", search="    return a - b", replace="    return a - b")])


def test_apply_edits_rejects_an_empty_patch():
    with pytest.raises(PatchError, match="no edits"):
        apply_edits({"m.py": SAMPLE}, [])


def test_apply_edits_tolerates_reindented_search_blocks():
    """Models reproduce code faithfully but sometimes normalise indentation."""
    out = apply_edits(
        {"m.py": SAMPLE},
        [Edit(path="m.py", search="return a - b", replace="    return a + b")],
    )
    assert "return a + b" in out["m.py"]


def test_apply_edits_supports_whole_file_rewrites():
    out = apply_edits({"m.py": SAMPLE}, [Edit(path="m.py", new_content="print('hi')\n")])
    assert out["m.py"] == "print('hi')\n"


def test_apply_edits_can_create_a_new_file():
    out = apply_edits({"m.py": SAMPLE}, [Edit(path="new.py", new_content="X = 1\n")])
    assert out["new.py"] == "X = 1\n"


def test_changed_files_only_returns_the_difference():
    after = {"a.py": "1", "b.py": "2"}
    assert changed_files({"a.py": "1", "b.py": "9"}, after) == {"b.py": "2"}


def test_unified_diff_is_readable_and_scoped():
    diff = unified_diff({"m.py": SAMPLE}, apply_edits({"m.py": SAMPLE}, [Edit(path="m.py", search="    return a - b", replace="    return a + b")]))
    assert "a/m.py" in diff and "+    return a + b" in diff
    assert "mul" not in diff.split("@@")[0]


JUNIT = b"""<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" errors="0" failures="1" skipped="1" tests="4">
<testcase classname="tests.test_x" name="test_ok" time="0.01"/>
<testcase classname="tests.test_x" name="test_also_ok" time="0.01"/>
<testcase classname="tests.test_x" name="test_bad" time="0.01"><failure message="boom">trace</failure></testcase>
<testcase classname="tests.test_x" name="test_skip" time="0.0"><skipped/></testcase>
</testsuite></testsuites>"""


def test_parse_junit_extracts_test_identities():
    report = parse_junit(JUNIT)
    assert report.total == 4
    assert report.passed == 2
    assert report.failed == 1
    assert report.skipped == 1
    assert "tests.test_x::test_bad" in report.failed_ids
    assert "tests.test_x::test_ok" in report.passed_ids
    assert not report.green


def test_parse_junit_returns_none_for_garbage():
    assert parse_junit(b"not xml at all") is None


def test_parse_junit_detects_a_green_suite():
    xml = b'<testsuite tests="1"><testcase classname="t" name="a"/></testsuite>'
    assert parse_junit(xml).green


def test_parse_pytest_text_is_a_usable_fallback():
    out = "FAILED tests/test_a.py::test_one - assert 1 == 2\n1 failed, 3 passed in 0.10s"
    report = parse_pytest_text(out, "", 1)
    assert report.passed == 3
    assert report.failed == 1
    assert report.total == 4
    assert "tests/test_a.py::test_one" in report.failed_ids


def test_select_context_honours_order_and_budget():
    files = {"a.py": "x" * 100, "b.py": "y" * 100, "c.py": "z" * 100}
    chosen = select_context(files, ["b.py", "a.py", "c.py"], budget_chars=250)
    assert list(chosen) == ["b.py", "a.py"]


def test_select_context_supports_globs():
    files = {"src/x.py": "1", "src/y.py": "2", "docs/z.md": "3"}
    chosen = select_context(files, ["src/*.py"], fill=False)
    assert set(chosen) == {"src/x.py", "src/y.py"}


def test_select_context_fills_the_rest_of_the_budget():
    """A heuristic that names two files must not hide the rest of the repo.

    A model asked to patch a file it was never shown will invent one, so any
    leftover budget goes to whatever else fits.
    """
    files = {"src/x.py": "1", "src/y.py": "2", "docs/z.md": "3"}
    chosen = select_context(files, ["src/x.py"])
    assert next(iter(chosen)) == "src/x.py", "the named file still comes first"
    assert set(chosen) == set(files)


def test_select_context_fill_respects_the_budget():
    files = {"a.py": "x" * 100, "big.py": "y" * 500}
    chosen = select_context(files, ["a.py"], budget_chars=200)
    assert set(chosen) == {"a.py"}


def test_apply_edits_recovers_a_path_missing_its_source_root():
    """Models drop `src/` often enough to be worth recovering."""
    files = {"src/billing/money.py": SAMPLE}
    out = apply_edits(
        files, [Edit(path="billing/money.py", search="    return a - b", replace="    return a + b")]
    )
    assert "return a + b" in out["src/billing/money.py"]
    assert "billing/money.py" not in out, "the shortened path must not become a second file"


def test_apply_edits_recovers_a_bare_filename():
    files = {"src/deep/util.py": SAMPLE}
    out = apply_edits(files, [Edit(path="util.py", search="    return a - b", replace="    return a + b")])
    assert "return a + b" in out["src/deep/util.py"]


def test_apply_edits_refuses_an_ambiguous_shortened_path():
    """A guess that could mean two files is worse than a rejected patch."""
    files = {"a/util.py": SAMPLE, "b/util.py": SAMPLE}
    with pytest.raises(PatchError, match="file not found"):
        apply_edits(files, [Edit(path="util.py", search="    return a - b", replace="    return a + b")])


def test_text_files_skips_binaries():
    assert text_files({"a.py": b"ok", "b.png": b"\x89PNG"}) == {"a.py": "ok"}


def test_test_report_green_requires_tests():
    assert not TestReport(total=0).green
    assert TestReport(total=2, passed=2).green


def test_apply_edits_rejects_a_rewrite_that_breaks_the_file():
    """A mangled whole-file rewrite otherwise costs a sandbox run and poisons the branch."""
    with pytest.raises(PatchError, match="not valid Python"):
        apply_edits({"m.py": SAMPLE}, [Edit(path="m.py", new_content="def add(a, b:\n    return")])


def test_the_rejection_tells_the_model_what_to_do():
    try:
        apply_edits({"m.py": SAMPLE}, [Edit(path="m.py", new_content="x = (1\n")])
    except PatchError as exc:
        assert "complete and unescaped" in str(exc)
    else:
        raise AssertionError("expected a PatchError")


def test_a_file_that_was_already_broken_is_not_blamed_on_the_patch():
    """Repairing a file that does not parse is a legitimate thing to be doing."""
    broken = "def f(:\n    pass\n"
    out = apply_edits({"m.py": broken}, [Edit(path="m.py", new_content="def f():\n    pass\n")])
    assert out["m.py"] == "def f():\n    pass\n"


def test_non_python_files_are_not_syntax_checked():
    out = apply_edits({"a.py": SAMPLE, "r.txt": "x"}, [Edit(path="r.txt", new_content="{{ not python")])
    assert out["r.txt"] == "{{ not python"


# --------------------------------------------------------------------------- #
# protected paths
# --------------------------------------------------------------------------- #

TEST_FILE = "def test_add():\n    assert add(1, 2) == 3\n"


def test_a_protected_file_cannot_be_edited():
    files = {"src/app.py": SAMPLE, "tests/test_app.py": TEST_FILE}
    with pytest.raises(PatchError, match="protected"):
        apply_edits(files, [Edit(path="tests/test_app.py", search="== 3", replace="== -1")], protected=["tests/*"])


def test_a_protected_file_cannot_be_rewritten_either():
    files = {"tests/test_app.py": TEST_FILE}
    with pytest.raises(PatchError, match="protected"):
        apply_edits(files, [Edit(path="tests/test_app.py", new_content="")], protected=["test_*.py"])


def test_protection_also_covers_a_path_the_model_shortened():
    """The model's path is resolved first, so a shortened path is no way around it."""
    files = {"src/app.py": SAMPLE, "tests/test_app.py": TEST_FILE}
    with pytest.raises(PatchError, match="protected"):
        apply_edits(files, [Edit(path="test_app.py", search="== 3", replace="== -1")], protected=["tests/*"])


def test_the_refusal_says_what_to_do_instead():
    files = {"tests/test_app.py": TEST_FILE}
    with pytest.raises(PatchError) as excinfo:
        apply_edits(files, [Edit(path="tests/test_app.py", new_content="")], protected=["tests/*"])
    assert "code under test" in str(excinfo.value)


def test_a_pattern_without_a_slash_matches_any_basename():
    assert is_protected("pkg/tests/test_x.py", ["test_*.py"])
    assert is_protected("tests/unit/test_x.py", ["tests/*"])
    assert not is_protected("pkg/src/x.py", ["test_*.py", "tests/*"])


def test_unprotected_files_stay_editable():
    files = {"src/app.py": SAMPLE, "tests/test_app.py": TEST_FILE}
    out = apply_edits(files, [Edit(path="src/app.py", search="a - b", replace="a + b")], protected=["tests/*"])
    assert "a + b" in out["src/app.py"]


# --------------------------------------------------------------------------- #
# path normalisation
# --------------------------------------------------------------------------- #


def test_a_dotfile_keeps_its_leading_dot():
    """`lstrip("./")` strips a character set: `.coveragerc` became `coveragerc`."""
    files = {".coveragerc": "[run]\nbranch = False\n"}
    out = apply_edits(files, [Edit(path=".coveragerc", new_content="[run]\nbranch = True\n")])
    assert out[".coveragerc"].endswith("True\n")
    assert "coveragerc" not in out, "the rewrite must not create a second, undotted file"


def test_a_leading_dot_slash_is_still_removed():
    files = {"src/app.py": SAMPLE}
    out = apply_edits(files, [Edit(path="./src/app.py", search="a - b", replace="a + b")])
    assert "a + b" in out["src/app.py"]

