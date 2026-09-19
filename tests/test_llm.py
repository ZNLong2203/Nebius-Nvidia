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
