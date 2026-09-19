"""Shared fixtures.

``multi_branch_report`` is a **real run**, not hand-written JSON: the scripted
model produces one branch that cannot be applied, one that changes nothing, and
a three-deep chain that goes green. Rendering and publishing are therefore
tested against output the search actually produced.
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

import pytest

from arborist.config import load_settings
from arborist.llm import ScriptedLLM
from arborist.sandbox import LocalBackend
from arborist.search import Arborist, RunConfig

from .test_search import INVOICE_FIXED, MONEY_FIXED

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "broken-invoice"
PYTEST_CMD = f"{shlex.quote(sys.executable)} -m pytest -q"

_DIAGNOSES = [
    {
        "root_cause": (
            "round_money() delegates to Python's round(), which uses banker's rounding, so "
            "half-cent amounts round toward even instead of away from zero."
        ),
        "confidence": 0.82,
        "hypotheses": [
            {
                "title": "round_money uses banker's rounding",
                "rationale": "round(2.675, 2) returns 2.67 because of round-half-to-even.",
                "target_files": ["src/billing/money.py"],
                "strategy": "quantize with Decimal and ROUND_HALF_UP",
            },
            {
                "title": "pct() loses precision before rounding",
                "rationale": "If the percentage helper introduced the error, fix it upstream.",
                "target_files": ["src/billing/money.py"],
                "strategy": "round inside pct()",
            },
            {
                "title": "the test encodes the wrong expectation",
                "rationale": "Banker's rounding is a defensible convention.",
                "target_files": ["tests/test_billing.py"],
                "strategy": "relax the assertion",
            },
        ],
    },
    {
        "root_cause": "invoice_total() subtracts the coupon after tax, taxing money never paid.",
        "hypotheses": [
            {
                "title": "coupon is applied after tax",
                "rationale": "The docstring says the coupon reduces the taxable base.",
                "target_files": ["src/billing/invoice.py"],
                "strategy": "subtract the coupon from the subtotal, then tax",
            }
        ],
    },
    {
        "root_cause": "billed_days() returns an exclusive day count.",
        "hypotheses": [
            {
                "title": "billed_days treats the end date as exclusive",
                "rationale": "Both endpoints are documented as inclusive.",
                "target_files": ["src/billing/proration.py"],
                "strategy": "add one to the day difference",
            }
        ],
    },
]

# Keyed on the `Title:` line, which is unique to one branch's patch prompt.
_PATCHES = {
    "Title: round_money uses banker's rounding": {
        "explanation": "Quantize with Decimal and ROUND_HALF_UP so half-cent amounts round away from zero.",
        "edits": [{"path": "src/billing/money.py", "new_content": MONEY_FIXED}],
    },
    "Title: pct() loses precision before rounding": {
        "explanation": "Round inside pct() so the caller never sees a long float.",
        "edits": [
            {
                "path": "src/billing/money.py",
                "search": "    return value * (percent / 100.0)",
                "replace": "    return round(value * (percent / 100.0), 2)",
            }
        ],
    },
    "Title: the test encodes the wrong expectation": {
        "explanation": "Loosen the assertion to accept banker's rounding.",
        "edits": [
            {
                "path": "tests/test_billing.py",
                "search": "    assert round_money(2.675) == 2.675",
                "replace": "    pass",
            }
        ],
    },
    "Title: coupon is applied after tax": {
        "explanation": "Subtract the coupon from the subtotal so tax is charged on the discounted base.",
        "edits": [{"path": "src/billing/invoice.py", "new_content": INVOICE_FIXED}],
    },
    "Title: billed_days treats the end date as exclusive": {
        "explanation": "Count both endpoints.",
        "edits": [
            {
                "path": "src/billing/proration.py",
                "search": "    return (end - start).days",
                "replace": "    return (end - start).days + 1",
            }
        ],
    },
}


@pytest.fixture(scope="session")
def multi_branch_report() -> dict:
    llm = ScriptedLLM(responses={"super": list(_DIAGNOSES)}, by_prompt={"nano": dict(_PATCHES)})
    settings = load_settings(backend="local", fanout=3, max_nodes=10, max_depth=5)
    backend = LocalBackend()
    try:
        agent = Arborist(settings, backend, llm)
        result = agent.run(RunConfig(repo_path=str(EXAMPLE), test_command=PYTEST_CMD))
    finally:
        backend.close()
    return result.to_dict()


@pytest.fixture
def report_file(multi_branch_report, tmp_path) -> Path:
    import json

    path = tmp_path / "run.json"
    path.write_text(json.dumps(multi_branch_report), encoding="utf-8")
    return path


@pytest.fixture
def demo_git_repo(tmp_path) -> Path:
    """A git repository containing the broken example, with one commit."""
    import shutil
    import subprocess

    repo = tmp_path / "repo"
    shutil.copytree(EXAMPLE, repo)
    def run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

    run("init", "-b", "main")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "Test")
    run("add", "-A")
    run("commit", "-m", "initial")
    return repo
