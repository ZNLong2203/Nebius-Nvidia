"""Nemotron access through Nebius Token Factory.

The three tiers are not decoration. The search spends its calls like this:

===========  ========================  ==============================================
tier         model                     used for
===========  ========================  ==============================================
``nano``     Nemotron 3 Nano 30B A3B   one call per candidate patch -- the wide,
                                       disposable work. Most branches are thrown
                                       away, so they must be cheap.
``super``    Nemotron 3 Super 120B     one diagnosis per node: read the failure,
                                       name the root cause, propose distinct
                                       hypotheses worth branching on.
``ultra``    Nemotron 3 Ultra 550B     only when the search stalls or two branches
                                       score the same. Expensive, so it is rare.
===========  ========================  ==============================================

:class:`Usage` keeps the per-tier token counts that the report prints, which is
how the cost claim in the README stays checkable.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import Settings


@dataclass
class Usage:
    prompt: int = 0
    completion: int = 0
    calls: int = 0

    def add(self, prompt: int, completion: int) -> None:
        self.prompt += prompt
        self.completion += completion
        self.calls += 1

    @property
    def total(self) -> int:
        return self.prompt + self.completion

    def to_dict(self) -> dict[str, int]:
        return {
            "calls": self.calls,
            "prompt_tokens": self.prompt,
            "completion_tokens": self.completion,
            "total_tokens": self.total,
        }


class BudgetExceeded(RuntimeError):
    pass


class LLM(Protocol):
    def json(self, tier: str, system: str, user: str, schema: dict | None = None, **kw) -> dict: ...
    def text(self, tier: str, system: str, user: str, **kw) -> str: ...


class NemotronClient:
    """Thin OpenAI-compatible client pointed at Token Factory."""

    def __init__(self, settings: Settings) -> None:
        from openai import OpenAI

        self._settings = settings
        self._client = OpenAI(
            base_url=settings.nebius_base_url,
            api_key=settings.nebius_api_key,
            timeout=300.0,
            max_retries=2,
        )
        self._models = settings.models
        self._budget = settings.token_budget
        self._lock = threading.Lock()
        self.usage: dict[str, Usage] = {tier: Usage() for tier in self._models}

    # -- accounting ---------------------------------------------------------
    @property
    def tokens_used(self) -> int:
        return sum(u.total for u in self.usage.values())

    def usage_report(self) -> dict[str, Any]:
        return {
            "by_tier": {t: u.to_dict() for t, u in self.usage.items()},
            "models": dict(self._models),
            "total_tokens": self.tokens_used,
            "budget": self._budget,
        }

    def _charge(self, tier: str, response) -> None:
        usage = getattr(response, "usage", None)
        prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion = int(getattr(usage, "completion_tokens", 0) or 0)
        with self._lock:
            self.usage[tier].add(prompt, completion)
            if self.tokens_used > self._budget:
                raise BudgetExceeded(
                    f"token budget exhausted: {self.tokens_used} > {self._budget}"
                )

    # -- calls --------------------------------------------------------------
    def _chat(
        self,
        tier: str,
        system: str,
        user: str,
        *,
        response_format: dict | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ):
        model = self._models[tier]
        with self._lock:
            if self.tokens_used > self._budget:
                raise BudgetExceeded(f"token budget exhausted before call to {model}")
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format
        response = self._client.chat.completions.create(**kwargs)
        self._charge(tier, response)
        return response.choices[0].message.content or ""

    def text(self, tier: str, system: str, user: str, **kw) -> str:
        return self._chat(tier, system, user, **kw)

    def json(self, tier: str, system: str, user: str, schema: dict | None = None, **kw) -> dict:
        """Ask for JSON, strictly if the model supports it, leniently otherwise."""
        fmt: dict | None
        if schema:
            fmt = {
                "type": "json_schema",
                "json_schema": {"name": "arborist_response", "strict": False, "schema": schema},
            }
        else:
            fmt = {"type": "json_object"}

        try:
            raw = self._chat(tier, system, user, response_format=fmt, **kw)
        except BudgetExceeded:
            raise
        except Exception:  # noqa: BLE001 - retry once without the strict format
            raw = self._chat(tier, system, user, response_format={"type": "json_object"}, **kw)
        return parse_json(raw)


def parse_json(raw: str) -> dict:
    """Recover a JSON object from a model response.

    Reasoning models like to wrap output in prose or fences, and a whole search
    branch should never be lost to a stray backtick.
    """
    if not raw:
        return {}
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {"value": value}
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return {}


@dataclass
class ScriptedLLM:
    """Deterministic stand-in used by the test suite.

    Responses are keyed by tier and popped in order; anything unscripted returns
    an empty object, which the search must survive.
    """

    responses: dict[str, list[dict]] = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list)
    usage: dict[str, Usage] = field(default_factory=lambda: {t: Usage() for t in ("nano", "super", "ultra")})

    def _next(self, tier: str) -> dict:
        queue = self.responses.get(tier) or []
        self.usage.setdefault(tier, Usage()).add(10, 10)
        return queue.pop(0) if queue else {}

    def json(self, tier: str, system: str, user: str, schema: dict | None = None, **kw) -> dict:
        self.calls.append((tier, user[:200]))
        return self._next(tier)

    def text(self, tier: str, system: str, user: str, **kw) -> str:
        self.calls.append((tier, user[:200]))
        return json.dumps(self._next(tier))

    @property
    def tokens_used(self) -> int:
        return sum(u.total for u in self.usage.values())

    def usage_report(self) -> dict[str, Any]:
        return {
            "by_tier": {t: u.to_dict() for t, u in self.usage.items()},
            "models": {"nano": "scripted", "super": "scripted", "ultra": "scripted"},
            "total_tokens": self.tokens_used,
            "budget": 0,
        }
