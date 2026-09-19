"""Tavily search, used as a last-resort tool during diagnosis.

Arborist only reaches for the web when the failure points *outside* the
repository: an exception raised inside a third-party package, a version-pinned
API that changed, a deprecation the code has not caught up with. Those are
exactly the bugs a repo-local agent cannot reason its way out of, because the
answer is not in the context window and never was.

The diagnosis step decides this itself and emits a query; nothing else in the
search touches the network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx

TAVILY_URL = "https://api.tavily.com/search"


@dataclass
class SearchHit:
    title: str
    url: str
    content: str
    score: float = 0.0

    def to_dict(self) -> dict:
        return {"title": self.title, "url": self.url, "content": self.content, "score": self.score}


@dataclass
class TavilyClient:
    api_key: str
    max_results: int = 4
    timeout: float = 25.0
    queries: list[str] = field(default_factory=list)
    _cache: dict[str, tuple[str, list[SearchHit]]] = field(default_factory=dict)

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str) -> tuple[str, list[SearchHit]]:
        """Return ``(answer, hits)``. Never raises: search is an optimisation."""
        if not self.enabled or not query.strip():
            return "", []
        key = query.strip().lower()
        if key in self._cache:
            return self._cache[key]

        self.queries.append(query)
        try:
            response = httpx.post(
                TAVILY_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "query": query,
                    "search_depth": "advanced",
                    "max_results": self.max_results,
                    "include_answer": True,
                    "topic": "general",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:  # noqa: BLE001 - degrade to no evidence
            self._cache[key] = ("", [])
            return "", []

        hits = [
            SearchHit(
                title=item.get("title", ""),
                url=item.get("url", ""),
                content=(item.get("content") or "")[:1200],
                score=float(item.get("score") or 0.0),
            )
            for item in payload.get("results", [])
        ]
        answer = payload.get("answer") or ""
        self._cache[key] = (answer, hits)
        return answer, hits

    @staticmethod
    def render(answer: str, hits: list[SearchHit]) -> str:
        if not answer and not hits:
            return ""
        parts = []
        if answer:
            parts.append(f"Summary: {answer}")
        for hit in hits:
            parts.append(f"[{hit.title}]({hit.url})\n{hit.content}")
        return "\n\n".join(parts)

    def log(self) -> str:
        return json.dumps(self.queries)
