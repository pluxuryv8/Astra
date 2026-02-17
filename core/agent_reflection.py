from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

"""
Lightweight local adaptation inspired by PraisonAI reflection workflows:
- tmp/praisonai/src/praisonai-agents/praisonaiagents/main.py
- tmp/praisonai/src/praisonai-agents/praisonaiagents/agent/agent.py

No external dependencies are required.
"""


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower().replace("ё", "е"))


def _history_tail(history: list[dict[str, Any]] | None, limit: int = 4) -> list[str]:
    if not isinstance(history, list):
        return []
    rows: list[str] = []
    for item in history[-12:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role != "user":
            continue
        content = item.get("content")
        if isinstance(content, str) and content.strip():
            rows.append(content.strip())
    return rows[-limit:]


@dataclass(slots=True)
class ReflectionStep:
    iteration: int
    critique: str
    adjustment: str
    score: float


def _focus_area(
    user_message: str,
    *,
    tone_type: str,
    task_complex: bool,
    workflow: bool,
    conversation: bool,
) -> str:
    text = _normalized(user_message)
    if workflow:
        return "orchestration_clarity"
    if conversation:
        return "dialog_quality"
    if task_complex:
        return "decomposition_quality"
    if tone_type in {"frustrated", "crisis"}:
        return "stability_and_action"
    if tone_type == "dry":
        return "signal_to_noise"
    if "почему" in text or "смысл" in text:
        return "reasoning_depth"
    return "answer_quality"


def _initial_score(
    *,
    intensity: float,
    tone_type: str,
    task_complex: bool,
    workflow: bool,
    conversation: bool,
) -> float:
    score = 0.54 + min(0.26, max(0.0, intensity) * 0.25)
    if tone_type in {"frustrated", "crisis"}:
        score -= 0.06
    if task_complex:
        score -= 0.03
    if workflow:
        score -= 0.02
    if conversation:
        score -= 0.01
    return max(0.35, min(0.92, score))


def _critique_text(focus: str, *, iteration: int, tone_type: str, trend: str) -> str:
    if focus == "orchestration_clarity":
        return "Graph path must stay explicit: nodes, transitions, and stop condition."
    if focus == "dialog_quality":
        return "Conversation should move forward with clear next step, not loop on abstractions."
    if focus == "decomposition_quality":
        return "Parallel/workflow branches need sharper boundaries and output contracts."
    if focus == "stability_and_action":
        return "Keep empathy short and convert quickly into controlled action."
    if focus == "signal_to_noise":
        return "Trim boilerplate and keep a compact, structured answer."
    if tone_type == "reflective" or trend == "rising":
        return "Reasoning must be coherent and grounded in user context."
    return f"Iteration {iteration}: keep response practical and context-aware."


def _adjustment_text(focus: str, *, conversation: bool, workflow: bool) -> str:
    if workflow:
        return "Add explicit workflow summary with stage outputs."
    if conversation:
        return "Add concise dialog summary and one concrete follow-up question."
    if focus == "decomposition_quality":
        return "Separate plan into planner/builder/challenger perspectives."
    if focus == "signal_to_noise":
        return "Start from direct answer, then add only essential details."
    return "Anchor response around action-first structure."


def run(
    history: list[dict[str, Any]] | None,
    *,
    user_message: str,
    tone_analysis: dict[str, Any] | None = None,
    max_rounds: int = 2,
) -> dict[str, Any]:
    tone_analysis = tone_analysis if isinstance(tone_analysis, dict) else {}
    signals = tone_analysis.get("signals") if isinstance(tone_analysis.get("signals"), dict) else {}
    recall = tone_analysis.get("recall") if isinstance(tone_analysis.get("recall"), dict) else {}

    tone_type = str(tone_analysis.get("type") or "neutral")
    intensity = float(tone_analysis.get("intensity") or 0.0)
    task_complex = bool(tone_analysis.get("task_complex"))
    workflow = bool(tone_analysis.get("workflow"))
    conversation = bool(tone_analysis.get("conversation"))
    trend = str(recall.get("trend") or "steady")

    focus = _focus_area(
        user_message,
        tone_type=tone_type,
        task_complex=task_complex,
        workflow=workflow,
        conversation=conversation,
    )
    score = _initial_score(
        intensity=intensity,
        tone_type=tone_type,
        task_complex=task_complex,
        workflow=workflow,
        conversation=conversation,
    )

    rounds = max(1, min(int(max_rounds), 4))
    steps: list[ReflectionStep] = []
    for index in range(1, rounds + 1):
        critique = _critique_text(focus, iteration=index, tone_type=tone_type, trend=trend)
        adjustment = _adjustment_text(focus, conversation=conversation, workflow=workflow)

        gain = 0.05
        gain += 0.02 if int(signals.get("question", 0)) > 0 else 0.0
        gain += 0.02 if task_complex or workflow else 0.0
        gain += 0.01 if conversation else 0.0
        score = min(0.98, score + gain)

        steps.append(
            ReflectionStep(
                iteration=index,
                critique=critique,
                adjustment=adjustment,
                score=round(score, 3),
            )
        )

    if score >= 0.84:
        mode_boost = "high"
    elif score >= 0.70:
        mode_boost = "medium"
    else:
        mode_boost = "low"

    history_tail = _history_tail(history, limit=3)
    final_reflection = (
        f"focus={focus}; boost={mode_boost}; "
        f"history_context={len(history_tail)}; "
        f"last_adjustment={steps[-1].adjustment if steps else 'none'}"
    )

    return {
        "updated": True,
        "focus": focus,
        "mode_boost": mode_boost,
        "confidence": round(score, 3),
        "steps": [
            {
                "iteration": item.iteration,
                "critique": item.critique,
                "adjustment": item.adjustment,
                "score": item.score,
            }
            for item in steps
        ],
        "summary": final_reflection,
        "final_reflection": final_reflection,
    }


__all__ = ["ReflectionStep", "run"]
