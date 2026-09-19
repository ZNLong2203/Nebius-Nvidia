"""End-to-end exercise of the search, with no network and no credentials.

``ScriptedLLM`` stands in for Nemotron and ``LocalBackend`` for Nebius
Sandboxes, so the selection, scoring, patch validation and backtracking logic
are all genuinely executed here -- only the two remote services are swapped out.
"""

from __future__ import annotations

import shlex
import sys
import textwrap
from pathlib import Path

import pytest

from arborist.config import load_settings
from arborist.llm import ScriptedLLM
from arborist.models import TestReport
from arborist.sandbox import LocalBackend
from arborist.search import Arborist, RunConfig

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "broken-invoice"
PYTEST_CMD = f"{shlex.quote(sys.executable)} -m pytest -q"

MONEY_FIXED = textwrap.dedent(
    '''\
    """Money helpers."""

    from decimal import ROUND_HALF_UP, Decimal


    def round_money(amount: float) -> float:
        """Round a monetary amount to two decimal places, half away from zero."""
        return float(Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


    def pct(value: float, percent: float) -> float:
        """Apply a percentage to a value."""
        return value * (percent / 100.0)
    '''
)

INVOICE_FIXED = textwrap.dedent(
    '''\
    """Invoice totals."""

    from dataclasses import dataclass

    from .money import pct, round_money


    @dataclass
    class InvoiceLine:
        description: str
        quantity: int
        unit_price: float
        line_discount_pct: float = 0.0


    def line_total(line: InvoiceLine) -> float:
        """Total for a single line, after its own discount."""
        gross = line.quantity * line.unit_price
        return round_money(gross - pct(gross, line.line_discount_pct))


    def invoice_total(
        lines: list[InvoiceLine],
        tax_pct: float = 0.0,
        coupon: float = 0.0,
    ) -> float:
        """Total payable, with the coupon reducing the taxable base."""
        subtotal = round_money(sum(line_total(line) for line in lines))
        taxable = max(0.0, subtotal - coupon)
        return round_money(taxable + pct(taxable, tax_pct))
    '''
)


def _diagnosis(title: str, path: str) -> dict:
    return {
        "root_cause": f"failure traced to {path}",
        "confidence": 0.8,
        "needs_external_docs": False,
        "hypotheses": [{"title": title, "strategy": f"repair {path}", "target_files": [path]}],
    }


def _scripted_repair_sequence() -> ScriptedLLM:
    """Three diagnoses and three patches: one per independent bug."""
    return ScriptedLLM(
        responses={
            "super": [
                _diagnosis("banker's rounding in round_money", "src/billing/money.py"),
                _diagnosis("coupon applied after tax", "src/billing/invoice.py"),
                _diagnosis("exclusive end date in billed_days", "src/billing/proration.py"),
            ],
            "nano": [
                {
                    "explanation": "round half away from zero with Decimal",
                    "edits": [{"path": "src/billing/money.py", "new_content": MONEY_FIXED}],
                },
                {
                    "explanation": "subtract the coupon before applying tax",
                    "edits": [{"path": "src/billing/invoice.py", "new_content": INVOICE_FIXED}],
                },
                {
                    "explanation": "count both endpoints",
                    "edits": [
                        {
                            "path": "src/billing/proration.py",
                            "search": "    return (end - start).days",
                            "replace": "    return (end - start).days + 1",
                        }
                    ],
                },
            ],
        }
    )


@pytest.fixture
def backend():
    b = LocalBackend()
    yield b
    b.close()


# --------------------------------------------------------------------------- #
# scoring
# --------------------------------------------------------------------------- #


def test_score_is_the_pass_rate_at_the_root():
    score, _, _ = Arborist.score(None, TestReport(total=10, passed=4, failed=6))
    assert score == pytest.approx(0.4)


def test_a_green_suite_scores_one():
    score, fixed, regressions = Arborist.score(
        TestReport(total=2, passed=1, passed_ids={"a"}),
        TestReport(total=2, passed=2, passed_ids={"a", "b"}),
    )
    assert score == 1.0
    assert fixed == ["b"] and regressions == []


