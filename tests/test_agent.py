"""The model-facing layer: what it accepts, and what it refuses to pass on."""

from __future__ import annotations

from arborist.agent import diagnose, propose_patch
from arborist.llm import ScriptedLLM
from arborist.models import Hypothesis, TestReport

GOOD = {
    "root_cause": "off by one",
    "hypotheses": [
        {"title": "exclusive end date", "strategy": "add one", "target_files": ["src/a.py"]},
        {"title": "wrong constant", "strategy": "use 30"},
    ],
}


def _diagnose(llm, **kw):
    return diagnose(
        llm,
        tier="super",
        test_command="pytest -q",
        report=TestReport(total=2, passed=1, failed=1),
        stdout="assert 29 == 30",
        stderr="",
        sources={"src/a.py": "x = 1"},
        file_index=["src/a.py"],
        **kw,
    )


def test_diagnose_reads_hypotheses():
    hypotheses, meta = _diagnose(ScriptedLLM(responses={"super": [GOOD]}))
    assert [h.title for h in hypotheses] == ["exclusive end date", "wrong constant"]
    assert hypotheses[0].target_files == ["src/a.py"]
    assert meta["root_cause"] == "off by one"
    assert meta["attempts"] == 1


def test_diagnose_respects_the_fanout_cap():
    hypotheses, _ = _diagnose(ScriptedLLM(responses={"super": [GOOD]}), fanout=1)
    assert len(hypotheses) == 1


def test_diagnose_retries_once_when_the_model_returns_nothing():
    """An empty diagnosis ends the expansion after the call is already paid for."""
    llm = ScriptedLLM(responses={"super": [{}, GOOD]})
    hypotheses, meta = _diagnose(llm)
    assert len(hypotheses) == 2
    assert meta["attempts"] == 2
    assert len(llm.calls) == 2
    assert "no usable hypotheses" in llm.calls[1][1], "the retry tells the model what went wrong"


def test_diagnose_gives_up_after_the_retry_and_says_what_came_back():
    llm = ScriptedLLM(responses={"super": [{"root_cause": "hmm"}, {"root_cause": "hmm"}]})
    hypotheses, meta = _diagnose(llm)
    assert hypotheses == []
    assert meta["attempts"] == 2
    assert meta["reply_keys"] == ["root_cause"]


def test_diagnose_skips_malformed_hypotheses():
    llm = ScriptedLLM(
        responses={"super": [{"hypotheses": ["not a dict", {}, {"strategy": "only a strategy"}]}]}
    )
    hypotheses, _ = _diagnose(llm)
    assert [h.title for h in hypotheses] == ["only a strategy"], "a bare strategy still names itself"


def test_diagnose_searches_only_when_the_cause_is_external():
    class Tavily:
        enabled = True

        def __init__(self):
            self.queries: list[str] = []

        def search(self, query):
            self.queries.append(query)
            return "the API moved", []

        @staticmethod
        def render(answer, hits):
            return answer

    tavily = Tavily()
    _diagnose(ScriptedLLM(responses={"super": [GOOD]}), tavily=tavily)
    assert tavily.queries == [], "a repo-local failure must not hit the network"

    external = {**GOOD, "needs_external_docs": True, "search_query": "pydantic root_validator v2"}
    _, meta = _diagnose(ScriptedLLM(responses={"super": [external, GOOD]}), tavily=tavily)
    assert tavily.queries == ["pydantic root_validator v2"]
    assert meta["searched"] is True


def _propose(llm):
    return propose_patch(
        llm,
        tier="nano",
        hypothesis=Hypothesis(id="h1", title="t", strategy="s"),
        root_cause="rc",
        test_command="pytest -q",
        report=None,
        stdout="",
        stderr="",
        sources={"src/a.py": "x = 1"},
    )


def test_propose_patch_reads_search_replace_edits():
    edits, explanation = _propose(
        ScriptedLLM(
            responses={"nano": [{"explanation": "why", "edits": [{"path": "a.py", "search": "x", "replace": "y"}]}]}
        )
    )
    assert explanation == "why"
    assert (edits[0].path, edits[0].search, edits[0].replace) == ("a.py", "x", "y")


def test_propose_patch_reads_whole_file_rewrites():
    edits, _ = _propose(ScriptedLLM(responses={"nano": [{"edits": [{"path": "a.py", "new_content": "z = 1"}]}]}))
    assert edits[0].is_rewrite


def test_propose_patch_drops_edits_it_cannot_use():
    edits, _ = _propose(
        ScriptedLLM(
            responses={
                "nano": [
                    {
                        "edits": [
                            "not a dict",
                            {"search": "x", "replace": "y"},   # no path
                            {"path": "a.py"},                   # nothing to do
                            {"path": "b.py", "search": "x", "replace": "y"},
                        ]
                    }
                ]
            }
        )
    )
    assert [e.path for e in edits] == ["b.py"]


def test_propose_patch_drops_a_search_with_no_replace():
    """Ambiguous between a deletion and a truncated reply — and one of those deletes working code."""
    edits, _ = _propose(ScriptedLLM(responses={"nano": [{"edits": [{"path": "a.py", "search": "drop me"}]}]}))
    assert edits == []
