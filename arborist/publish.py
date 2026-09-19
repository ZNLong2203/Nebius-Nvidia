"""Getting a repaired branch in front of a human.

Nothing here runs without being asked. Creating a branch, pushing it, and
opening a pull request are outward-facing actions, so the default for every
entry point in this module is to plan and print, never to act.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .report import pr_title, render_pr_body

TRAILER = "Generated-by: Arborist (NVIDIA Nemotron 3 on Nebius Token Factory)"


class GitError(RuntimeError):
    pass


def _git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True
    )
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {(proc.stderr or proc.stdout).strip()}")
    return (proc.stdout or "").strip()


def slugify(text: str, limit: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:limit].rstrip("-") or "repair"


@dataclass
class PublishPlan:
    repo_path: Path
    branch: str
    base: str
    title: str
    body: str
    patch: str
    commit_message: str
    files: list[str] = field(default_factory=list)

    def describe(self) -> str:
        """The commands this plan would run, for a dry run."""
        return "\n".join(
            [
                f"cd {self.repo_path}",
                f"git checkout -b {self.branch} {self.base}",
                "git apply <patch>",
                f"git add {' '.join(self.files) if self.files else '-A'}",
                "git commit -F <message>",
                f"git push -u origin {self.branch}",
                (
                    f"gh pr create --base {self.base} --head {self.branch} "
                    f'--title "{self.title}" --body-file <body>'
                ),
            ]
        )


@dataclass
class PublishResult:
    branch: str
    committed: bool = False
    pushed: bool = False
    pr_url: str = ""
    steps: list[str] = field(default_factory=list)


def patched_files(patch: str) -> list[str]:
    return sorted({m.group(1) for m in re.finditer(r"^\+\+\+ b/(.+)$", patch, re.MULTILINE)})


def current_branch(repo: Path) -> str:
    return _git(repo, "rev-parse", "--abbrev-ref", "HEAD")


def is_clean(repo: Path) -> bool:
    return _git(repo, "status", "--porcelain") == ""


def build_plan(
    report: dict,
    repo_path: str | Path,
    *,
    branch: str | None = None,
    base: str | None = None,
) -> PublishPlan:
    """Assemble everything needed to open the pull request, without doing it."""
    repo = Path(repo_path).resolve()
    if not (repo / ".git").exists():
        raise GitError(f"{repo} is not a git repository")

    patch = report.get("diff") or ""
    if not patch.strip():
        raise GitError("this run produced no diff — nothing to publish")

    title = pr_title(report)
    body = render_pr_body(report)
    files = patched_files(patch)
    run_id = report.get("run_id", "run")
    branch = branch or f"arborist/{slugify(title.split(':', 1)[-1])}-{run_id.split('-')[-1]}"
    base = base or current_branch(repo)

    summary = title[0].upper() + title[1:]
    stats = report.get("stats") or {}
    message = (
        f"{summary}\n\n"
        f"Found by searching {stats.get('patches_evaluated', 0)} candidate patches across forked\n"
        f"sandbox states; the alternatives that were rejected, and the tests each one\n"
        f"broke, are in the pull request body.\n\n"
        f"{TRAILER}\n"
    )

    return PublishPlan(
        repo_path=repo,
        branch=branch,
        base=base,
        title=title,
        body=body,
        patch=patch,
        commit_message=message,
        files=files,
    )


def apply_patch(plan: PublishPlan, *, check_only: bool = False) -> None:
    """Apply the run's diff to the working tree.

    ``check_only`` verifies the patch still applies without touching anything,
    which is worth doing before creating a branch.
    """
    args = ["apply", "--3way"]
    if check_only:
        args = ["apply", "--check"]
    proc = subprocess.run(
        ["git", *args, "-"],
        cwd=plan.repo_path,
        input=plan.patch,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise GitError(
            "the patch no longer applies to this working tree: "
            + (proc.stderr or proc.stdout).strip()
        )


def publish(plan: PublishPlan, *, push: bool = False, open_pr: bool = False) -> PublishResult:
    """Create the branch and commit. Push and open a PR only when asked."""
    result = PublishResult(branch=plan.branch)
    repo = plan.repo_path

    if not is_clean(repo):
        raise GitError("working tree has uncommitted changes — commit or stash them first")

    apply_patch(plan, check_only=True)

    _git(repo, "checkout", "-b", plan.branch)
    result.steps.append(f"created branch {plan.branch}")

    try:
        apply_patch(plan)
        _git(repo, "add", *(plan.files or ["-A"]))
        _commit(repo, plan.commit_message)
        result.committed = True
        result.steps.append("committed the patch")
    except GitError:
        _git(repo, "checkout", plan.base, check=False)
        _git(repo, "branch", "-D", plan.branch, check=False)
        raise

    if push:
        _git(repo, "push", "-u", "origin", plan.branch)
        result.pushed = True
        result.steps.append(f"pushed {plan.branch} to origin")

    if open_pr:
        if shutil.which("gh") is None:
            raise GitError("the GitHub CLI (gh) is not installed, so the pull request was not opened")
        result.pr_url = _gh_pr_create(plan)
        result.steps.append(f"opened {result.pr_url}")

    return result


def _commit(repo: Path, message: str) -> None:
    proc = subprocess.run(
        ["git", "commit", "-F", "-"], cwd=repo, input=message, capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise GitError(f"git commit: {(proc.stderr or proc.stdout).strip()}")


def _gh_pr_create(plan: PublishPlan) -> str:
    proc = subprocess.run(
        [
            "gh", "pr", "create",
            "--base", plan.base,
            "--head", plan.branch,
            "--title", plan.title,
            "--body-file", "-",
        ],
        cwd=plan.repo_path,
        input=plan.body,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise GitError(f"gh pr create: {(proc.stderr or proc.stdout).strip()}")
    match = re.search(r"https://\S+", proc.stdout or "")
    return match.group(0) if match else (proc.stdout or "").strip()