def test_a_patch_that_trades_one_failure_for_another_is_penalised():
    """Pass rate alone would call this progress. Test identities say otherwise."""
    parent = TestReport(total=4, passed=2, failed=2, passed_ids={"a", "b"})
    trade = TestReport(total=4, passed=2, failed=2, passed_ids={"a", "c"})
    improvement = TestReport(total=4, passed=3, failed=1, passed_ids={"a", "b", "c"})

    trade_score, _, regressions = Arborist.score(parent, trade)
    improved_score, fixed, _ = Arborist.score(parent, improvement)

    assert regressions == ["b"]
    assert trade_score < 0.5
    assert improved_score > trade_score
    assert fixed == ["c"]


def test_a_collection_error_scores_zero():
    score, _, _ = Arborist.score(TestReport(total=4, passed=2), TestReport(collection_error=True, total=0))
    assert score == 0.0


def test_a_missing_report_scores_zero():
    assert Arborist.score(None, None) == (0.0, [], [])


# --------------------------------------------------------------------------- #
# end to end
# --------------------------------------------------------------------------- #


def test_search_repairs_every_bug_by_deepening(backend):
    settings = load_settings(backend="local", fanout=1, max_nodes=8, max_depth=5)
    llm = _scripted_repair_sequence()
    agent = Arborist(settings, backend, llm)

    result = agent.run(RunConfig(repo_path=str(EXAMPLE), test_command=PYTEST_CMD))

    assert result.baseline.passed == 5
    assert result.baseline.failed == 4
    assert result.solved, result.error
    assert result.final.green
    assert result.winner.depth == 3, "each bug needed its own branch, built on the last"

    # Every intermediate state was kept, and each one strictly improved.
    scores = [n.score for n in result.nodes]
    assert scores == sorted(scores)
    assert result.diff.count("--- a/") == 3


def test_the_winning_diff_contains_every_fix_and_nothing_else(backend):
    settings = load_settings(backend="local", fanout=1, max_nodes=8, max_depth=5)
    agent = Arborist(settings, backend, _scripted_repair_sequence())
    result = agent.run(RunConfig(repo_path=str(EXAMPLE), test_command=PYTEST_CMD))

    assert "ROUND_HALF_UP" in result.diff
    assert "taxable" in result.diff
    assert "+    return (end - start).days + 1" in result.diff
    assert "tests/test_billing.py" not in result.diff, "the agent must not edit the tests"


def test_an_unapplicable_patch_costs_tokens_but_no_sandbox_run(backend):
    """Patch validation happens before execution, on purpose."""
    llm = ScriptedLLM(
        responses={
            "super": [_diagnosis("wrong guess", "src/billing/money.py")],
            "nano": [
                {
                    "explanation": "hallucinated code",
                    "edits": [
                        {
                            "path": "src/billing/money.py",
                            "search": "def this_function_does_not_exist():",
                            "replace": "pass",
                        }
                    ],
                }
            ],
        }
    )
    settings = load_settings(backend="local", fanout=1, max_nodes=2, max_depth=2)
    agent = Arborist(settings, backend, llm)
    result = agent.run(RunConfig(repo_path=str(EXAMPLE), test_command=PYTEST_CMD))

    invalid = [n for n in result.nodes if n.status == "invalid"]
    assert len(invalid) == 1
    assert "not found" in invalid[0].note
    assert result.stats["invalid_patches"] == 1
    # baseline run only: the rejected patch never reached the sandbox
    assert result.stats["sandbox_executions"] == 1
    assert not result.solved


def test_a_patch_that_does_not_apply_gets_one_repaired_attempt(backend):
    """A failed patch taught the search nothing: the next expansion read the same
    source, formed the same theory and quoted the same snippet that did not match."""
    llm = ScriptedLLM(
        responses={
            "super": [_diagnosis("banker's rounding in round_money", "src/billing/money.py")],
            "nano": [
                {
                    "explanation": "quoting a snippet that is not there",
                    "edits": [
                        {
                            "path": "src/billing/money.py",
                            "search": "def round_money(value: float) -> Decimal:",
                            "replace": "def round_money(value: float) -> float:",
                        }
                    ],
                },
                {
                    "explanation": "second attempt, whole file",
                    "edits": [{"path": "src/billing/money.py", "new_content": MONEY_FIXED}],
                },
            ],
        }
    )
    settings = load_settings(backend="local", fanout=1, max_nodes=2, max_depth=2)
    agent = Arborist(settings, backend, llm)
    result = agent.run(RunConfig(repo_path=str(EXAMPLE), test_command=PYTEST_CMD))

    child = next(n for n in result.nodes if n.depth == 1)
    assert child.status == "improved", "the retry rescued the branch"
    assert "applied on retry after" in child.note
    assert result.stats["invalid_patches"] == 0

    retry_prompt = next(
        user for _tier, user in llm.calls if "A PREVIOUS ATTEMPT FAILED TO APPLY" in user
    )
    assert "search block not found" in retry_prompt, "the reason comes back to the model"


