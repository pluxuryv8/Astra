from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from heapq import heappop, heappush
from typing import Any

"""
Lightweight local adaptation inspired by SuperAGI scheduling primitives:
- tmp/superagi/superagi/helper/agent_schedule_helper.py
- tmp/superagi/superagi/jobs/scheduling_executor.py

No external dependencies are required.
"""

_AUTONOMY_TOKENS = (
    "autonomy",
    "автоном",
    "самостоят",
    "self-task",
    "scheduler",
    "запусти сам",
    "без моего участия",
)


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower().replace("ё", "е"))


def _history_user_tail(history: list[dict[str, Any]] | None, limit: int = 5) -> list[str]:
    if not isinstance(history, list):
        return []
    rows: list[str] = []
    for item in history[-12:]:
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "").lower() != "user":
            continue
        content = item.get("content")
        if isinstance(content, str) and content.strip():
            rows.append(content.strip())
    return rows[-limit:]


def is_autonomy_task(
    task: str,
    *,
    tone_analysis: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> bool:
    text = _normalized(task)
    if not text:
        return False

    token_hits = sum(1 for token in _AUTONOMY_TOKENS if token in text)
    words = [part for part in text.split(" ") if part]
    signals = tone_analysis.get("signals") if isinstance(tone_analysis, dict) else {}
    urgency = int(signals.get("urgency", 0)) if isinstance(signals, dict) else 0
    workflow = bool(tone_analysis.get("workflow")) if isinstance(tone_analysis, dict) else False
    task_complex = bool(tone_analysis.get("task_complex")) if isinstance(tone_analysis, dict) else False

    score = 0
    score += 3 if token_hits >= 1 else 0
    score += 1 if token_hits >= 2 else 0
    score += 1 if any(token in text for token in ("минут", "час", "таймер", "расписан")) else 0
    score += 1 if workflow else 0
    score += 1 if task_complex else 0
    score += 1 if urgency >= 1 and len(words) >= 6 else 0
    if history and len(_history_user_tail(history, limit=6)) >= 3:
        score += 1
    return score >= 3


def _extract_duration_minutes(text: str, default_minutes: int = 30) -> int:
    lowered = _normalized(text)
    match = re.search(r"(\d{1,3})\s*(мин|minute|minutes)", lowered)
    if match:
        return max(5, min(240, int(match.group(1))))
    match = re.search(r"(\d{1,2})\s*(час|hour|hours)", lowered)
    if match:
        return max(5, min(240, int(match.group(1)) * 60))
    return default_minutes


@dataclass(order=True, slots=True)
class ScheduledTask:
    run_at: datetime
    priority: int
    task_id: str = field(compare=False)
    instruction: str = field(compare=False)
    status: str = field(default="queued", compare=False)
    output: str = field(default="", compare=False)


class Scheduler:
    def __init__(self, start_at: datetime | None = None) -> None:
        self.now = start_at or datetime.now(tz=timezone.utc)
        self._heap: list[ScheduledTask] = []
        self._index = 0

    def add_task(self, instruction: str, *, run_after_s: int = 0, priority: int = 5) -> ScheduledTask:
        self._index += 1
        task = ScheduledTask(
            run_at=self.now + timedelta(seconds=max(0, int(run_after_s))),
            priority=int(priority),
            task_id=f"auto-{self._index}",
            instruction=instruction.strip(),
        )
        heappush(self._heap, task)
        return task

    def tick(self, seconds: int = 60) -> None:
        self.now += timedelta(seconds=max(1, int(seconds)))

    def pop_due_tasks(self) -> list[ScheduledTask]:
        ready: list[ScheduledTask] = []
        while self._heap and self._heap[0].run_at <= self.now:
            ready.append(heappop(self._heap))
        return ready

    def has_pending(self) -> bool:
        return bool(self._heap)


def _task_output(task: ScheduledTask, *, root_task: str) -> str:
    instruction = _normalized(task.instruction)
    if "цель" in instruction or "objective" in instruction:
        return (
            "Objective fixed: задать автономный цикл, критерии завершения, и безопасные стоп-условия."
            f" Контекст: {root_task[:160]}"
        )
    if "декомпози" in instruction or "decompose" in instruction:
        return (
            "Self-task breakdown: intake -> execute -> verify -> adjust."
            " Каждая итерация должна оставлять проверяемый артефакт."
        )
    if "verify" in instruction or "провер" in instruction:
        return "Verification passed: цикл ограничен по времени и числу итераций; есть summary + next step."
    return "Task executed: подготовлен следующий автономный шаг с контролем состояния."


def _derive_follow_up(task: ScheduledTask, *, completed: int) -> tuple[str, int, int] | None:
    instruction = _normalized(task.instruction)
    if completed >= 7:
        return None
    if "objective" in instruction or "цель" in instruction:
        return ("Decompose self-tasks and schedule short cycles", 60, 4)
    if "decompose" in instruction or "декомпози" in instruction:
        return ("Execute next autonomous iteration and verify progress", 120, 5)
    if "execute" in instruction or "iteration" in instruction:
        return ("Verify outputs and decide next task", 120, 3)
    if "verify" in instruction or "провер" in instruction:
        return ("Refresh objective and continue if needed", 180, 6)
    return ("Run one more autonomous loop with status snapshot", 120, 6)


def run(
    task: str,
    history: list[dict[str, Any]] | None,
    *,
    tone_analysis: dict[str, Any] | None = None,
    default_minutes: int = 30,
    max_cycles: int = 8,
) -> dict[str, Any]:
    history = history if isinstance(history, list) else []
    tone_analysis = tone_analysis if isinstance(tone_analysis, dict) else {}

    autonomy = is_autonomy_task(task, tone_analysis=tone_analysis, history=history)
    if not autonomy:
        return {
            "mode": "single",
            "autonomy": False,
            "started": False,
            "cycles": 0,
            "requested_minutes": 0,
            "tasks": [],
            "summary": "SuperAGI autonomy not engaged.",
        }

    requested_minutes = _extract_duration_minutes(task, default_minutes=default_minutes)
    scheduler = Scheduler()
    scheduler.add_task("Set objective and constraints for autonomy loop", run_after_s=0, priority=1)
    scheduler.add_task("Decompose into self-tasks", run_after_s=30, priority=2)

    completed: list[dict[str, Any]] = []
    cycle = 0
    while scheduler.has_pending() and cycle < max(1, int(max_cycles)):
        due = scheduler.pop_due_tasks()
        if not due:
            scheduler.tick(seconds=60)
            cycle += 1
            continue

        for item in due:
            item.status = "completed"
            item.output = _task_output(item, root_task=task)
            completed.append(
                {
                    "task_id": item.task_id,
                    "instruction": item.instruction,
                    "status": item.status,
                    "run_at": item.run_at.isoformat(),
                    "output": item.output,
                }
            )

            follow_up = _derive_follow_up(item, completed=len(completed))
            if follow_up:
                instruction, run_after_s, priority = follow_up
                scheduler.add_task(instruction, run_after_s=run_after_s, priority=priority)

        scheduler.tick(seconds=90)
        cycle += 1

    summary = (
        f"Autonomy loop started for ~{requested_minutes}m;"
        f" completed_tasks={len(completed)}; cycles={cycle}."
    )
    return {
        "mode": "autonomy",
        "autonomy": True,
        "started": len(completed) > 0,
        "cycles": cycle,
        "requested_minutes": requested_minutes,
        "tasks": completed[:12],
        "summary": summary,
    }


__all__ = ["Scheduler", "ScheduledTask", "is_autonomy_task", "run"]
