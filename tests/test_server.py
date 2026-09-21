"""API surface. The search itself is covered in test_search.py."""

from __future__ import annotations

import shlex
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from arborist import server
from arborist.llm import ScriptedLLM

from .test_search import _scripted_repair_sequence

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "broken-invoice"
PYTEST_CMD = f"{shlex.quote(sys.executable)} -m pytest -q"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    monkeypatch.setenv("ARBORIST_BACKEND", "local")
    # Keep run reports out of the working tree; a test must not leave artefacts.
    monkeypatch.setenv("ARBORIST_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.delenv("ARBORIST_DEMO_RUN", raising=False)
    server._RUNS.clear()
    return TestClient(server.app)


def _wait(client, run_id, timeout=60.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        payload = client.get(f"/api/runs/{run_id}").json()
        if payload["done"]:
            return payload
        time.sleep(0.05)
    raise AssertionError("run did not finish in time")


def test_health_reports_configuration(client):
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert body["llm_configured"] is True
    assert "nano" in body["models"]


def test_index_serves_the_ui(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Arborist" in response.text


def test_a_missing_repository_is_rejected(client):
    response = client.post("/api/runs", json={"repo_path": "/definitely/not/here"})
    assert response.status_code == 400


def test_unknown_run_is_404(client):
    assert client.get("/api/runs/nope").status_code == 404


def test_a_run_completes_and_reports_its_tree(client, monkeypatch):
    monkeypatch.setattr(server, "NemotronClient", lambda _s: _scripted_repair_sequence())

    run_id = client.post(
        "/api/runs",
        json={
            "repo_path": str(EXAMPLE),
            "test_command": PYTEST_CMD,
            "backend": "local",
            "fanout": 1,
            "max_nodes": 8,
            "max_depth": 5,
        },
    ).json()["run_id"]

    payload = _wait(client, run_id)
    assert payload["error"] == ""
    assert payload["result"]["solved"] is True
    assert len(payload["result"]["nodes"]) == 4

    kinds = [e["type"] for e in payload["events"]]
    assert "run_started" in kinds and "run_finished" in kinds and "done" in kinds

    listing = client.get("/api/runs").json()["runs"]
    assert listing[0]["run_id"] == run_id and listing[0]["solved"] is True


def test_a_failing_run_is_reported_not_raised(client, monkeypatch):
    def explode(_settings):
        raise RuntimeError("token factory unreachable")

    monkeypatch.setattr(server, "NemotronClient", explode)
    run_id = client.post(
        "/api/runs", json={"repo_path": str(EXAMPLE), "test_command": PYTEST_CMD, "backend": "local"}
    ).json()["run_id"]

    payload = _wait(client, run_id)
    assert "token factory unreachable" in payload["error"]
    assert payload["result"] is None


def test_events_replay_for_a_late_subscriber(client, monkeypatch):
    monkeypatch.setattr(server, "NemotronClient", lambda _s: ScriptedLLM())
    run_id = client.post(
        "/api/runs",
        json={"repo_path": str(EXAMPLE), "test_command": PYTEST_CMD, "backend": "local", "max_nodes": 1},
    ).json()["run_id"]
    _wait(client, run_id)

    with client.stream("GET", f"/api/runs/{run_id}/events") as response:
        assert response.status_code == 200
        body = "".join(chunk for chunk in response.iter_text())
    assert "run_started" in body


# --------------------------------------------------------------------------- #
# replaying finished runs
# --------------------------------------------------------------------------- #


@pytest.fixture
def runs_dir(tmp_path, monkeypatch, multi_branch_report):
    import json

    directory = tmp_path / "runs"
    directory.mkdir()
    (directory / f"{multi_branch_report['run_id']}.json").write_text(json.dumps(multi_branch_report))
    monkeypatch.setenv("ARBORIST_RUNS_DIR", str(directory))
    return directory


def test_demo_serves_the_newest_saved_run(client, runs_dir, multi_branch_report):
    body = client.get("/api/demo").json()
    assert body["available"] is True
    assert body["source"].startswith(multi_branch_report["run_id"])
    assert body["run"]["solved"] is True
    assert len(body["run"]["nodes"]) == len(multi_branch_report["nodes"])


def test_demo_honours_an_explicit_report(client, runs_dir, monkeypatch, multi_branch_report):
    target = next(runs_dir.glob("*.json"))
    monkeypatch.setenv("ARBORIST_DEMO_RUN", str(target))
    assert client.get("/api/demo").json()["source"] == target.name


def test_demo_is_empty_when_nothing_has_been_recorded(client, tmp_path, monkeypatch):
    monkeypatch.setenv("ARBORIST_RUNS_DIR", str(tmp_path / "nothing-here"))
    monkeypatch.setattr(server, "EVIDENCE_DIR", tmp_path / "no-evidence-either")
    body = client.get("/api/demo").json()
    assert body == {"available": False, "source": "", "recorded_at": None, "run": None}


def test_a_fresh_clone_opens_on_the_shipped_demo(client, tmp_path, monkeypatch, multi_branch_report):
    """runs/ is not checked in; evals/evidence/ is, and fills the gap."""
    import json

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "shipped.json").write_text(json.dumps(multi_branch_report))
    (evidence / "manifest.json").write_text(
        json.dumps({"demo": "shipped.json", "runs": [{"file": "shipped.json", "recorded_at": 1790000000}]})
    )
    monkeypatch.setenv("ARBORIST_RUNS_DIR", str(tmp_path / "empty"))
    monkeypatch.setattr(server, "EVIDENCE_DIR", evidence)

    body = client.get("/api/demo").json()
    assert body["available"] is True
    assert body["source"] == "shipped.json"
    assert body["recorded_at"] == 1790000000, "the recording time, not the checkout time"
    assert body["run"]["run_id"] == multi_branch_report["run_id"]


def test_a_saved_run_still_wins_over_the_shipped_demo(client, runs_dir, tmp_path, monkeypatch, multi_branch_report):
    import json

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "shipped.json").write_text(json.dumps({**multi_branch_report, "run_id": "shipped"}))
    (evidence / "manifest.json").write_text(json.dumps({"demo": "shipped.json", "runs": [{"file": "shipped.json"}]}))
    monkeypatch.setattr(server, "EVIDENCE_DIR", evidence)

    assert client.get("/api/demo").json()["run"]["run_id"] == multi_branch_report["run_id"]


def test_demo_skips_a_corrupt_report(client, runs_dir):
    (runs_dir / "broken.json").write_text("{not json")
    body = client.get("/api/demo").json()
    assert body["available"] is True, "one bad file must not take the demo down"


def test_a_run_from_a_previous_process_is_still_readable(client, runs_dir, multi_branch_report):
    payload = client.get(f"/api/runs/{multi_branch_report['run_id']}").json()
    assert payload["recorded"] is True
    assert payload["done"] is True
    assert payload["result"]["solved"] is True


def test_listing_includes_saved_runs(client, runs_dir, multi_branch_report):
    rows = client.get("/api/runs").json()["runs"]
    assert any(r["run_id"] == multi_branch_report["run_id"] and r["recorded"] for r in rows)


def test_health_reports_whether_a_live_run_is_possible(client, runs_dir, monkeypatch):
    assert client.get("/api/health").json()["can_run"] is True
    monkeypatch.delenv("NEBIUS_API_KEY")
    body = client.get("/api/health").json()
    assert body["can_run"] is False
    assert body["saved_runs"] == 1


def test_demo_finds_an_explicit_report_by_name_when_the_path_moved(
    client, runs_dir, monkeypatch, multi_branch_report
):
    """A relative ARBORIST_DEMO_RUN written for the working tree must still
    resolve when the reports are on a mounted volume."""
    monkeypatch.setenv("ARBORIST_DEMO_RUN", f"runs/{multi_branch_report['run_id']}.json")
    body = client.get("/api/demo").json()
    assert body["available"] is True
    assert body["run"]["run_id"] == multi_branch_report["run_id"]


# --------------------------------------------------------------------------- #
# cancelling a run
# --------------------------------------------------------------------------- #


def test_cancelling_an_unknown_run_is_404(client):
    assert client.post("/api/runs/nope/cancel").status_code == 404


def test_cancel_stops_the_search_instead_of_only_the_watching(client, monkeypatch):
    """Closing the event stream leaves the run spending tokens; this must not."""
    import threading

    from arborist.llm import ScriptedLLM

    released = threading.Event()
    calls = {"n": 0}

    class SlowLLM(ScriptedLLM):
        def json(self, tier, system, user, schema=None, **kw):
            calls["n"] += 1
            released.wait(timeout=10)
            return {}

    monkeypatch.setattr(server, "NemotronClient", lambda _s: SlowLLM())

    run_id = client.post(
        "/api/runs",
        json={"repo_path": str(EXAMPLE), "test_command": PYTEST_CMD, "backend": "local"},
    ).json()["run_id"]

    # Wait until the search is actually inside a model call.
    deadline = time.time() + 30
    while calls["n"] == 0 and time.time() < deadline:
        time.sleep(0.05)
    assert calls["n"] > 0, "the run never reached a model call"

    body = client.post(f"/api/runs/{run_id}/cancel").json()
    assert body["cancelling"] is True
    released.set()

    payload = _wait(client, run_id)
    assert payload["result"]["error"] == "stopped by request"
    assert payload["result"]["stats"]["cancelled"] is True
    # The baseline it already measured is kept rather than thrown away.
    assert payload["result"]["baseline"]["passed"] == 5


def test_a_stop_arriving_before_the_agent_exists_is_not_dropped(client, monkeypatch):
    from arborist.llm import ScriptedLLM

    monkeypatch.setattr(server, "NemotronClient", lambda _s: ScriptedLLM())
    run = server._Run("run-test", server.StartRun(repo_path=str(EXAMPLE)))
    server._RUNS["run-test"] = run

    assert client.post("/api/runs/run-test/cancel").json()["cancelling"] is True
    assert run.stop_requested is True
