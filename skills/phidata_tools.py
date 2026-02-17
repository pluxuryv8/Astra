from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib import error, parse, request

"""
Lightweight local adaptation inspired by Phidata/Agno toolkits:
- tmp/phidata/libs/agno/agno/tools/toolkit.py
- tmp/phidata/libs/agno/agno/tools/knowledge.py
- tmp/phidata/libs/agno/agno/tools/shell.py
- tmp/phidata/libs/agno/agno/tools/websearch.py

No external dependencies are required.
"""


@dataclass(slots=True)
class ToolSpec:
    name: str
    entrypoint: Callable[..., Any]
    description: str


class Toolkit:
    def __init__(self, name: str = "toolkit") -> None:
        self.name = name
        self._tools: dict[str, ToolSpec] = {}

    def register(self, func: Callable[..., Any], *, name: str | None = None, description: str = "") -> None:
        tool_name = (name or func.__name__).strip()
        if not tool_name:
            raise ValueError("tool_name_required")
        self._tools[tool_name] = ToolSpec(name=tool_name, entrypoint=func, description=description.strip())

    def call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        spec = self._tools.get(name)
        if spec is None:
            raise KeyError(f"tool_not_found: {name}")
        return spec.entrypoint(*args, **kwargs)

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())


class PhidataTools(Toolkit):
    def __init__(self, workspace: Path | None = None) -> None:
        super().__init__(name="phidata_tools")
        self.workspace = workspace or Path(".")
        self.register(
            self.web_search,
            name="web_search",
            description="Search the web for query context.",
        )
        self.register(
            self.shell,
            name="shell",
            description="Run a shell command and return short output.",
        )
        self.register(
            self.rag,
            name="rag",
            description="Retrieve relevant context from history and tool docs.",
        )

    def web_search(self, query: str, max_results: int = 5) -> dict[str, Any]:
        query_text = (query or "").strip()
        if not query_text:
            return {"query": "", "results": [], "source": "empty_query"}

        url = (
            "https://duckduckgo.com/?"
            + parse.urlencode(
                {
                    "q": query_text,
                    "format": "json",
                    "no_redirect": "1",
                    "no_html": "1",
                }
            )
        )
        req = request.Request(url, headers={"User-Agent": "Astra-PhidataTools/1.0"})

        try:
            with request.urlopen(req, timeout=6) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(body)
            results: list[dict[str, Any]] = []
            abstract = str(parsed.get("AbstractText") or "").strip()
            if abstract:
                results.append(
                    {
                        "title": str(parsed.get("Heading") or "DuckDuckGo"),
                        "snippet": abstract,
                        "url": str(parsed.get("AbstractURL") or "").strip(),
                    }
                )
            topics = parsed.get("RelatedTopics") if isinstance(parsed, dict) else []
            if isinstance(topics, list):
                for item in topics:
                    if not isinstance(item, dict):
                        continue
                    text = str(item.get("Text") or "").strip()
                    if not text:
                        continue
                    results.append(
                        {
                            "title": text.split(" - ")[0][:120],
                            "snippet": text[:240],
                            "url": str(item.get("FirstURL") or "").strip(),
                        }
                    )
                    if len(results) >= max(1, max_results):
                        break
            return {
                "query": query_text,
                "results": results[: max(1, max_results)],
                "source": "duckduckgo_instant_answer",
            }
        except (error.URLError, json.JSONDecodeError):
            return {
                "query": query_text,
                "results": [],
                "source": "duckduckgo_unavailable",
            }

    def shell(
        self,
        args: list[str],
        *,
        tail: int = 60,
        timeout_s: int = 8,
    ) -> dict[str, Any]:
        if not isinstance(args, list) or not args or not all(isinstance(item, str) for item in args):
            return {
                "ok": False,
                "error": "invalid_args",
                "stdout": "",
                "stderr": "",
                "returncode": 2,
            }

        try:
            proc = subprocess.run(
                args,
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                timeout=max(1, int(timeout_s)),
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "error": str(exc),
                "stdout": "",
                "stderr": "",
                "returncode": 1,
            }

        stdout_tail = "\n".join((proc.stdout or "").splitlines()[-max(1, tail) :])
        stderr_tail = "\n".join((proc.stderr or "").splitlines()[-max(1, tail) :])
        return {
            "ok": proc.returncode == 0,
            "error": "" if proc.returncode == 0 else "command_failed",
            "stdout": stdout_tail,
            "stderr": stderr_tail,
            "returncode": proc.returncode,
            "command": args,
        }

    def rag(
        self,
        history: list[dict[str, Any]] | None,
        *,
        query: str | None = None,
        max_results: int = 4,
    ) -> dict[str, Any]:
        history = history if isinstance(history, list) else []
        corpus = _build_corpus(history)

        query_text = (query or "").strip() or _latest_user_text(history)
        q_tokens = _tokens(query_text)

        scored: list[tuple[float, dict[str, Any]]] = []
        for idx, item in enumerate(corpus):
            text = str(item.get("text") or "")
            t_tokens = _tokens(text)
            overlap = len(q_tokens.intersection(t_tokens)) if q_tokens else 0
            recency = max(0.0, 1.0 - (idx / max(1, len(corpus))))
            score = float(overlap) + recency * 0.25
            if q_tokens and overlap == 0:
                continue
            scored.append((score, item))

        if not q_tokens:
            scored = [(1.0, item) for item in corpus]

        scored.sort(key=lambda pair: pair[0], reverse=True)
        top = scored[: max(1, max_results)]

        hits = [
            {
                "source": item.get("source"),
                "text": str(item.get("text") or "")[:320],
                "score": round(score, 4),
            }
            for score, item in top
        ]

        recommended_tools = _recommended_tools(query_text)
        summary = "\n".join(f"- {hit['source']}: {hit['text'][:120]}" for hit in hits)
        return {
            "query": query_text,
            "hit_count": len(hits),
            "hits": hits,
            "recommended_tools": recommended_tools,
            "summary": summary[:1600],
        }


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_+-]+", (text or "").lower())
        if len(token) >= 3
    }