def test_a_patch_that_fails_twice_is_given_up_on(backend):
    bad = {
        "explanation": "still wrong",
        "edits": [{"path": "src/billing/money.py", "search": "def nope():", "replace": "pass"}],
    }
    llm = ScriptedLLM(
        responses={
            "super": [_diagnosis("wrong guess", "src/billing/money.py")],
            "nano": [bad, bad],
        }
    )
    settings = load_settings(backend="local", fanout=1, max_nodes=2, max_depth=2)
    result = Arborist(settings, backend, llm).run(
        RunConfig(repo_path=str(EXAMPLE), test_command=PYTEST_CMD)
    )

    child = next(n for n in result.nodes if n.depth == 1)
    assert child.status == "invalid"
    assert "retry:" in child.note
    assert result.stats["invalid_patches"] == 1
    assert result.stats["sandbox_executions"] == 1, "neither attempt reached the sandbox"


def test_short_files_are_offered_for_whole_file_rewrite(backend):
    """Reproducing a whole short file is more reliable than an exact fragment of it."""
    llm = ScriptedLLM(
        responses={
            "super": [_diagnosis("anything", "src/billing/money.py")],
            "nano": [{"edits": [{"path": "src/billing/money.py", "new_content": MONEY_FIXED}]}],
        }
    )
    settings = load_settings(backend="local", fanout=1, max_nodes=1, max_depth=1)
    Arborist(settings, backend, llm).run(
        RunConfig(repo_path=str(EXAMPLE), test_command=PYTEST_CMD)
    )

    patch_prompt = next(user for tier, user in llm.calls if "YOUR ASSIGNED HYPOTHESIS" in user)
    assert "SHORT FILES" in patch_prompt
    assert "src/billing/money.py" in patch_prompt.split("SHORT FILES")[1]


def test_a_regressing_branch_is_recorded_and_not_followed(backend):
    """A patch that breaks a passing test must not become the next fork point."""
    llm = ScriptedLLM(
        responses={
            "super": [_diagnosis("break something", "src/billing/money.py")],
            "nano": [
                {
                    "explanation": "this breaks line_total",
                    "edits": [
                        {
                            "path": "src/billing/money.py",
                            "search": "    return value * (percent / 100.0)",
                            "replace": "    return value * percent",
                        }
                    ],
                }
            ],
        }
    )
    settings = load_settings(backend="local", fanout=1, max_nodes=1, max_depth=2)
    agent = Arborist(settings, backend, llm)
    result = agent.run(RunConfig(repo_path=str(EXAMPLE), test_command=PYTEST_CMD))

    child = next(n for n in result.nodes if n.depth == 1)
    assert child.status == "regressed"
    assert child.regressions, "the tests it broke are named, not just counted"
    assert not result.solved


def test_run_events_are_emitted_for_the_ui(backend):
    events = []
    settings = load_settings(backend="local", fanout=1, max_nodes=8, max_depth=5)
    agent = Arborist(settings, backend, _scripted_repair_sequence(), on_event=events.append)
    agent.run(RunConfig(repo_path=str(EXAMPLE), test_command=PYTEST_CMD))

    kinds = [e["type"] for e in events]
    assert kinds[0] == "run_started"
    assert kinds[-1] == "run_finished"
    assert "diagnosed" in kinds and "node" in kinds


def test_a_green_repo_is_left_alone(backend, tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    settings = load_settings(backend="local", fanout=2, max_nodes=4)
    llm = ScriptedLLM()
    agent = Arborist(settings, backend, llm)

    result = agent.run(RunConfig(repo_path=str(tmp_path), test_command=PYTEST_CMD))

    assert result.solved
    assert result.diff == ""
    assert llm.calls == [], "a passing suite must not cost a single model call"
