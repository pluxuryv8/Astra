from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

"""
Lightweight local adaptation inspired by Agentic Context Engine:
- tmp/agentic/ace/adaptation.py
- tmp/agentic/ace/async_learning.py
- tmp/agentic/ace/updates.py

Implements a minimal feedback loop for self-improvement based on mode history.
No external dependencies are required.
"""

_SELF_IMPROVE_TOKENS = (
    "self_improve",
    "self improve",
    "self-improve",
    "улучши себя",
    "самоулучш",
    "feedback loop",
    "адаптир",
    "learn from history",
)


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower().replace("ё", "е"))


def _history_user_tail(history: list[dict[str, Any]] | None, limit: int = 5) -> list[str]:
    if not isinstance(history, list):
        return []
    tail: list[str] = []
    for item in history[-12:]:
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "").lower() != "user":
            continue
        content = item.get("content")
        if isinstance(content, str) and content.strip():
            tail.append(content.strip())
    return tail[-limit:]


def is_self_improve_task(
    user_message: str,
    *,
    tone_analysis: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> bool:
    text = _normalized(user_message)
    if not text:
        return False

    token_hits = sum(1 for token in _SELF_IMPROVE_TOKENS if token in text)
    signals = tone_analysis.get("signals") if isinstance(tone_analysis, dict) else {}
    memory_callback = int(signals.get("memory_callback", 0)) if isinstance(signals, dict) else 0
    reflective = int(signals.get("reflective_cues", 0)) if isinstance(signals, dict) else 0
    question = int(signals.get("question", 0)) if isinstance(signals, dict) else 0
    mode_history = tone_analysis.get("mode_history") if isinstance(tone_analysis, dict) else []

    score = 0
    score += 3 if token_hits >= 1 else 0
    score += 1 if token_hits >= 2 else 0
    score += 1 if memory_callback >= 1 else 0
    score += 1 if reflective >= 1 else 0
    score += 1 if question >= 1 and ("как" in text or "почему" in text) else 0
    score += 1 if isinstance(mode_history, list) and len(mode_history) >= 3 else 0
    if history and len(_history_user_tail(history, limit=6)) >= 4:
        score += 1
    return score >= 3


@dataclass(slots=True)
class FeedbackSample:
    label: str
    confidence: float
    evidence: str


def _dominant(values: list[str]) -> str | None:
    if not values:
        return None
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _extract_mode_history(
    mode_history: list[Any] | None,
    *,
    max_items: int = 8,
) -> list[str]:
    if not isinstance(mode_history, list):
        return []
    clean = [str(item).strip() for item in mode_history if isinstance(item, str) and str(item).strip()]
    return clean[-max_items:]


def _feedback_samples(
    *,
    mode_history: list[str],
    primary_mode: str,
    supporting_mode: str,
    response_shape: str,
    trend: str,
) -> list[FeedbackSample]:
    samples: list[FeedbackSample] = []
    dominant = _dominant(mode_history)
    if dominant:
        samples.append(
            FeedbackSample(
                label="persona.mode.dominant",
                confidence=0.72,
                evidence=f"dominant_mode={dominant}",
            )
        )
    if primary_mode:
        samples.append(
            FeedbackSample(
                label="persona.mode.primary",
                confidence=0.74,
                evidence=f"primary_mode={primary_mode}",
            )
        )
    if supporting_mode:
        samples.append(
            FeedbackSample(
                label="persona.mode.supporting",
                confidence=0.70,
                evidence=f"supporting_mode={supporting_mode}",
            )
        )
    if response_shape:
        samples.append(
            FeedbackSample(
                label="style.response_shape",
                confidence=0.68,
                evidence=f"shape={response_shape}",
            )
        )
    if trend:
        samples.append(
            FeedbackSample(
                label="conversation.trend",
                confidence=0.66,
                evidence=f"trend={trend}",
            )
        )
    return samples


def run(
    user_message: str,
    *,
    tone_analysis: dict[str, Any] | None = None,
    mode_history: list[str] | None = None,
    history: list[dict[str, Any]] | None = None,
    existing_pairs: set[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    tone_analysis = tone_analysis if isinstance(tone_analysis, dict) else {}
    existing_pairs = existing_pairs if isinstance(existing_pairs, set) else set()
    history = history if isinstance(history, list) else []

    extracted_mode_history = _extract_mode_history(
        mode_history if isinstance(mode_history, list) else tone_analysis.get("mode_history"),
    )
    primary_mode = str(tone_analysis.get("primary_mode") or "").strip()
    supporting_mode = str(tone_analysis.get("supporting_mode") or "").strip()
    response_shape = str(tone_analysis.get("response_shape") or "").strip()
    recall = tone_analysis.get("recall") if isinstance(tone_analysis.get("recall"), dict) else {}
    trend = str(recall.get("trend") or "steady")

    self_improve = bool(tone_analysis.get("self_improve")) or is_self_improve_task(
        user_message,
        tone_analysis=tone_analysis,
        history=history,
    )
    if not self_improve:
        return {
            "self_improve": False,
            "updated": False,
            "preferences": [],
            "summary": "Agentic context improve not engaged.",
            "history_digest": "empty",
        }

    samples = _feedback_samples(
        mode_history=extracted_mode_history,
        primary_mode=primary_mode,
        supporting_mode=supporting_mode,
        response_shape=response_shape,
        trend=trend,
    )

    preferences: list[dict[str, Any]] = []
    for sample in samples:
        key = sample.label
        if key.startswith("persona.mode"):
            value = sample.evidence.split("=")[-1].strip()
        elif key == "style.response_shape":
            value = response_shape or "balanced_direct"
        elif key == "conversation.trend":
            value = trend
        else:
            continue

        pair = (key.lower(), value.lower())
        if pair in existing_pairs:
            continue

        preferences.append(
            {
                "key": key,
                "value": value,
                "confidence": round(max(0.55, min(0.95, sample.confidence)), 2),
                "evidence": sample.evidence,
            }
        )

    digest = " > ".join(extracted_mode_history[-4:]) if extracted_mode_history else "none"
    summary = (
        f"Agentic self-improve updated using mode_history={digest}; "
        f"new_preferences={len(preferences)}."
    )
    return {
        "self_improve": True,
        "updated": bool(preferences),
        "preferences": preferences,
        "summary": summary,
        "history_digest": digest,
        "sample_count": len(samples),
    }


__all__ = ["FeedbackSample", "is_self_improve_task", "run"]