def _latest_user_text(history: list[dict[str, Any]]) -> str:
    for item in reversed(history):
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "").lower() != "user":
            continue
        content = item.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ""


def _build_corpus(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    corpus: list[dict[str, Any]] = [
        {
            "source": "tool:web_search",
            "text": "web_search: external web context, links, facts, quick discovery",
        },
        {
            "source": "tool:shell",
            "text": "shell: terminal commands, diagnostics, scripts, local automation",
        },
    ]

    for idx, item in enumerate(reversed(history[-20:])):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").lower()
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        corpus.append(
            {
                "source": f"history:{idx}:{role}",
                "text": content.strip(),
            }
        )
    return corpus


def _recommended_tools(query: str) -> list[str]:
    text = (query or "").lower()
    tools: list[str] = []

    if any(token in text for token in ("найд", "поиск", "search", "web", "новост", "источник")):
        tools.append("web_search")
    if any(token in text for token in ("shell", "terminal", "bash", "команд", "скрипт", "cli")):
        tools.append("shell")

    if not tools:
        tools = ["web_search", "shell"]
    return tools


_DEFAULT = PhidataTools()


def rag(
    history: list[dict[str, Any]] | None,
    *,
    query: str | None = None,
    max_results: int = 4,
) -> dict[str, Any]:
    return _DEFAULT.rag(history, query=query, max_results=max_results)


def available_tools() -> list[str]:
    return _DEFAULT.list_tools()


def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    return _DEFAULT.web_search(query, max_results=max_results)


def shell(args: list[str], *, tail: int = 60, timeout_s: int = 8) -> dict[str, Any]:
    return _DEFAULT.shell(args, tail=tail, timeout_s=timeout_s)


__all__ = [
    "Toolkit",
    "PhidataTools",
    "ToolSpec",
    "rag",
    "available_tools",
    "web_search",
    "shell",
]
