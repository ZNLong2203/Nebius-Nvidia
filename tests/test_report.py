"""Rendering a run as something a human reviews."""

from __future__ import annotations

import json

import pytest

from arborist.report import (
    load_report,
    pr_title,
    rejected_branches,
    render_markdown_summary,
    render_pr_body,
    winning_path,
)


def test_winning_path_is_the_accepted_chain_root_first(multi_branch_report):
    path = winning_path(multi_branch_report)
    titles = [n["hypothesis"]["title"] for n in path]
    assert titles == [
        "round_money uses banker's rounding",
        "coupon is applied after tax",
        "billed_days treats the end date as exclusive",
    ]
    assert [n["depth"] for n in path] == [1, 2, 3]


def test_rejected_branches_exclude_the_winning_chain(multi_branch_report):
    kept = {n["id"] for n in winning_path(multi_branch_report)}
    assert not kept & {n["id"] for n in rejected_branches(multi_branch_report)}


def test_rejected_branches_put_informative_failures_first(multi_branch_report):
    """A patch that broke or changed something teaches more than one that never ran."""
    order = [n["status"] for n in rejected_branches(multi_branch_report)]
    assert order.index("neutral") < order.index("invalid")


def test_pr_title_names_the_whole_chain_not_just_the_last_patch(multi_branch_report):
    title = pr_title(multi_branch_report)
    assert title.startswith("fix: round_money uses banker's rounding + 2 more")
    assert "(4 failing tests)" in title


def test_pr_title_marks_an_unfinished_run_as_wip(multi_branch_report):
    partial = {**multi_branch_report, "solved": False}
    assert pr_title(partial).startswith("wip:")


def test_pr_title_survives_a_run_with_no_winner():
    title = pr_title({"baseline": {"failed": 1}, "nodes": [], "stats": {}})
    assert title == "wip: repair failing tests (1 failing test)"


def test_body_leads_with_the_outcome(multi_branch_report):
    body = render_pr_body(multi_branch_report)
    assert body.splitlines()[0] == "Repairs the failing suite: **5/9 → 9/9 passing**."


def test_body_quotes_the_diagnosis(multi_branch_report):
    assert "> round_money() delegates to Python's round()" in render_pr_body(multi_branch_report)


def test_body_lists_each_patch_with_the_tests_it_fixed(multi_branch_report):
    body = render_pr_body(multi_branch_report)
    assert "**1. round_money uses banker's rounding**" in body
    assert "**3. billed_days treats the end date as exclusive**" in body
    assert "test_prorate_charges_inclusive_days" in body


def test_body_reports_what_the_search_cost(multi_branch_report):
    body = render_pr_body(multi_branch_report)
    assert "Searched **5 candidate patches** across **3 levels**" in body
    assert "1 proposed patch did not apply cleanly and was rejected before execution." in body


def test_body_carries_the_rejected_alternatives_with_their_reasons(multi_branch_report):
    """The whole point: a reviewer sees what was tried and why it lost."""
    body = render_pr_body(multi_branch_report)
    assert "## Alternatives considered (2)" in body
    assert "<b>pct() loses precision before rounding</b> — no test changed state" in body
    assert "<b>the test encodes the wrong expectation</b> — tests/test_billing.py: search block not found" in body
    assert "```diff" in body


def test_body_credits_the_models_and_the_platform(multi_branch_report):
    body = render_pr_body(multi_branch_report)
    assert "NVIDIA Nemotron 3 on Nebius Token Factory" in body
    assert "sandbox executions" in body


def test_body_links_the_project_only_when_given_a_url(multi_branch_report):
    assert "[Arborist](https://example.test)" in render_pr_body(multi_branch_report, repo_url="https://example.test")
    assert "[Arborist](" not in render_pr_body(multi_branch_report)


def test_an_unsolved_run_is_labelled_as_partial(multi_branch_report):
    body = render_pr_body({**multi_branch_report, "solved": False})
    assert body.startswith("⚠️ **Partial.**")
    assert "Opened for review rather than merge" in body


def test_summary_is_one_line(multi_branch_report):
    line = render_markdown_summary(multi_branch_report)
    assert "\n" not in line
    assert "5/9 → 9/9 passing (green)" in line


def test_load_report_rejects_something_that_is_not_a_run(tmp_path):
    path = tmp_path / "nope.json"
    path.write_text(json.dumps({"hello": "world"}))
    with pytest.raises(ValueError, match="does not look like"):
        load_report(path)


def test_load_report_reads_a_real_one(report_file):
    assert load_report(report_file)["solved"] is True
