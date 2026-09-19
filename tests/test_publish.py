"""Branch, commit, push, open — and the guard rails that stop each one."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from arborist.publish import (
    GitError,
    apply_patch,
    build_plan,
    current_branch,
    is_clean,
    patched_files,
    publish,
    slugify,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


# --------------------------------------------------------------------------- #
# plan
# --------------------------------------------------------------------------- #


def test_slugify_makes_a_usable_branch_component():
    assert slugify("round_money uses banker's rounding") == "round-money-uses-banker-s-rounding"
    assert slugify("!!!") == "repair"
    assert not slugify("a" * 80).endswith("-")


def test_patched_files_reads_the_diff_headers(multi_branch_report):
    assert patched_files(multi_branch_report["diff"]) == [
        "src/billing/invoice.py",
        "src/billing/money.py",
        "src/billing/proration.py",
    ]


def test_build_plan_derives_branch_base_and_files(multi_branch_report, demo_git_repo):
    plan = build_plan(multi_branch_report, demo_git_repo)
    assert plan.base == "main"
    assert plan.branch.startswith("arborist/round-money-uses-banker-s-rounding")
    assert plan.branch.endswith(multi_branch_report["run_id"].split("-")[-1])
    assert plan.files == ["src/billing/invoice.py", "src/billing/money.py", "src/billing/proration.py"]
    assert "Generated-by: Arborist" in plan.commit_message


def test_build_plan_accepts_explicit_branch_and_base(multi_branch_report, demo_git_repo):
    plan = build_plan(multi_branch_report, demo_git_repo, branch="my-branch", base="release")
    assert (plan.branch, plan.base) == ("my-branch", "release")


def test_build_plan_refuses_a_non_repository(multi_branch_report, tmp_path):
    with pytest.raises(GitError, match="not a git repository"):
        build_plan(multi_branch_report, tmp_path)


def test_build_plan_refuses_a_run_that_changed_nothing(multi_branch_report, demo_git_repo):
    with pytest.raises(GitError, match="no diff"):
        build_plan({**multi_branch_report, "diff": ""}, demo_git_repo)


def test_describe_lists_the_commands_without_running_them(multi_branch_report, demo_git_repo):
    plan = build_plan(multi_branch_report, demo_git_repo)
    described = plan.describe()
    assert "git checkout -b" in described and "gh pr create" in described
    assert current_branch(demo_git_repo) == "main", "a dry run must not touch the repository"


# --------------------------------------------------------------------------- #
# publish
# --------------------------------------------------------------------------- #


def test_publish_creates_a_branch_and_commits_the_fix(multi_branch_report, demo_git_repo):
    plan = build_plan(multi_branch_report, demo_git_repo)
    result = publish(plan)

    assert result.committed and not result.pushed and not result.pr_url
    assert current_branch(demo_git_repo) == plan.branch
    assert "round_money uses banker's rounding" in _git(demo_git_repo, "log", "-1", "--pretty=%B")
    assert is_clean(demo_git_repo)


def test_the_committed_branch_actually_passes_the_suite(multi_branch_report, demo_git_repo):
    """The end of the whole pipeline: a repo that was red is green on the branch."""
    publish(build_plan(multi_branch_report, demo_git_repo))
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"], cwd=demo_git_repo, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stdout
    assert "9 passed" in proc.stdout


def test_publish_refuses_a_dirty_working_tree(multi_branch_report, demo_git_repo):
    (demo_git_repo / "scratch.txt").write_text("uncommitted")
    plan = build_plan(multi_branch_report, demo_git_repo)
    with pytest.raises(GitError, match="uncommitted changes"):
        publish(plan)
    assert current_branch(demo_git_repo) == "main"


def test_publish_refuses_a_patch_that_no_longer_applies(multi_branch_report, demo_git_repo):
    (demo_git_repo / "src" / "billing" / "money.py").write_text("# rewritten by someone else\n")
    subprocess.run(["git", "commit", "-am", "drift"], cwd=demo_git_repo, check=True, capture_output=True)

    plan = build_plan(multi_branch_report, demo_git_repo)
    with pytest.raises(GitError, match="no longer applies"):
        publish(plan)
    assert current_branch(demo_git_repo) == "main", "the branch must not be left behind"


def test_apply_patch_check_only_changes_nothing(multi_branch_report, demo_git_repo):
    plan = build_plan(multi_branch_report, demo_git_repo)
    apply_patch(plan, check_only=True)
    assert is_clean(demo_git_repo)


def test_publish_opens_a_pull_request_through_gh(multi_branch_report, demo_git_repo, tmp_path, monkeypatch):
    """`gh` is stubbed; what is asserted is the arguments we hand it."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    recorded = tmp_path / "gh-args.txt"
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$@" > {recorded}\n'
        f'cat > {tmp_path}/gh-body.md\n'
        'echo https://github.com/acme/demo/pull/7\n'
    )
    gh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    # A push needs a remote; a bare repo alongside stands in for origin.
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=demo_git_repo, check=True, capture_output=True)

    plan = build_plan(multi_branch_report, demo_git_repo)
    result = publish(plan, push=True, open_pr=True)

    assert result.pushed
    assert result.pr_url == "https://github.com/acme/demo/pull/7"
    args = recorded.read_text().splitlines()
    assert args[:3] == ["pr", "create", "--base"]
    assert plan.branch in args
    assert "Alternatives considered" in (tmp_path / "gh-body.md").read_text()


def test_publish_reports_a_missing_gh_instead_of_crashing(multi_branch_report, demo_git_repo, monkeypatch):
    monkeypatch.setattr("arborist.publish.shutil.which", lambda _name: None)
    plan = build_plan(multi_branch_report, demo_git_repo)
    with pytest.raises(GitError, match="GitHub CLI"):
        publish(plan, open_pr=True)
    assert current_branch(demo_git_repo) == plan.branch, "the commit is kept; only the PR step failed"
