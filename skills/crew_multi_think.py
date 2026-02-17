from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any
from urllib import error, request

"""
Lightweight local adaptation inspired by CrewAI core abstractions:
- tmp/crewai/lib/crewai/src/crewai/agent/core.py
- tmp/crewai/lib/crewai/src/crewai/task.py
- tmp/crewai/lib/crewai/src/crewai/crew.py

No external dependencies are required; execution can run with heuristic fallback,
and can optionally query local Ollama for each parallel agent.
"""

_COMPLEXITY_TOKENS = (
    "разбей",
    "паралл",
    "сложн",
    "архитект",
    "декомпоз",
    "стратег",
    "многошаг",
    "multi-step",
    "complex",
    "plan",
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _history_user_tail(history: list[dict[str, Any]], limit: int = 4) -> list[str]:
    user_turns: list[str] = []
    for item in history[-10:]:
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "").lower() != "user":
            continue
        content = item.get("content")
        if isinstance(content, str) and content.strip():
            user_turns.append(content.strip())
    return user_turns[-limit:]


def is_complex_task(
    task: str,
    *,
    tone_analysis: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> bool:
    text = _normalized(task)
    if not text:
        return False

    words = [part for part in re.split(r"\s+", text) if part]
    token_hits = sum(1 for token in _COMPLEXITY_TOKENS if token in text)

    signals = tone_analysis.get("signals") if isinstance(tone_analysis, dict) else {}
    urgency = int(signals.get("urgency", 0)) if isinstance(signals, dict) else 0
    technical = int(signals.get("technical_density", 0)) if isinstance(signals, dict) else 0

    score = 0
    score += 2 if len(words) >= 18 else 0
    score += 2 if len(words) >= 30 else 0
    score += 2 if token_hits >= 1 else 0
    score += 1 if token_hits >= 2 else 0
    score += 1 if text.count("?") >= 2 else 0
    score += 1 if technical >= 3 else 0
    score += 1 if urgency >= 1 and len(words) >= 12 else 0
    if history:
        score += 1 if len(_history_user_tail(history, limit=6)) >= 3 else 0

    return score >= 3


@dataclass(slots=True)
class Agent:
    role: str
    goal: str
    backstory: str = ""


@dataclass(slots=True)
class Task:
    description: str
    expected_output: str
    agent: Agent


class OllamaAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_s: float = 6.0,
        enabled: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = max(0.5, float(timeout_s))
        self.enabled = enabled

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        if not self.enabled:
            raise RuntimeError("ollama_adapter_disabled")

        payload = {
            "model": self.model,
            "prompt": f"{system_prompt}\n\n{user_prompt}",
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 260},
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_s) as resp:
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


