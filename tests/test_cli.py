"""The CLI, exercised with the scripted model and the local backend."""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from arborist import cli
from arborist.llm import ScriptedLLM

from .test_search import _scripted_repair_sequence  # noqa: PLC2701

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "broken-invoice"
PYTEST_CMD = f"{shlex.quote(sys.executable)} -m pytest -q"
runner = CliRunner()


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    monkeypatch.setenv("ARBORIST_BACKEND", "local")


def test_fix_reports_a_successful_repair(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "NemotronClient", lambda _s: _scripted_repair_sequence())

    result = runner.invoke(
        cli.app,
        ["fix", str(EXAMPLE), "--test", PYTEST_CMD, "--backend", "local",
         "-k", "1", "--max-nodes", "8", "--max-depth", "5", "--out", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert "suite is green" in result.output
    assert "baseline  5/9 passing" in result.output
    assert "Nemotron usage" in result.output

    reports = list(tmp_path.glob("*.json"))
    assert len(reports) == 1
    payload = json.loads(reports[0].read_text())
    assert payload["solved"] is True
    assert len(payload["nodes"]) == 4
    assert list(tmp_path.glob("*.patch")), "the winning diff is written next to the report"


def test_fix_exits_nonzero_when_it_cannot_repair(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "NemotronClient", lambda _s: ScriptedLLM())
    result = runner.invoke(
        cli.app,
        ["fix", str(EXAMPLE), "--test", PYTEST_CMD, "--backend", "local",
         "--max-nodes", "1", "--out", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "not fully repaired" in result.output


def test_fix_refuses_to_run_without_a_key(monkeypatch, tmp_path):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    result = runner.invoke(cli.app, ["fix", str(EXAMPLE), "--out", str(tmp_path)])
    assert result.exit_code == 2
    assert "NEBIUS_API_KEY" in result.output
