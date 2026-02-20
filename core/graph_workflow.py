from __future__ import annotations

import json
import os
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib import error, parse, request

"""
Lightweight local adaptation inspired by LangGraph primitives:
- tmp/langgraph/libs/langgraph/langgraph/graph/state.py
- tmp/langgraph/libs/langgraph/langgraph/constants.py

This module provides a minimal stateful graph runtime without external deps.
"""

START = "__start__"
END = "__end__"

_WORKFLOW_TOKENS = (
    "workflow",
    "воркфло",
    "граф",
    "pipeline",
    "пайплайн",
    "оркестрац",
    "схем",
    "stateful",
)


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _history_user_tail(history: list[dict[str, Any]], limit: int = 5) -> list[str]:
    lines: list[str] = []
    for item in history[-12:]:
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "").lower() != "user":
            continue
        content = item.get("content")
        if isinstance(content, str) and content.strip():
            lines.append(content.strip())
    return lines[-limit:]


def is_workflow_task(
    task: str,
    *,
    tone_analysis: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> bool:
    text = _normalized(task)
    if not text:
        return False

    words = [part for part in text.split(" ") if part]
    token_hits = sum(1 for token in _WORKFLOW_TOKENS if token in text)
    signals = tone_analysis.get("signals") if isinstance(tone_analysis, dict) else {}
    technical = int(signals.get("technical_density", 0)) if isinstance(signals, dict) else 0
    task_complex = bool(tone_analysis.get("task_complex")) if isinstance(tone_analysis, dict) else False

    score = 0
    score += 3 if token_hits >= 1 else 0
    score += 1 if token_hits >= 2 else 0
    score += 1 if len(words) >= 12 else 0
    score += 1 if len(words) >= 20 else 0
    score += 1 if technical >= 2 else 0
    score += 1 if task_complex else 0
    if history:
        score += 1 if len(_history_user_tail(history, limit=6)) >= 3 else 0

    return score >= 3


@dataclass(slots=True)
class NodeSpec:
    name: str
    node: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


@dataclass(slots=True)
class StateGraph:
    nodes: dict[str, NodeSpec] = field(default_factory=dict)
    edges: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))

    def add_node(
        self,
        name: str,
        node: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    ) -> "StateGraph":
        if not name:
            raise ValueError("node_name_required")
        self.nodes[name] = NodeSpec(name=name, node=node)
        return self

    def add_edge(self, start: str, end: str) -> "StateGraph":
        if not start or not end:
            raise ValueError("edge_requires_start_end")
        self.edges[start].append(end)
        return self

    def compile(self) -> "CompiledStateGraph":
        return CompiledStateGraph(nodes=dict(self.nodes), edges={k: list(v) for k, v in self.edges.items()})


@dataclass(slots=True)
class CompiledStateGraph:
    nodes: dict[str, NodeSpec]
    edges: dict[str, list[str]]

    def invoke(
        self,
        state: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
        max_steps: int = 20,
    ) -> dict[str, Any]:
        runtime_state = dict(state or {})
        runtime_context = dict(context or {})
        queue: deque[str] = deque(self.edges.get(START, []))
        steps = 0
        trace: list[dict[str, Any]] = []

        while queue and steps < max_steps:
            node_name = queue.popleft()
            if node_name == END:
                break
            spec = self.nodes.get(node_name)
            if spec is None:
                continue

            update = spec.node(dict(runtime_state), runtime_context)
            if not isinstance(update, dict):
                update = {"result": str(update)}

            next_nodes: list[str] = []
            if "_next" in update:
                raw_next = update.pop("_next")
                if isinstance(raw_next, str):
                    next_nodes = [raw_next]
                elif isinstance(raw_next, list):
                    next_nodes = [item for item in raw_next if isinstance(item, str)]

            runtime_state.update(update)
            trace.append(
                {
                    "node": node_name,
                    "updated_keys": sorted(update.keys()),
                }
            )

            if next_nodes:
                for target in next_nodes:
                    if target == END:
                        queue.clear()
                        break
                    queue.append(target)
            else:
                for target in self.edges.get(node_name, []):
                    if target == END:
                        queue.clear()
                        break
                    queue.append(target)

            steps += 1

        runtime_state["trace"] = trace
        runtime_state["workflow_steps"] = steps
        runtime_state["workflow_finished"] = bool(trace)
        runtime_state["workflow_max_steps_reached"] = steps >= max_steps and bool(queue)
        return runtime_state


@dataclass(slots=True)
class OllamaAdapter:
    base_url: str
    model: str
    timeout_s: float = 6.0
    enabled: bool = False

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        if not self.enabled:
            raise RuntimeError("ollama_adapter_disabled")

        payload = {
            "model": self.model,
            "prompt": f"{system_prompt}\n\n{user_prompt}",
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 320},
        }
        raw = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url.rstrip('/')}/api/generate",
            data=raw,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=max(0.5, self.timeout_s)) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except error.URLError as exc:
            raise RuntimeError(f"ollama_connection_failed: {exc}") from exc

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("ollama_invalid_json") from exc

        text = str(parsed.get("response") or "").strip()
        if not text:
            raise RuntimeError("ollama_empty_response")
        return text


