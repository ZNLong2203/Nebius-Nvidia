from arborist.llm import ScriptedLLM, Usage, parse_json


def test_parse_json_reads_a_bare_object():
    assert parse_json('{"a": 1}') == {"a": 1}


def test_parse_json_unwraps_a_fenced_block():
    assert parse_json('```json\n{"a": [1, 2]}\n```') == {"a": [1, 2]}


def test_parse_json_survives_surrounding_prose():
    raw = 'Here is my analysis.\n{"root_cause": "off by one"}\nHope that helps!'
    assert parse_json(raw) == {"root_cause": "off by one"}


def test_parse_json_handles_braces_inside_strings():
    raw = 'thinking...\n{"replace": "if x: {y}", "n": 1}'
    assert parse_json(raw)["replace"] == "if x: {y}"


def test_parse_json_skips_a_broken_first_object():
    raw = '{"broken": ,}\ntrailing\n{"good": true}'
    assert parse_json(raw) == {"good": True}


def test_parse_json_returns_empty_on_hopeless_input():
    assert parse_json("no json here") == {}
    assert parse_json("") == {}


def test_parse_json_wraps_a_non_object():
    assert parse_json("[1, 2]") == {"value": [1, 2]}


def test_usage_accumulates():
    u = Usage()
    u.add(10, 5)
    u.add(1, 1)
    assert (u.calls, u.prompt, u.completion, u.total) == (2, 11, 6, 17)


def test_scripted_llm_pops_in_order_then_degrades_to_empty():
    llm = ScriptedLLM(responses={"nano": [{"a": 1}, {"b": 2}]})
    assert llm.json("nano", "s", "u") == {"a": 1}
    assert llm.json("nano", "s", "u") == {"b": 2}
    assert llm.json("nano", "s", "u") == {}
    assert llm.tokens_used > 0


# --------------------------------------------------------------------------- #
# cost
# --------------------------------------------------------------------------- #


def test_usage_is_priced_per_model():
    from arborist.config import MODEL_NANO, MODEL_ULTRA

    u = Usage()
    u.add(1_000_000, 1_000_000)
    assert round(u.cost(MODEL_NANO), 4) == 0.30
    assert round(u.cost(MODEL_ULTRA), 4) == 4.00, "Ultra is the expensive tier"
    assert u.cost("some/unpriced-model") == 0.0


class _Response:
    def __init__(self, prompt: int, completion: int) -> None:
        self.usage = type("U", (), {"prompt_tokens": prompt, "completion_tokens": completion})()
        message = type("M", (), {"content": '{"ok": true}', "reasoning_content": None})()
        self.choices = [type("C", (), {"message": message, "finish_reason": "stop"})()]


def _client(max_cost: float, per_call: tuple[int, int], token_budget: int = 10_000_000):
    """A NemotronClient whose API answers every call with a fixed token count."""
    from arborist.config import load_settings
    from arborist.llm import NemotronClient

    client = NemotronClient(load_settings(nebius_api_key="test", max_cost=max_cost, token_budget=token_budget))
    calls = []

    def create(**kwargs):
        calls.append(kwargs["model"])
        return _Response(*per_call)

    client._client = type("O", (), {"chat": type("C", (), {"completions": type("X", (), {"create": staticmethod(create)})()})()})()
    return client, calls


def test_a_run_stops_calling_models_once_it_reaches_its_cost_limit():
    import pytest

    from arborist.llm import BudgetExceeded

    # 200k prompt tokens on Ultra is $0.20 a call; the limit is $0.50.
    client, calls = _client(max_cost=0.50, per_call=(200_000, 0))
    client.json("ultra", "s", "u")
    client.json("ultra", "s", "u")
    with pytest.raises(BudgetExceeded, match="cost limit"):
        client.json("ultra", "s", "u")  # the third call crosses the limit
    with pytest.raises(BudgetExceeded, match="not calling"):
        client.json("nano", "s", "u")  # and nothing is sent after that
    assert len(calls) == 3


def test_the_report_carries_dollars_per_tier_and_in_total():
    client, _ = _client(max_cost=0, per_call=(1_000_000, 0))
    client.json("nano", "s", "u")
    client.json("ultra", "s", "u")
    report = client.usage_report()
    assert report["by_tier"]["nano"]["cost_usd"] == 0.06
    assert report["by_tier"]["ultra"]["cost_usd"] == 1.0
    assert report["cost_usd"] == 1.06
    assert report["max_cost_usd"] == 0, "0 means no limit, and no limit stopped the second call"