@dataclass(slots=True)
class Crew:
    agents: list[Agent]
    tasks: list[Task]
    ollama: OllamaAdapter
    max_workers: int = 3
    _agent_index: dict[str, Agent] = field(default_factory=dict)

    def kickoff(self, *, context: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.tasks:
            return []

        self._agent_index = {agent.role: agent for agent in self.agents}
        max_workers = max(1, min(self.max_workers, len(self.tasks)))
        results: list[dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_map = {
                pool.submit(self._run_task, task, context): task
                for task in self.tasks
            }
            for future in as_completed(future_map):
                task = future_map[future]
                try:
                    results.append(future.result())
                except Exception as exc:  # noqa: BLE001
                    results.append(
                        {
                            "agent": task.agent.role,
                            "task": task.description,
                            "output": f"task_failed: {exc}",
                            "duration_ms": 0,
                            "source": "error",
                        }
                    )

        role_order = [task.agent.role for task in self.tasks]
        results.sort(key=lambda item: role_order.index(str(item.get("agent") or "")))
        return results

    def _run_task(self, task: Task, context: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        system_prompt = (
            "You are a focused sub-agent in a Crew-style parallel workflow. "
            "Answer with actionable details and no filler."
        )
        user_prompt = _compose_user_prompt(task, context)

        try:
            output = self.ollama.complete(system_prompt=system_prompt, user_prompt=user_prompt)
            source = "ollama"
        except Exception:  # noqa: BLE001
            output = _heuristic_output(task, context)
            source = "heuristic"

        duration_ms = int((time.perf_counter() - started) * 1000)
        return {
            "agent": task.agent.role,
            "task": task.description,
            "output": output.strip(),
            "duration_ms": duration_ms,
            "source": source,
        }


def _compose_user_prompt(task: Task, context: dict[str, Any]) -> str:
    root_task = str(context.get("task") or "").strip()
    history = context.get("history") if isinstance(context.get("history"), list) else []
    tail = _history_user_tail(history, limit=4)
    history_block = "\n".join(f"- {line}" for line in tail) if tail else "- empty"
    return (
        f"Root task:\n{root_task}\n\n"
        f"Sub-task:\n{task.description}\n\n"
        f"Expected output:\n{task.expected_output}\n\n"
        f"Recent user context:\n{history_block}"
    )


def _heuristic_output(task: Task, context: dict[str, Any]) -> str:
    root_task = str(context.get("task") or "").strip()
    role = task.agent.role.lower()

    if "planner" in role:
        return (
            "1) Разделить задачу на блоки: входы, ограничения, результат.\n"
            "2) Определить краткий порядок шагов и критерий готовности.\n"
            f"3) Декомпозиция по теме: {root_task[:160]}"
        )
    if "challenger" in role:
        return (
            "Риски: неясные требования, недооценка edge-cases, отсутствие тестов.\n"
            "Контроль: зафиксировать assumptions, добавить smoke + regression проверки."
        )
    return (
        "Выполнить реализацию минимальным вертикальным срезом, затем усилить:\n"
        "- сначала рабочий путь end-to-end\n"
        "- затем покрыть тестами критичные ветки\n"
        "- финально убрать технический долг в изменённых местах"
    )


def _build_default_crew(task: str, history: list[dict[str, Any]]) -> Crew:
    agents = [
        Agent(role="Planner", goal="Разложить сложную задачу на части"),
        Agent(role="Builder", goal="Предложить исполнимый план реализации"),
        Agent(role="Challenger", goal="Проверить риски и пробелы"),
    ]
    tasks = [
        Task(
            description="Сделай декомпозицию задачи и выдели 3-5 подзадач.",
            expected_output="Нумерованный план подзадач.",
            agent=agents[0],
        ),
        Task(
            description="Собери практический план внедрения с минимальным риском регрессий.",
            expected_output="Пошаговый plan-of-record.",
            agent=agents[1],
        ),
        Task(
            description="Назови риски, пробелы и обязательные тесты до релиза.",
            expected_output="Список рисков и тестов.",
            agent=agents[2],
        ),
    ]

    base_url = os.getenv("ASTRA_LLM_LOCAL_BASE_URL", "http://127.0.0.1:11434")
    model = os.getenv(
        "ASTRA_LLM_LOCAL_CHAT_MODEL_COMPLEX",
        os.getenv("ASTRA_LLM_LOCAL_CHAT_MODEL", "qwen2.5:7b-instruct"),
    )
    timeout_s = float(os.getenv("ASTRA_CREWAI_OLLAMA_TIMEOUT_S", "4"))
    use_ollama = _env_bool("ASTRA_CREWAI_USE_OLLAMA", False)

    adapter = OllamaAdapter(
        base_url=base_url,
        model=model,
        timeout_s=timeout_s,
        enabled=use_ollama,
    )
    return Crew(agents=agents, tasks=tasks, ollama=adapter)


def crew_think(
    task: str,
    history: list[dict[str, Any]] | None,
    *,
    tone_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    history = history if isinstance(history, list) else []
    complex_task = is_complex_task(task, tone_analysis=tone_analysis, history=history)
    if not complex_task:
        return {
            "mode": "single",
            "task_complex": False,
            "items": [],
            "summary": "Parallel crew not engaged.",
        }

    crew = _build_default_crew(task, history)
    items = crew.kickoff(context={"task": task, "history": history})

    summary_lines = [
        f"- {item['agent']}: {item['output'].splitlines()[0]}"
        for item in items
        if isinstance(item.get("output"), str) and item.get("output")
    ]

    return {
        "mode": "parallel",
        "task_complex": True,
        "items": items,
        "summary": "\n".join(summary_lines)[:1500],
    }


__all__ = ["Agent", "Task", "Crew", "OllamaAdapter", "crew_think", "is_complex_task"]