def _heuristic_node_output(stage: str, task: str, history_tail: list[str]) -> str:
    context_hint = history_tail[-1] if history_tail else ""
    if stage == "decompose":
        return (
            "1) Цель и входы workflow.\n"
            "2) Последовательность node-этапов с критериями готовности.\n"
            f"3) Контекст: {context_hint or task[:140]}"
        )
    if stage == "implement":
        return (
            "Собрать stateful pipeline: intake -> plan -> execute -> verify.\n"
            "Добавить переходы по условиям и выход при достижении результата."
        )
    if stage == "verify":
        return (
            "Проверить инварианты: детерминированный state update, trace шагов,"
            " защита от бесконечного цикла и fallback при ошибке узла."
        )
    return "Workflow step completed."


def _run_stage(
    stage: str,
    state: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    task = str(state.get("task") or "")
    history_tail = state.get("history_tail") if isinstance(state.get("history_tail"), list) else []
    adapter = context.get("adapter")

    system_prompt = (
        "You are a workflow node in a LangGraph-style stateful execution. "
        "Return concise, practical output for your node."
    )
    user_prompt = (
        f"Stage: {stage}\n"
        f"Task: {task}\n"
        f"History tail: {history_tail}\n"
    )

    text: str
    source: str
    try:
        if isinstance(adapter, OllamaAdapter):
            text = adapter.complete(system_prompt=system_prompt, user_prompt=user_prompt)
            source = "ollama"
        else:
            raise RuntimeError("adapter_missing")
    except Exception:
        text = _heuristic_node_output(stage, task, history_tail)
        source = "heuristic"

    updates = {
        f"{stage}_output": text,
        f"{stage}_source": source,
    }

    if stage == "verify":
        updates["_next"] = END
    return updates


def _build_workflow_graph() -> CompiledStateGraph:
    graph = StateGraph()
    graph.add_node("decompose", lambda state, context: _run_stage("decompose", state, context))
    graph.add_node("implement", lambda state, context: _run_stage("implement", state, context))
    graph.add_node("verify", lambda state, context: _run_stage("verify", state, context))
    graph.add_edge(START, "decompose")
    graph.add_edge("decompose", "implement")
    graph.add_edge("implement", "verify")
    graph.add_edge("verify", END)
    return graph.compile()


def _build_adapter() -> OllamaAdapter:
    enabled = os.getenv("ASTRA_LANGGRAPH_USE_OLLAMA", "0").strip().lower() in {"1", "true", "yes", "on"}
    model = os.getenv(
        "ASTRA_LLM_LOCAL_CHAT_MODEL_COMPLEX",
        os.getenv("ASTRA_LLM_LOCAL_CHAT_MODEL", "wizardlm-uncensored:13b"),
    )
    timeout_raw = os.getenv("ASTRA_LANGGRAPH_OLLAMA_TIMEOUT_S", "5")
    try:
        timeout_s = float(timeout_raw)
    except ValueError:
        timeout_s = 5.0
    base_url = os.getenv("ASTRA_LLM_LOCAL_BASE_URL", "http://127.0.0.1:11434")
    return OllamaAdapter(base_url=base_url, model=model, timeout_s=max(0.5, timeout_s), enabled=enabled)


def graph_workflow(
    task: str,
    history: list[dict[str, Any]] | None,
    *,
    tone_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    history = history if isinstance(history, list) else []
    workflow_required = is_workflow_task(task, tone_analysis=tone_analysis, history=history)
    if not workflow_required:
        return {
            "mode": "single",
            "workflow": False,
            "executed": False,
            "summary": "Workflow graph not engaged.",
            "state": {},
        }

    compiled = _build_workflow_graph()
    state = {
        "task": (task or "").strip(),
        "history_tail": _history_user_tail(history),
    }
    adapter = _build_adapter()
    result_state = compiled.invoke(state, context={"adapter": adapter})

    summary_lines = [
        f"- decompose: {str(result_state.get('decompose_output') or '').splitlines()[0]}",
        f"- implement: {str(result_state.get('implement_output') or '').splitlines()[0]}",
        f"- verify: {str(result_state.get('verify_output') or '').splitlines()[0]}",
    ]

    return {
        "mode": "workflow",
        "workflow": True,
        "executed": True,
        "summary": "\n".join(summary_lines)[:1800],
        "state": result_state,
    }


__all__ = [
    "START",
    "END",
    "StateGraph",
    "CompiledStateGraph",
    "OllamaAdapter",
    "graph_workflow",
    "is_workflow_task",
]
