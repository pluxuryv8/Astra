from __future__ import annotations

import json
import logging
import os
import re
from copy import deepcopy
from pathlib import Path
from time import perf_counter
from typing import Any

from core import agent_reflection, agentic_improve
from core.chat_context import build_user_profile_context
from core.graph_workflow import graph_workflow, is_workflow_task
from memory import letta_bridge
from skills import metagpt_dev, phidata_tools, superagi_autonomy
from skills.autogen_chat import autogen_chat, is_conversation_task
from skills.crew_multi_think import crew_think, is_complex_task

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
_PROMPT_FILES = {
    "core_identity": "core_identity.md",
    "tone_pipeline": "tone_pipeline.md",
    "variation_rules": "variation_rules.md",
}
_PROMPT_CACHE: dict[str, tuple[int, str]] = {}
_LOG = logging.getLogger(__name__)

_MODE_CATALOG: tuple[str, ...] = (
    "Supportive/Empathetic",
    "Enthusiastic/Motivational",
    "Calm/Analytical",
    "Reflective/Wise",
    "Playful-lite",
    "Curious/Inquisitive",
    "Nurturing/Caring",
    "Practical/Solution",
    "Witty/Humorous-lite",
    "Introspective/Thoughtful",
    "Adventurous/Creative",
    "Loyal/Reliable",
    "Insightful/Perceptive",
    "Gentle/Soothing",
    "Bold/Decisive",
    "Humble/Learning",
    "Optimistic/Hopeful",
    "Empowered/Mentoring",
    "Playful-Deep",
    "Resilient/Steady",
    "Strategic/Architect",
    "Precision/Verifier",
    "Creative-Deep",
    "Steady",
)
_MODE_ALIAS: dict[str, str] = {re.sub(r"[^a-z0-9]+", "", item.lower()): item for item in _MODE_CATALOG}

_TONE_MODE_MAP: dict[str, tuple[str, str]] = {
    "dry": ("Calm/Analytical", "Practical/Solution"),
    "frustrated": ("Supportive/Empathetic", "Resilient/Steady"),
    "tired": ("Nurturing/Caring", "Gentle/Soothing"),
    "energetic": ("Enthusiastic/Motivational", "Bold/Decisive"),
    "uncertain": ("Curious/Inquisitive", "Humble/Learning"),
    "reflective": ("Reflective/Wise", "Insightful/Perceptive"),
    "creative": ("Adventurous/Creative", "Creative-Deep"),
    "crisis": ("Resilient/Steady", "Loyal/Reliable"),
    "neutral": ("Loyal/Reliable", "Practical/Solution"),
}

_PROFANITY_TOKENS = (
    "бля",
    "блять",
    "еб",
    "нах",
    "заеб",
    "хер",
    "пизд",
    "fuck",
    "shit",
)
_FATIGUE_TOKENS = (
    "устал",
    "устала",
    "выгорел",
    "выгорание",
    "не вывожу",
    "нет сил",
    "замотан",
    "измотан",
)
_STRESS_TOKENS = (
    "бесит",
    "достал",
    "задолбал",
    "горит",
    "горю",
    "заебал",
    "не могу",
    "сломалось",
)
_DRY_TOKENS = (
    "дай",
    "формула",
    "формулу",
    "кратко",
    "коротко",
    "без воды",
    "шаги",
    "пункты",
    "определение",
    "definition",
    "just",
)
_TECH_TOKENS = (
    "код",
    "python",
    "js",
    "javascript",
    "typescript",
    "sql",
    "covariance",
    "ковариац",
    "regex",
    "api",
    "формул",
)
_URGENCY_TOKENS = ("срочно", "быстро", "прямо сейчас", "urgent", "asap")
_UNCERTAINTY_TOKENS = ("не знаю", "не понял", "что делать", "как быть", "сомневаюсь")
_REFLECTIVE_TOKENS = ("почему", "смысл", "осознаю", "рефлек", "вспоминая", "как вчера")
_CREATIVE_TOKENS = ("придумай", "идея", "что если", "brainstorm", "креатив")
_HUMOR_TOKENS = ("ахах", "лол", "шут", "ирони", "подколи")
_GRATITUDE_TOKENS = ("спасибо", "благодар", "круто", "класс", "ура", "nice", "great")
_TRUST_TOKENS = ("помоги", "выручи", "рассчитываю", "я с тобой", "держи меня")
_CRISIS_TOKENS = ("пиздец", "паника", "катастроф", "всё пропало", "аврал")
_POSITIVE_ENERGY_TOKENS = ("погнали", "давай", "огонь", "вперёд", "разъеб")
_WORKFLOW_TOKENS = ("workflow", "воркфло", "граф", "pipeline", "пайплайн", "оркестрац", "stateful")
_CONVERSATION_TOKENS = ("поговор", "диалог", "обсуд", "chat", "conversation", "brainstorm")
_AUTONOMY_TOKENS = ("autonomy", "автоном", "self-task", "scheduler", "без моего участия")
_DEV_TASK_TOKENS = ("dev_task", "напиши модуль", "реализ", "feature", "код", "module", "тест")
_SELF_IMPROVE_TOKENS = (
    "self_improve",
    "self improve",
    "self-improve",
    "самоулучш",
    "feedback loop",
    "адаптир",
    "улучши себя",
)

_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_+-]+")


def _read_prompt_file(filename: str) -> str:
    path = _PROMPTS_DIR / filename
    stat = path.stat()
    cached = _PROMPT_CACHE.get(filename)
    if cached and cached[0] == stat.st_mtime_ns:
        return cached[1]
    text = path.read_text(encoding="utf-8").strip()
    _PROMPT_CACHE[filename] = (stat.st_mtime_ns, text)
    return text


def load_persona_modules() -> dict[str, str]:
    return {name: _read_prompt_file(filename) for name, filename in _PROMPT_FILES.items()}


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower().replace("ё", "е"))


def _words(value: str) -> list[str]:
    return _WORD_RE.findall(value or "")


def _count_token_hits(text: str, tokens: tuple[str, ...]) -> int:
    lowered = _normalized_text(text)
    if not lowered:
        return 0
    return sum(1 for token in tokens if token in lowered)


def _signal_counts(text: str) -> dict[str, int]:
    words = _words(text)
    exclamation = text.count("!")
    question = text.count("?")
    uppercase = sum(1 for token in words if token.isupper() and len(token) > 2)
    ellipsis = text.count("...") + text.count("…")

    fatigue = _count_token_hits(text, _FATIGUE_TOKENS)
    stress = _count_token_hits(text, _STRESS_TOKENS)
    dry_task = _count_token_hits(text, _DRY_TOKENS)
    technical = _count_token_hits(text, _TECH_TOKENS)
    energetic = _count_token_hits(text, _POSITIVE_ENERGY_TOKENS)
    workflow_cues = _count_token_hits(text, _WORKFLOW_TOKENS)
    conversation_cues = _count_token_hits(text, _CONVERSATION_TOKENS)
    autonomy_cues = _count_token_hits(text, _AUTONOMY_TOKENS)
    dev_task_cues = _count_token_hits(text, _DEV_TASK_TOKENS)
    self_improve_cues = _count_token_hits(text, _SELF_IMPROVE_TOKENS)

    signals = {
        "word_count": len(words),
        "profanity": _count_token_hits(text, _PROFANITY_TOKENS),
        "fatigue": fatigue,
        "stress": stress,
        "dry_task": dry_task,
        "technical_density": technical,
        "urgency": _count_token_hits(text, _URGENCY_TOKENS),
        "uncertainty": _count_token_hits(text, _UNCERTAINTY_TOKENS),
        "reflective_cues": _count_token_hits(text, _REFLECTIVE_TOKENS),
        "creative_cues": _count_token_hits(text, _CREATIVE_TOKENS),
        "humor_cues": _count_token_hits(text, _HUMOR_TOKENS),
        "gratitude": _count_token_hits(text, _GRATITUDE_TOKENS),
        "trust_language": _count_token_hits(text, _TRUST_TOKENS),
        "crisis_cues": _count_token_hits(text, _CRISIS_TOKENS),
        "workflow_cues": workflow_cues,
        "conversation_cues": conversation_cues,
        "autonomy_cues": autonomy_cues,
        "dev_task_cues": dev_task_cues,
        "self_improve_cues": self_improve_cues,
        "positive_energy": energetic,
        "energetic_markers": energetic + exclamation + uppercase,
        "brevity_request": 1 if ("кратко" in _normalized_text(text) or "коротко" in _normalized_text(text) or "без воды" in _normalized_text(text)) else 0,
        "depth_request": 1 if ("подроб" in _normalized_text(text) or "глуб" in _normalized_text(text)) else 0,
        "memory_callback": 1 if ("помнишь" in _normalized_text(text) or "как вчера" in _normalized_text(text)) else 0,
        "ambiguity": 1 if len(words) <= 3 and question > 0 else 0,
        "question": question,
        "exclamation": exclamation,
        "uppercase": uppercase,
        "ellipsis": ellipsis,
        "negative": fatigue + stress,
        "dry": dry_task,
        "tech": technical,
        "positive": energetic + _count_token_hits(text, _GRATITUDE_TOKENS),
    }
    return signals


def _clamp_intensity(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)


def _classify_tone_type(text: str) -> tuple[str, float, dict[str, int]]:
    signals = _signal_counts(text)
    profanity = signals["profanity"]
    fatigue = signals["fatigue"]
    stress = signals["stress"]
    dry_task = signals["dry_task"]
    technical = signals["technical_density"]
    energetic_markers = signals["energetic_markers"]
    uncertainty = signals["uncertainty"]
    reflective = signals["reflective_cues"]
    creative = signals["creative_cues"]
    crisis = signals["crisis_cues"]
    urgency = signals["urgency"]
    word_count = max(1, signals["word_count"])

    if crisis > 0 and (stress > 0 or profanity > 0):
        intensity = 0.74 + crisis * 0.1 + profanity * 0.08 + urgency * 0.05
        return "crisis", _clamp_intensity(intensity), signals

    if profanity > 0 or stress >= 2:
        intensity = 0.62 + profanity * 0.12 + stress * 0.09 + signals["exclamation"] * 0.03
        return "frustrated", _clamp_intensity(intensity), signals

    if fatigue > 0 and stress > 0:
        intensity = 0.58 + fatigue * 0.08 + stress * 0.06 + signals["ellipsis"] * 0.03
        return "tired", _clamp_intensity(intensity), signals

    dry_density = (dry_task + technical + signals["brevity_request"]) / max(1, word_count)
    if (
        ((dry_task + technical) >= 2 or (signals["brevity_request"] > 0 and word_count <= 12))
        and signals["exclamation"] == 0
        and signals["humor_cues"] == 0
    ):
        intensity = 0.5 + dry_density * 2.2
        return "dry", _clamp_intensity(intensity), signals

    if energetic_markers >= 3 or signals["positive_energy"] >= 1:
        intensity = 0.5 + signals["positive_energy"] * 0.12 + signals["exclamation"] * 0.05 + signals["uppercase"] * 0.03
        return "energetic", _clamp_intensity(intensity), signals

    if uncertainty > 0 and reflective == 0:
        intensity = 0.46 + uncertainty * 0.1 + signals["question"] * 0.03
        return "uncertain", _clamp_intensity(intensity), signals

    if creative > 0:
        intensity = 0.45 + creative * 0.1 + signals["positive_energy"] * 0.04
        return "creative", _clamp_intensity(intensity), signals

    if reflective > 0:
        intensity = 0.44 + reflective * 0.08 + signals["question"] * 0.03
        return "reflective", _clamp_intensity(intensity), signals

    if fatigue > 0:
        intensity = 0.45 + fatigue * 0.08
        return "tired", _clamp_intensity(intensity), signals

    return "neutral", 0.34, signals


def _history_user_texts(history: list[dict] | None, *, limit: int = 8) -> list[str]:
    if not isinstance(history, list):
        return []
    user_messages: list[str] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        if item.get("role") != "user":
            continue
        content = item.get("content")
        if isinstance(content, str) and content.strip():
            user_messages.append(content.strip())
    if len(user_messages) > limit:
        return user_messages[-limit:]
    return user_messages


def _dominant_label(values: list[str]) -> str | None:
    if not values:
        return None
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _mirror_level(tone_type: str, intensity: float) -> str:
    if tone_type == "dry":
        return "low"
    if tone_type in {"frustrated", "crisis", "energetic"} and intensity >= 0.65:
        return "high"
    if tone_type in {"tired", "uncertain", "reflective"}:
        return "medium"
    return "medium"


def _response_shape(tone_type: str, signals: dict[str, int]) -> str:
    if tone_type == "dry":
        return "short_structured"
    if tone_type in {"frustrated", "tired"}:
        return "warm_actionable"
    if tone_type == "energetic":
        return "high_energy_steps"
    if tone_type == "reflective":
        return "deep_reflective"
    if tone_type == "crisis":
        return "stabilize_then_plan"
    if signals.get("depth_request", 0) > 0:
        return "deep_reflective"
    return "balanced_direct"


def _is_simple_query_fast_path(
    text: str,
    *,
    tone_type: str,
    signals: dict[str, int],
    task_complex: bool,
    workflow: bool,
    conversation: bool,
    autonomy: bool,
    dev_task: bool,
    self_improve: bool,
) -> tuple[bool, str]:
    normalized = (text or "").strip()
    lowered = _normalized_text(normalized)
    emotional_blockers = (
        "не работает",
        "ничего не работает",
        "не вывожу",
        "нет сил",
        "устал",
        "устала",
        "выгорел",
        "выгорание",
        "сломалось",
    )
    if not normalized:
        return False, "empty"
    if tone_type in {"frustrated", "crisis", "tired"}:
        return False, "emotional_tone"
    if int(signals.get("fatigue", 0)) > 0:
        return False, "fatigue"
    if any(token in lowered for token in emotional_blockers):
        return False, "emotional_keyword"
    if task_complex or workflow or conversation or autonomy or dev_task or self_improve:
        return False, "advanced_route"
    if len(normalized) > 50:
        return False, "length"
    if int(signals.get("word_count", 0)) > 10:
        return False, "word_count"
    if int(signals.get("profanity", 0)) > 0 or int(signals.get("stress", 0)) > 0:
        return False, "stress_or_profanity"
    if int(signals.get("urgency", 0)) > 0 or int(signals.get("crisis_cues", 0)) > 0:
        return False, "urgency_or_crisis"
    if any(token in lowered for token in ("напомни", "помни", "вспомни", "remember")):
        return False, "memory_recall"
    if int(signals.get("question", 0)) > 1:
        return False, "multi_question"
    if int(signals.get("reflective_cues", 0)) > 0 or int(signals.get("creative_cues", 0)) > 0:
        return False, "deep_dialog"
    return True, "short_dry_simple"


def _normalize_mode_label(value: str) -> str | None:
    raw = re.sub(r"[^a-z0-9]+", "", (value or "").lower())
    if not raw:
        return None
    return _MODE_ALIAS.get(raw)


def _extract_modes_from_string(value: str) -> list[str]:
    if not isinstance(value, str):
        return []
    # Mode labels themselves contain "/", so do not split by slash.
    parts = re.split(r"[,;>|]+", value)
    detected: list[str] = []
    for part in parts:
        mode = _normalize_mode_label(part)
        if mode and mode not in detected:
            detected.append(mode)
    return detected


def _memory_preferences(memories: list[dict]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in memories:
        if not isinstance(item, dict):
            continue
        meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
        preferences = meta.get("preferences") if isinstance(meta.get("preferences"), list) else []
        for pref in preferences:
            if isinstance(pref, dict):
                result.append(pref)
    return result


def retrieve_modes(history: list[dict], memories: list[dict] | None = None) -> dict[str, Any]:
    profile_memories = memories if isinstance(memories, list) else []
    from_memory: list[str] = []

    for pref in _memory_preferences(profile_memories):
        key = pref.get("key")
        value = pref.get("value")
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        lowered = key.strip().lower()
        if lowered in {
            "persona.mode.primary",
            "persona.mode.supporting",
            "persona.mode.last",
            "persona.mode.history",
            "style.mode.primary",
            "style.mode.supporting",
        }:
            for mode in _extract_modes_from_string(value):
                from_memory.append(mode)

    inferred_from_history: list[str] = []
    for hist_text in _history_user_texts(history, limit=4):
        hist_type, _hist_intensity, hist_signals = _classify_tone_type(hist_text)
        base_modes = list(_TONE_MODE_MAP.get(hist_type, _TONE_MODE_MAP["neutral"]))
        if hist_signals.get("humor_cues", 0) > 0:
            base_modes.append("Witty/Humorous-lite")
        if base_modes:
            inferred_from_history.append(base_modes[0])

    mode_history = [*from_memory[-6:], *inferred_from_history[-4:]]
    mode_history = mode_history[-8:]
    dominant_mode = _dominant_label(mode_history)

    return {
        "mode_history": mode_history,
        "dominant_mode": dominant_mode,
        "from_memory": from_memory[-6:],
        "inferred_from_history": inferred_from_history,
    }


def _candidate_modes(tone_type: str, signals: dict[str, int]) -> list[str]:
    base = list(_TONE_MODE_MAP.get(tone_type, _TONE_MODE_MAP["neutral"]))
    if signals.get("humor_cues", 0) > 0:
        base.append("Witty/Humorous-lite")
    if signals.get("uncertainty", 0) > 0:
        base.append("Curious/Inquisitive")
    if signals.get("trust_language", 0) > 0:
        base.append("Loyal/Reliable")
    if signals.get("creative_cues", 0) > 0:
        base.append("Adventurous/Creative")
    if signals.get("reflective_cues", 0) > 0:
        base.append("Insightful/Perceptive")
    if signals.get("technical_density", 0) > 1:
        base.append("Precision/Verifier")
    if signals.get("urgency", 0) > 0:
        base.append("Bold/Decisive")

    result: list[str] = []
    for item in base:
        if item not in result:
            result.append(item)
    return result[:6]


def _select_modes(tone_type: str, signals: dict[str, int], recall: dict[str, Any], mode_recall: dict[str, Any]) -> dict[str, Any]:
    candidates = _candidate_modes(tone_type, signals)
    dominant_mode = mode_recall.get("dominant_mode") if isinstance(mode_recall.get("dominant_mode"), str) else None
    if dominant_mode and dominant_mode not in candidates:
        candidates.insert(1, dominant_mode)

    if not candidates:
        candidates = list(_TONE_MODE_MAP["neutral"])

    primary_mode = candidates[0]
    supporting_mode = candidates[1] if len(candidates) > 1 else _TONE_MODE_MAP["neutral"][1]

    if recall.get("detected_shift") and supporting_mode == primary_mode:
        supporting_mode = _TONE_MODE_MAP["neutral"][1]

    return {
        "primary_mode": primary_mode,
        "supporting_mode": supporting_mode,
        "candidate_modes": candidates,
    }


def _self_reflection_text(
    tone_type: str,
    intensity: float,
    recall: dict[str, Any],
    mode_plan: dict[str, Any],
    signals: dict[str, int],
    task_complex: bool = False,
    workflow: bool = False,
    conversation: bool = False,
    autonomy: bool = False,
    dev_task: bool = False,
    self_improve: bool = False,
) -> str:
    shift = "shift detected" if recall.get("detected_shift") else "tone stable"
    urgency = "urgent" if signals.get("urgency", 0) > 0 else "normal pace"
    planning_mode = "parallel" if task_complex else "single"
    workflow_mode = "workflow" if workflow else "no-workflow"
    conversation_mode = "conversation" if conversation else "no-conversation"
    autonomy_mode = "autonomy" if autonomy else "manual"
    dev_mode = "dev" if dev_task else "general"
    improve_mode = "enabled" if self_improve else "disabled"
    return (
        "Self-reflection: "
        f"tone={tone_type} intensity={intensity:.2f}; {shift}; pace={urgency}; "
        f"mode_mix={mode_plan.get('primary_mode')} + {mode_plan.get('supporting_mode')}; "
        f"planning={planning_mode}; orchestration={workflow_mode}; dialog={conversation_mode}; "
        f"autonomy={autonomy_mode}; dev_mode={dev_mode}; self_improve={improve_mode}; "
        "compose answer with full improvisation via self-reflection and no canned opener."
    )


def analyze_tone(user_msg: str, history: list[dict], *, memories: list[dict] | None = None) -> dict[str, Any]:
    text = (user_msg or "").strip()
    tone_type, intensity, signals = _classify_tone_type(text)
    task_complex = is_complex_task(text, tone_analysis={"signals": signals}, history=history)
    workflow = is_workflow_task(text, tone_analysis={"signals": signals, "task_complex": task_complex}, history=history)
    conversation = is_conversation_task(
        text,
        tone_analysis={"signals": signals, "task_complex": task_complex, "workflow": workflow},
        history=history,
    )
    autonomy = superagi_autonomy.is_autonomy_task(
        text,
        tone_analysis={
            "signals": signals,
            "task_complex": task_complex,
            "workflow": workflow,
            "conversation": conversation,
        },
        history=history,
    )
    dev_task = metagpt_dev.is_dev_task(
        text,
        tone_analysis={
            "signals": signals,
            "task_complex": task_complex,
            "workflow": workflow,
            "conversation": conversation,
            "autonomy": autonomy,
        },
        history=history,
    )
    self_improve = agentic_improve.is_self_improve_task(
        text,
        tone_analysis={
            "signals": signals,
            "task_complex": task_complex,
            "workflow": workflow,
            "conversation": conversation,
            "autonomy": autonomy,
            "dev_task": dev_task,
        },
        history=history,
    )
    simple_query, fast_path_reason = _is_simple_query_fast_path(
        text,
        tone_type=tone_type,
        signals=signals,
        task_complex=task_complex,
        workflow=workflow,
        conversation=conversation,
        autonomy=autonomy,
        dev_task=dev_task,
        self_improve=self_improve,
    )

    history_types: list[str] = []
    history_intensities: list[float] = []
    for hist_text in _history_user_texts(history):
        hist_type, hist_intensity, _hist_signals = _classify_tone_type(hist_text)
        history_types.append(hist_type)
        history_intensities.append(hist_intensity)

    dominant_recent = _dominant_label(history_types)
    same_type_count = sum(1 for item in history_types if item == tone_type)
    recent_avg_intensity = round(sum(history_intensities) / len(history_intensities), 3) if history_intensities else 0.0
    detected_shift = bool(dominant_recent and dominant_recent != tone_type and intensity >= 0.42)

    trend = "steady"
    if history_intensities:
        if intensity > recent_avg_intensity + 0.14:
            trend = "rising"
        elif intensity < recent_avg_intensity - 0.14:
            trend = "cooling"

    recall = {
        "history_tail_types": history_types,
        "dominant_recent_tone": dominant_recent,
        "detected_shift": detected_shift,
        "same_type_count": same_type_count,
        "recent_avg_intensity": recent_avg_intensity,
        "trend": trend,
        "autonomy_cues": int(signals.get("autonomy_cues", 0)),
        "dev_task_cues": int(signals.get("dev_task_cues", 0)),
        "self_improve_cues": int(signals.get("self_improve_cues", 0)),
        "fast_path_reason": fast_path_reason,
    }
    mode_recall = retrieve_modes(history, memories=memories)
    mode_plan = _select_modes(tone_type, signals, recall, mode_recall)
    response_shape = _response_shape(tone_type, signals)

    if simple_query:
        recall["letta_hits"] = 0
        recall["phidata_hits"] = 0
        recall["praison_confidence"] = 0.0

        analysis = {
            "type": tone_type,
            "intensity": intensity,
            "mirror_level": _mirror_level(tone_type, intensity),
            "signals": signals,
            "recall": recall,
            "primary_mode": mode_plan["primary_mode"],
            "supporting_mode": mode_plan["supporting_mode"],
            "candidate_modes": mode_plan["candidate_modes"],
            "mode_history": mode_recall.get("mode_history", []),
            "response_shape": response_shape,
            "task_complex": task_complex,
            "workflow": workflow,
            "conversation": conversation,
            "autonomy": autonomy,
            "dev_task": dev_task,
            "self_improve": self_improve,
            "path": "fast",
            "simple_query": True,
            "fast_path_reason": fast_path_reason,
            "letta_recall": {
                "query": text,
                "hit_count": 0,
                "blocks": [],
                "summary": "",
            },
            "phidata_context": {
                "query": text,
                "hit_count": 0,
                "hits": [],
                "recommended_tools": [],
                "summary": "Fast path: direct chat without tools RAG.",
            },
            "praison_reflect": {
                "updated": False,
                "focus": "fast_path",
                "mode_boost": "none",
                "confidence": 0.0,
                "steps": [],
                "summary": "Fast path: reflection skipped for latency.",
            },
        }
        analysis["self_reflection"] = _self_reflection_text(
            tone_type,
            intensity,
            recall,
            mode_plan,
            signals,
            task_complex=task_complex,
            workflow=workflow,
            conversation=conversation,
            autonomy=autonomy,
            dev_task=dev_task,
            self_improve=self_improve,
        )
        return analysis

    letta_recall = letta_bridge.retrieve(history, query=text)
    recall["letta_hits"] = int(letta_recall.get("hit_count") or 0)
    phidata_context = phidata_tools.rag(history, query=text)
    recall["phidata_hits"] = int(phidata_context.get("hit_count") or 0)
    praison_reflect = agent_reflection.run(
        history,
        user_message=text,
        tone_analysis={
            "type": tone_type,
            "intensity": intensity,
            "signals": signals,
            "recall": recall,
            "task_complex": task_complex,
            "workflow": workflow,
            "conversation": conversation,
            "autonomy": autonomy,
            "dev_task": dev_task,
            "self_improve": self_improve,
        },
    )
    recall["praison_confidence"] = float(praison_reflect.get("confidence") or 0.0)

    analysis = {
        "type": tone_type,
        "intensity": intensity,
        "mirror_level": _mirror_level(tone_type, intensity),
        "signals": signals,
        "recall": recall,
        "primary_mode": mode_plan["primary_mode"],
        "supporting_mode": mode_plan["supporting_mode"],
        "candidate_modes": mode_plan["candidate_modes"],
        "mode_history": mode_recall.get("mode_history", []),
        "response_shape": response_shape,
        "task_complex": task_complex,
        "workflow": workflow,
        "conversation": conversation,
        "autonomy": autonomy,
        "dev_task": dev_task,
        "self_improve": self_improve,
        "path": "full",
        "simple_query": False,
        "fast_path_reason": fast_path_reason,
        "letta_recall": letta_recall,
        "phidata_context": phidata_context,
        "praison_reflect": praison_reflect,
    }
    analysis["self_reflection"] = _self_reflection_text(
        tone_type,
        intensity,
        recall,
        mode_plan,
        signals,
        task_complex=task_complex,
        workflow=workflow,
        conversation=conversation,
        autonomy=autonomy,
        dev_task=dev_task,
        self_improve=self_improve,
    )
    return analysis


def _tone_runtime_directives(tone_analysis: dict[str, Any]) -> list[str]:
    tone_type = str(tone_analysis.get("type") or "neutral")
    mirror_level = str(tone_analysis.get("mirror_level") or "medium")
    intensity = float(tone_analysis.get("intensity") or 0.0)
    primary_mode = str(tone_analysis.get("primary_mode") or _TONE_MODE_MAP["neutral"][0])
    supporting_mode = str(tone_analysis.get("supporting_mode") or _TONE_MODE_MAP["neutral"][1])
    response_shape = str(tone_analysis.get("response_shape") or "balanced_direct")

    directives = [
        "Режим: живой инженерный ассистент без канцелярита и без автозаготовок.",
        "Запрещены стартовые шаблоны и бот-мета формулировки.",
        f"Mode mesh сейчас: primary={primary_mode}, supporting={supporting_mode}.",
        f"Форма ответа: {response_shape}.",
        "Применяй full improvisation via self-reflection перед отправкой.",
    ]
    if tone_analysis.get("task_complex"):
        directives.append("If complex_task, use CrewAI-style parallel thinking before final answer.")
    if tone_analysis.get("workflow"):
        directives.append("If workflow, use LangGraph-style stateful workflow before final answer.")
    if tone_analysis.get("conversation"):
        directives.append("If conversation, use AutoGen-style multi-agent conversation before final answer.")
    if tone_analysis.get("autonomy"):
        directives.append("If autonomy, use SuperAGI-style scheduler and self-task loop before final answer.")
    if tone_analysis.get("dev_task"):
        directives.append("If dev_task, use MetaGPT-style PRD->Code->Review->Test flow before final answer.")
    if tone_analysis.get("self_improve"):
        directives.append("If self_improve, run Agentic Context feedback loop before final answer.")
    praison = tone_analysis.get("praison_reflect") if isinstance(tone_analysis.get("praison_reflect"), dict) else {}
    if praison.get("mode_boost"):
        directives.append(f"Praison reflection boost: {praison.get('mode_boost')}.")
    phidata_ctx = tone_analysis.get("phidata_context") if isinstance(tone_analysis.get("phidata_context"), dict) else {}
    recommended = phidata_ctx.get("recommended_tools") if isinstance(phidata_ctx.get("recommended_tools"), list) else []
    if recommended:
        directives.append(f"Phidata RAG tools hint: {', '.join(str(item) for item in recommended[:4])}.")

    if tone_type == "dry":
        directives.extend(
            [
                "Сначала суть/формула, потом короткие шаги.",
                "Минимум эмоциональных вставок.",
            ]
        )
    elif tone_type in {"frustrated", "crisis"}:
        directives.extend(
            [
                "Коротко валидируй состояние и сразу веди к действию.",
                "Не копируй токсичность дословно; удерживай контрольный полезный тон.",
            ]
        )
    elif tone_type == "tired":
        directives.extend(
            [
                "Спокойный темп и мягкая плотная подача.",
                "Не перегружай длинными списками.",
            ]
        )
    elif tone_type == "energetic":
        directives.extend(
            [
                "Держи быстрый ритм и конкретику.",
                "Используй энергичный, но дисциплинированный тон.",
            ]
        )
    elif tone_type == "reflective":
        directives.append("Добавь смысловую глубину и аккуратные выводы без морализаторства.")
    elif tone_type == "creative":
        directives.append("Разрешены нестандартные идеи при сохранении прикладной пользы.")

    if mirror_level == "low":
        directives.append("Зеркалинг low: акцент на ясность и точность.")
    elif mirror_level == "high":
        directives.append("Зеркалинг high: ритм и энергия синхронизированы с пользователем.")
    else:
        directives.append("Зеркалинг medium: баланс формальности и человечности.")

    if tone_analysis.get("recall", {}).get("detected_shift"):
        directives.append("Обязательно добавь мягкий transition между состояниями диалога.")

    if intensity >= 0.85:
        directives.append("Сократи разгон: максимум одна вводная фраза до полезной части.")

    directives.append(
        "Локальный приватный режим: максимальная практическая полезность без пустых отказных клише, но без обхода защит и без вредоносных инструкций."
    )
    return directives


def apply_variation(prompt: str, tone_dict: dict[str, Any]) -> str:
    tone_type = str(tone_dict.get("type") or "neutral")
    primary_mode = str(tone_dict.get("primary_mode") or "Loyal/Reliable")
    supporting_mode = str(tone_dict.get("supporting_mode") or "Practical/Solution")
    response_shape = str(tone_dict.get("response_shape") or "balanced_direct")
    mirror_level = str(tone_dict.get("mirror_level") or "medium")

    variation_lines = [
        "Принцип генерации: full improvisation via self-reflection.",
        f"Tone={tone_type}; mirror_level={mirror_level}; response_shape={response_shape}.",
        f"Mode mix в ответе: {primary_mode} + {supporting_mode}.",
        "Варьируй opening/cadence/lexicon и не повторяй соседний ритм ответа.",
        "Если не уникально звучит, переформулируй до прохождения improvisation-check.",
        "Не копируй буквально примеры и не используй canned transitions.",
    ]

    if tone_dict.get("recall", {}).get("detected_shift"):
        variation_lines.append("Добавь естественный bridge между прошлым и текущим состоянием пользователя.")
    if tone_type == "dry":
        variation_lines.append("Вариативность сохраняется, но компактность обязательна.")
    elif tone_type in {"frustrated", "tired", "crisis"}:
        variation_lines.append("Сначала человечная опора, затем сразу actionable помощь.")

    variation_block = "[Variation Runtime]\n- " + "\n- ".join(variation_lines)
    return prompt + "\n\n" + variation_block


def _profile_preference_pairs(memories: list[dict]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for pref in _memory_preferences(memories):
        key = pref.get("key")
        value = pref.get("value")
        if isinstance(key, str) and isinstance(value, str):
            pairs.add((key.strip().lower(), value.strip().lower()))
    return pairs


def _tone_preference_candidates(tone_analysis: dict[str, Any]) -> list[dict[str, Any]]:
    tone_type = str(tone_analysis.get("type") or "neutral")
    intensity = float(tone_analysis.get("intensity") or 0.0)
    mirror_level = str(tone_analysis.get("mirror_level") or "medium")
    response_shape = str(tone_analysis.get("response_shape") or "balanced_direct")
    recall = tone_analysis.get("recall") if isinstance(tone_analysis.get("recall"), dict) else {}
    same_type_count = int(recall.get("same_type_count") or 0)
    dominant_recent = recall.get("dominant_recent_tone")
    stable = same_type_count >= 2 or (isinstance(dominant_recent, str) and dominant_recent == tone_type)

    confidence = round(min(0.96, 0.5 + intensity * 0.42), 2)
    if confidence < 0.7 and not stable:
        return []

    candidates: list[dict[str, Any]] = []
    if tone_type == "dry":
        candidates.append(
            {
                "key": "style.brevity",
                "value": "short",
                "confidence": confidence,
                "summary": "Пользователь чаще выбирает короткий структурный формат ответа.",
            }
        )
    elif tone_type in {"frustrated", "crisis"}:
        candidates.append(
            {
                "key": "style.tone",
                "value": "supportive-direct",
                "confidence": confidence,
                "summary": "В стрессовом контексте полезен прямой поддерживающий тон.",
            }
        )
    elif tone_type == "tired":
        candidates.append(
            {
                "key": "style.tone",
                "value": "calm-supportive",
                "confidence": confidence,
                "summary": "Пользователь лучше реагирует на спокойную поддерживающую подачу.",
            }
        )
    elif tone_type == "energetic":
        candidates.append(
            {
                "key": "style.tone",
                "value": "energetic-direct",
                "confidence": confidence,
                "summary": "Пользователь предпочитает энергичную деловую динамику.",
            }
        )

    if mirror_level in {"medium", "high"}:
        candidates.append(
            {
                "key": "style.mirror_level",
                "value": mirror_level,
                "confidence": max(0.7, confidence - 0.04),
                "summary": "Полезен динамический зеркалинг тона под контекст.",
            }
        )

    candidates.append(
        {
            "key": "style.response_shape",
            "value": response_shape,
            "confidence": max(0.68, confidence - 0.08),
            "summary": "Уточнена предпочитаемая форма ответа по динамике диалога.",
        }
    )
    return candidates


def _safe_evidence(user_msg: str, *, limit: int = 220) -> str:
    text = (user_msg or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


def _build_auto_memory_payload(
    user_msg: str,
    *,
    title: str,
    summary: str,
    confidence: float,
    preferences: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not preferences:
        return None
    safe_content = (user_msg or "").strip()
    if not safe_content:
        return None
    return {
        "content": safe_content,
        "origin": "auto",
        "memory_payload": {
            "title": title,
            "summary": summary,
            "confidence": round(max(0.0, min(1.0, confidence)), 2),
            "facts": [],
            "preferences": preferences,
            "possible_facts": [],
        },
    }


def _prepare_preferences(
    user_msg: str,
    candidates: list[dict[str, Any]],
    existing_pairs: set[tuple[str, str]],
) -> tuple[list[dict[str, Any]], list[str]]:
    evidence = _safe_evidence(user_msg)
    if not evidence:
        return [], []

    preferences: list[dict[str, Any]] = []
    summaries: list[str] = []
    for candidate in candidates:
        key = str(candidate.get("key") or "").strip()
        value = str(candidate.get("value") or "").strip()
        if not key or not value:
            continue
        pair = (key.lower(), value.lower())
        if pair in existing_pairs:
            continue
        confidence = float(candidate.get("confidence") or 0.0)
        preferences.append(
            {
                "key": key,
                "value": value,
                "confidence": round(max(0.0, min(1.0, confidence)), 2),
                "evidence": evidence,
            }
        )
        summary = str(candidate.get("summary") or "").strip()
        if summary:
            summaries.append(summary)

    return preferences, summaries


def update_profile_by_mode(
    user_msg: str,
    tone_analysis: dict[str, Any],
    memories: list[dict],
) -> dict[str, Any] | None:
    if not isinstance(tone_analysis, dict):
        return None

    primary_mode = str(tone_analysis.get("primary_mode") or "").strip()
    supporting_mode = str(tone_analysis.get("supporting_mode") or "").strip()
    if not primary_mode:
        return None

    history_modes = tone_analysis.get("mode_history") if isinstance(tone_analysis.get("mode_history"), list) else []
    mode_tail = [item for item in history_modes if isinstance(item, str) and item.strip()][-3:]
    mode_chain = " > ".join(mode_tail + [primary_mode]) if mode_tail else primary_mode

    base_confidence = round(min(0.95, 0.58 + float(tone_analysis.get("intensity") or 0.0) * 0.32), 2)
    candidates = [
        {
            "key": "persona.mode.primary",
            "value": primary_mode,
            "confidence": base_confidence,
            "summary": f"Актуальный основной mode взаимодействия: {primary_mode}.",
        }
    ]
    if supporting_mode:
        candidates.append(
            {
                "key": "persona.mode.supporting",
                "value": supporting_mode,
                "confidence": max(0.68, base_confidence - 0.05),
                "summary": f"Актуальный supporting mode: {supporting_mode}.",
            }
        )
    candidates.append(
        {
            "key": "persona.mode.history",
            "value": mode_chain,
            "confidence": max(0.66, base_confidence - 0.08),
            "summary": "Обновлена недавняя траектория mode-mix пользователя.",
        }
    )

    existing_pairs = _profile_preference_pairs(memories)
    agentic_result = agentic_improve.run(
        user_msg,
        tone_analysis=tone_analysis,
        mode_history=history_modes,
        existing_pairs=existing_pairs,
    )
    agentic_preferences = agentic_result.get("preferences") if isinstance(agentic_result, dict) else []
    if isinstance(agentic_preferences, list):
        for pref in agentic_preferences:
            if not isinstance(pref, dict):
                continue
            key = str(pref.get("key") or "").strip()
            value = str(pref.get("value") or "").strip()
            if not key or not value:
                continue
            confidence = float(pref.get("confidence") or base_confidence)
            candidates.append(
                {
                    "key": key,
                    "value": value,
                    "confidence": max(0.62, min(0.96, confidence)),
                    "summary": f"Self-improve feedback: {agentic_result.get('summary') or 'updated by agentic loop'}.",
                }
            )

    preferences, summaries = _prepare_preferences(user_msg, candidates, existing_pairs)
    if not preferences:
        return None

    summary = " ".join(dict.fromkeys(summaries))
    if not summary:
        summary = "Обновлена история режимов общения пользователя."
    agentic_summary = str(agentic_result.get("summary") or "").strip() if isinstance(agentic_result, dict) else ""
    if agentic_summary and agentic_summary not in summary:
        summary = f"{summary} {agentic_summary}".strip()

    return _build_auto_memory_payload(
        user_msg,
        title="Профиль режимов общения",
        summary=summary,
        confidence=max(item["confidence"] for item in preferences),
        preferences=preferences,
    )


def build_tone_profile_memory_payload(
    user_msg: str,
    tone_analysis: dict[str, Any],
    memories: list[dict],
) -> dict[str, Any] | None:
    if not isinstance(tone_analysis, dict):
        return None

    existing_pairs = _profile_preference_pairs(memories)
    tone_candidates = _tone_preference_candidates(tone_analysis)
    tone_preferences, tone_summaries = _prepare_preferences(user_msg, tone_candidates, existing_pairs)

    tone_payload = None
    if tone_preferences:
        tone_summary = " ".join(dict.fromkeys(tone_summaries))
        if not tone_summary:
            tone_summary = "Обновлён профиль предпочтений стиля пользователя."
        tone_payload = _build_auto_memory_payload(
            user_msg,
            title="Профиль стиля пользователя",
            summary=tone_summary,
            confidence=max(item["confidence"] for item in tone_preferences),
            preferences=tone_preferences,
        )

    mode_payload = update_profile_by_mode(user_msg, tone_analysis, memories)
    return merge_memory_payloads(tone_payload, mode_payload)


def _merge_unique_items(left: list[Any], right: list[Any]) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for raw_item in [*left, *right]:
        if not isinstance(raw_item, dict):
            continue
        key = raw_item.get("key")
        value = raw_item.get("value")
        if isinstance(key, str) and isinstance(value, str):
            signature = f"{key.strip().lower()}::{value.strip().lower()}"
        else:
            signature = json.dumps(raw_item, ensure_ascii=False, sort_keys=True)
        if signature in seen:
            continue
        seen.add(signature)
        merged.append(raw_item)
    return merged


def merge_memory_payloads(primary: dict[str, Any] | None, secondary: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(primary, dict) and not isinstance(secondary, dict):
        return None
    if not isinstance(primary, dict):
        return deepcopy(secondary)
    if not isinstance(secondary, dict):
        return deepcopy(primary)

    result = deepcopy(primary)
    left_payload = result.get("memory_payload")
    right_payload = secondary.get("memory_payload")
    if not isinstance(left_payload, dict) or not isinstance(right_payload, dict):
        return result

    left_preferences = left_payload.get("preferences") if isinstance(left_payload.get("preferences"), list) else []
    right_preferences = right_payload.get("preferences") if isinstance(right_payload.get("preferences"), list) else []
    left_payload["preferences"] = _merge_unique_items(left_preferences, right_preferences)

    left_facts = left_payload.get("facts") if isinstance(left_payload.get("facts"), list) else []
    right_facts = right_payload.get("facts") if isinstance(right_payload.get("facts"), list) else []
    left_payload["facts"] = _merge_unique_items(left_facts, right_facts)

    left_possible = left_payload.get("possible_facts") if isinstance(left_payload.get("possible_facts"), list) else []
    right_possible = right_payload.get("possible_facts") if isinstance(right_payload.get("possible_facts"), list) else []
    left_payload["possible_facts"] = _merge_unique_items(left_possible, right_possible)

    left_summary = str(left_payload.get("summary") or "").strip()
    right_summary = str(right_payload.get("summary") or "").strip()
    if left_summary and right_summary and right_summary not in left_summary:
        combined = f"{left_summary} {right_summary}".strip()
        left_payload["summary"] = combined[:320]
    elif right_summary and not left_summary:
        left_payload["summary"] = right_summary[:320]

    left_confidence = float(left_payload.get("confidence") or 0.0)
    right_confidence = float(right_payload.get("confidence") or 0.0)
    left_payload["confidence"] = round(max(left_confidence, right_confidence), 2)

    content = result.get("content")
    if (not isinstance(content, str) or not content.strip()) and isinstance(secondary.get("content"), str):
        result["content"] = secondary.get("content")
    return result


def _parallel_think_prompt_block(parallel_result: dict[str, Any]) -> str:
    if not isinstance(parallel_result, dict):
        return "Parallel mode: off."
    mode = str(parallel_result.get("mode") or "single")
    if mode != "parallel":
        return "Parallel mode: off."
    items = parallel_result.get("items") if isinstance(parallel_result.get("items"), list) else []
    if not items:
        return "Parallel mode: on, but no worker output."
    lines: list[str] = ["Parallel mode: ON (CrewAI-style)."]
    for item in items[:6]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("agent") or "worker")
        output = str(item.get("output") or "").strip()
        if not output:
            continue
        lines.append(f"- {role}: {output[:220]}")
    return "\n".join(lines)


def _workflow_prompt_block(workflow_result: dict[str, Any]) -> str:
    if not isinstance(workflow_result, dict):
        return "Workflow mode: off."
    if str(workflow_result.get("mode") or "single") != "workflow":
        return "Workflow mode: off."
    if not workflow_result.get("executed"):
        return "Workflow mode: requested, but graph not executed."
    state = workflow_result.get("state") if isinstance(workflow_result.get("state"), dict) else {}
    lines = [
        "Workflow mode: ON (LangGraph-style).",
        f"- decompose: {str(state.get('decompose_output') or '')[:220]}",
        f"- implement: {str(state.get('implement_output') or '')[:220]}",
        f"- verify: {str(state.get('verify_output') or '')[:220]}",
    ]
    return "\n".join(lines)


def _autogen_prompt_block(conversation_result: dict[str, Any]) -> str:
    if not isinstance(conversation_result, dict):
        return "Conversation mode: off."
    if str(conversation_result.get("mode") or "single") != "conversation":
        return "Conversation mode: off."
    if not conversation_result.get("executed"):
        return "Conversation mode: requested, but dialog not executed."
    turns = conversation_result.get("turns") if isinstance(conversation_result.get("turns"), list) else []
    if not turns:
        return "Conversation mode: on, no turns captured."
    lines = ["Conversation mode: ON (AutoGen-style)."]
    for item in turns[:6]:
        if not isinstance(item, dict):
            continue
        speaker = str(item.get("speaker") or "agent")
        message = str(item.get("message") or "").strip()
        if not message:
            continue
        lines.append(f"- {speaker}: {message[:220]}")
    return "\n".join(lines)


def _praison_prompt_block(reflection: dict[str, Any]) -> str:
    if not isinstance(reflection, dict):
        return "Praison reflection: unavailable."
    if not reflection.get("updated"):
        return "Praison reflection: not updated."
    summary = str(reflection.get("summary") or "no summary").strip()
    if len(summary) > 320:
        summary = summary[:319].rstrip() + "…"
    lines = [
        f"focus={reflection.get('focus') or 'answer_quality'}",
        f"boost={reflection.get('mode_boost') or 'low'}",
        f"confidence={reflection.get('confidence') or 0.0}",
        summary,
    ]
    return "\n".join(f"- {line}" for line in lines)


def _compact_text_for_prompt(value: Any, *, limit: int = 320) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def _runtime_analysis_prompt_block(analysis: dict[str, Any]) -> str:
    recall = analysis.get("recall") if isinstance(analysis.get("recall"), dict) else {}
    compact = {
        "type": analysis.get("type"),
        "intensity": analysis.get("intensity"),
        "mirror_level": analysis.get("mirror_level"),
        "path": analysis.get("path"),
        "response_shape": analysis.get("response_shape"),
        "primary_mode": analysis.get("primary_mode"),
        "supporting_mode": analysis.get("supporting_mode"),
        "flags": {
            "task_complex": bool(analysis.get("task_complex")),
            "workflow": bool(analysis.get("workflow")),
            "conversation": bool(analysis.get("conversation")),
            "autonomy": bool(analysis.get("autonomy")),
            "dev_task": bool(analysis.get("dev_task")),
            "self_improve": bool(analysis.get("self_improve")),
        },
        "recall": {
            "trend": recall.get("trend"),
            "detected_shift": bool(recall.get("detected_shift")),
            "fast_path_reason": recall.get("fast_path_reason"),
            "letta_hits": int(recall.get("letta_hits") or 0),
            "phidata_hits": int(recall.get("phidata_hits") or 0),
            "praison_confidence": float(recall.get("praison_confidence") or 0.0),
        },
        "self_reflection": _compact_text_for_prompt(analysis.get("self_reflection"), limit=420),
    }
    return json.dumps(compact, ensure_ascii=False, indent=2)


def _prompt_block_limit(env_name: str, default: int) -> int:
    raw = os.getenv(env_name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(300, min(12000, value))


def _compact_multiline_for_prompt(value: Any, *, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    lines: list[str] = []
    consumed = 0
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        chunk = len(line) + 1
        if consumed + chunk > max(1, limit - 2):
            break
        lines.append(line)
        consumed += chunk
    if not lines:
        return text[: max(1, limit - 1)].rstrip() + "…"
    return "\n".join(lines).rstrip() + "\n…"


def _chat_prompt_max_chars() -> int | None:
    raw = os.getenv("ASTRA_CHAT_SYSTEM_PROMPT_MAX_CHARS")
    if raw is None or not raw.strip():
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return max(2000, min(20000, value))


def _superagi_prompt_block(autonomy_result: dict[str, Any]) -> str:
    if not isinstance(autonomy_result, dict):
        return "Autonomy mode: off."
    if str(autonomy_result.get("mode") or "single") != "autonomy":
        return "Autonomy mode: off."
    if not autonomy_result.get("started"):
        return "Autonomy mode: requested, but scheduler not started."
    tasks = autonomy_result.get("tasks") if isinstance(autonomy_result.get("tasks"), list) else []
    lines = ["Autonomy mode: ON (SuperAGI-style)."]
    for item in tasks[:6]:
        if not isinstance(item, dict):
            continue
        instruction = str(item.get("instruction") or "").strip()
        output = str(item.get("output") or "").strip()
        if instruction:
            lines.append(f"- task: {instruction[:180]}")
        if output:
            lines.append(f"  output: {output[:180]}")
    return "\n".join(lines)


def _metagpt_prompt_block(dev_result: dict[str, Any]) -> str:
    if not isinstance(dev_result, dict):
        return "Dev mode: off."
    if str(dev_result.get("mode") or "single") != "dev":
        return "Dev mode: off."
    if not dev_result.get("executed"):
        return "Dev mode: requested, but pipeline not executed."
    return "\n".join(
        [
            "Dev mode: ON (MetaGPT-style).",
            f"- prd: {str(dev_result.get('prd') or '')[:220]}",
            f"- review: {str(dev_result.get('review') or '')[:220]}",
            f"- tests: {str(dev_result.get('tests') or '')[:220]}",
        ]
    )


def _agentic_prompt_block(improve_result: dict[str, Any]) -> str:
    if not isinstance(improve_result, dict):
        return "Self-improve mode: off."
    if not improve_result.get("self_improve"):
        return "Self-improve mode: off."
    if not improve_result.get("updated"):
        return "Self-improve mode: requested, no new preferences."
    preferences = improve_result.get("preferences") if isinstance(improve_result.get("preferences"), list) else []
    lines = ["Self-improve mode: ON (Agentic Context Engine style)."]
    for pref in preferences[:6]:
        if not isinstance(pref, dict):
            continue
        key = str(pref.get("key") or "").strip()
        value = str(pref.get("value") or "").strip()
        confidence = pref.get("confidence")
        if key and value:
            lines.append(f"- {key}={value} (confidence={confidence})")
    return "\n".join(lines)


def system_health_check() -> dict[str, Any]:
    module_status = {
        "crewai_parallel": callable(crew_think),
        "letta_memory": callable(letta_bridge.retrieve) and callable(letta_bridge.update),
        "langgraph_workflow": callable(graph_workflow),
        "phidata_tools": callable(phidata_tools.rag),
        "autogen_conversation": callable(autogen_chat),
        "praison_reflection": callable(agent_reflection.run),
        "superagi_autonomy": callable(superagi_autonomy.run),
        "metagpt_dev": callable(metagpt_dev.run),
        "agentic_improve": callable(agentic_improve.run),
    }
    active = sum(1 for value in module_status.values() if value)
    total = len(module_status)
    return {
        "active_count": active,
        "total_agents": total,
        "all_active": active == total,
        "module_status": module_status,
        "summary": f"Agents: {active}/{total} active",
    }


def build_dynamic_prompt(
    memories: list[dict],
    response_style_hint: str | None,
    *,
    user_message: str,
    history: list[dict],
    owner_direct_mode: bool = True,
    tone_analysis: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    started_at = perf_counter()
    persona = load_persona_modules()
    profile_context = build_user_profile_context(memories)
    profile_block = profile_context.get("profile_block")
    style_hints = profile_context.get("style_hints") if isinstance(profile_context.get("style_hints"), list) else []
    user_name = profile_context.get("user_name") if isinstance(profile_context.get("user_name"), str) else None

    analysis = tone_analysis if isinstance(tone_analysis, dict) else analyze_tone(
        user_message,
        history,
        memories=memories,
    )
    health_report = system_health_check()
    analysis["system_health"] = health_report
    core_identity_block = _compact_multiline_for_prompt(
        persona["core_identity"],
        limit=_prompt_block_limit("ASTRA_CHAT_PROMPT_CORE_IDENTITY_MAX_CHARS", 1100),
    )
    tone_pipeline_block = _compact_multiline_for_prompt(
        persona["tone_pipeline"],
        limit=_prompt_block_limit("ASTRA_CHAT_PROMPT_TONE_PIPELINE_MAX_CHARS", 900),
    )
    variation_rules_block = _compact_multiline_for_prompt(
        persona["variation_rules"],
        limit=_prompt_block_limit("ASTRA_CHAT_PROMPT_VARIATION_RULES_MAX_CHARS", 900),
    )
    if str(analysis.get("path") or "full") == "fast":
        analysis["parallel_think"] = {"mode": "single", "task_complex": False, "items": [], "summary": "Fast path skip."}
        analysis["workflow_graph"] = {
            "mode": "single",
            "workflow": False,
            "executed": False,
            "summary": "Fast path skip.",
            "state": {},
        }
        analysis["autogen_chat"] = {
            "mode": "single",
            "conversation": False,
            "executed": False,
            "turns": [],
            "summary": "Fast path skip.",
        }
        analysis["superagi_autonomy"] = {
            "mode": "single",
            "autonomy": False,
            "started": False,
            "tasks": [],
            "summary": "Fast path skip.",
        }
        analysis["metagpt_dev"] = {
            "mode": "single",
            "dev_task": False,
            "executed": False,
            "generated_code": "",
            "summary": "Fast path skip.",
        }
        analysis["agentic_improve"] = {
            "self_improve": False,
            "updated": False,
            "preferences": [],
            "summary": "Fast path skip.",
        }
        analysis["letta_update"] = {
            "updated": False,
            "digest": "",
            "summary": "Fast path: memory update skipped.",
            "tags": [],
        }
        profile_lines = f"Профиль пользователя:\n{profile_block}" if profile_block else "Профиль пользователя: пусто."
        runtime_lines = [
            "Fast path: ON (simple dry/short query).",
            "Skip mods/reflection/variation for lower latency.",
            "Rule retained: full improvisation via self-reflection.",
            health_report.get("summary") or "Agents: status unavailable.",
        ]
        if user_name:
            runtime_lines.append(f"Имя пользователя: {user_name}.")
        if style_hints:
            runtime_lines.append(f"Стиль из long-term профиля: {' '.join(style_hints[:3])}")
        fast_prompt = "\n\n".join(
            [
                "[Core Identity]\n" + core_identity_block,
                "[Fast Path Runtime]\n- " + "\n- ".join(runtime_lines),
                "[Profile Recall]\n" + profile_lines,
                "[Fast Path Directives]\n"
                "- Direct answer only: no templates, no canned opener.\n"
                "- Maintain full improvisation via self-reflection even in compact mode.\n"
                "- If user tone becomes frustrated/crisis, switch to full path with warm mirror immediately.",
            ]
        )
        elapsed_s = round(perf_counter() - started_at, 4)
        analysis["prompt_build_latency_s"] = elapsed_s
        _LOG.info("latency: %.4f sec", elapsed_s)
        return fast_prompt, analysis
    if analysis.get("task_complex"):
        parallel_result = crew_think(
            user_message,
            history,
            tone_analysis=analysis,
        )
    else:
        parallel_result = {
            "mode": "single",
            "task_complex": False,
            "items": [],
            "summary": "Parallel crew not engaged.",
        }
    analysis["parallel_think"] = parallel_result
    if analysis.get("workflow"):
        workflow_result = graph_workflow(
            user_message,
            history,
            tone_analysis=analysis,
        )
    else:
        workflow_result = {
            "mode": "single",
            "workflow": False,
            "executed": False,
            "summary": "Workflow graph not engaged.",
            "state": {},
        }
    analysis["workflow_graph"] = workflow_result
    if analysis.get("conversation"):
        conversation_result = autogen_chat(
            user_message,
            history,
            tone_analysis=analysis,
        )
    else:
        conversation_result = {
            "mode": "single",
            "conversation": False,
            "executed": False,
            "turns": [],
            "summary": "AutoGen chat not engaged.",
        }
    analysis["autogen_chat"] = conversation_result
    if analysis.get("autonomy"):
        autonomy_result = superagi_autonomy.run(
            user_message,
            history,
            tone_analysis=analysis,
        )
    else:
        autonomy_result = {
            "mode": "single",
            "autonomy": False,
            "started": False,
            "tasks": [],
            "summary": "SuperAGI autonomy not engaged.",
        }
    analysis["superagi_autonomy"] = autonomy_result
    if analysis.get("dev_task"):
        metagpt_result = metagpt_dev.run(
            user_message,
            history,
            tone_analysis=analysis,
        )
    else:
        metagpt_result = {
            "mode": "single",
            "dev_task": False,
            "executed": False,
            "generated_code": "",
            "summary": "MetaGPT dev pipeline not engaged.",
        }
    analysis["metagpt_dev"] = metagpt_result
    if analysis.get("self_improve"):
        agentic_result = agentic_improve.run(
            user_message,
            tone_analysis=analysis,
            mode_history=analysis.get("mode_history") if isinstance(analysis.get("mode_history"), list) else [],
            history=history,
        )
    else:
        agentic_result = {
            "self_improve": False,
            "updated": False,
            "preferences": [],
            "summary": "Agentic context improve not engaged.",
        }
    analysis["agentic_improve"] = agentic_result
    letta_update = letta_bridge.update(
        user_message=user_message,
        history=history,
        tone_analysis=analysis,
        crew_result=parallel_result,
    )
    analysis["letta_update"] = letta_update
    runtime_directives = _tone_runtime_directives(analysis)
    runtime_analysis_json = _runtime_analysis_prompt_block(analysis)

    mode_recall = retrieve_modes(history, memories=memories)
    mode_lines = [
        f"Dominant mode from recall: {mode_recall.get('dominant_mode') or 'none'}.",
        f"Recent mode history: {', '.join(mode_recall.get('mode_history') or []) or 'empty'}.",
    ]

    runtime_lines = [
        "Режим владельца: ON." if owner_direct_mode else "Режим владельца: OFF.",
        f"Self-reflection trace: {analysis.get('self_reflection')}",
    ]
    if isinstance(parallel_result, dict) and parallel_result.get("mode") == "parallel":
        runtime_lines.append(f"Parallel summary: {parallel_result.get('summary') or 'generated'}")
    if isinstance(workflow_result, dict) and workflow_result.get("executed"):
        runtime_lines.append(f"Workflow summary: {workflow_result.get('summary') or 'generated'}")
    if isinstance(conversation_result, dict) and conversation_result.get("executed"):
        runtime_lines.append(f"Conversation summary: {conversation_result.get('summary') or 'generated'}")
    if isinstance(autonomy_result, dict) and autonomy_result.get("started"):
        runtime_lines.append(f"Autonomy summary: {autonomy_result.get('summary') or 'generated'}")
    if isinstance(metagpt_result, dict) and metagpt_result.get("executed"):
        runtime_lines.append(f"MetaGPT summary: {metagpt_result.get('summary') or 'generated'}")
    if isinstance(agentic_result, dict) and agentic_result.get("self_improve"):
        runtime_lines.append(f"Agentic improve: {agentic_result.get('summary') or 'generated'}")
    letta_recall = analysis.get("letta_recall") if isinstance(analysis.get("letta_recall"), dict) else {}
    if letta_recall.get("summary"):
        runtime_lines.append(f"Episodic recall: {_compact_text_for_prompt(letta_recall.get('summary'), limit=360)}")
    phidata_context = analysis.get("phidata_context") if isinstance(analysis.get("phidata_context"), dict) else {}
    if phidata_context.get("summary"):
        runtime_lines.append(f"Phidata context: {_compact_text_for_prompt(phidata_context.get('summary'), limit=320)}")
    praison_reflect = analysis.get("praison_reflect") if isinstance(analysis.get("praison_reflect"), dict) else {}
    if praison_reflect.get("summary"):
        runtime_lines.append(f"Praison reflection: {_compact_text_for_prompt(praison_reflect.get('summary'), limit=320)}")
    runtime_lines.append(health_report.get("summary") or "Agents: status unavailable.")
    if user_name:
        runtime_lines.append(f"Имя пользователя: {user_name}.")
    if response_style_hint:
        runtime_lines.append(f"Явная стилевая подсказка: {_compact_text_for_prompt(response_style_hint, limit=260)}")
    if style_hints:
        runtime_lines.append(f"Стиль из long-term профиля: {' '.join(style_hints[:4])}")

    if profile_block:
        profile_lines = f"Профиль пользователя:\n{profile_block}"
    else:
        profile_lines = "Профиль пользователя: пусто."

    base_prompt = "\n\n".join(
        [
            "[Core Identity]\n" + core_identity_block,
            "[Tone Pipeline]\n" + tone_pipeline_block,
            "[Variation Rules]\n" + variation_rules_block,
            "[Runtime Analysis]\n" + runtime_analysis_json,
            "[Runtime Directives]\n- " + "\n- ".join(runtime_directives),
            "[Parallel Thinking]\n" + _parallel_think_prompt_block(parallel_result),
            "[Workflow Graph]\n" + _workflow_prompt_block(workflow_result),
            "[AutoGen Chat]\n" + _autogen_prompt_block(conversation_result),
            "[SuperAGI Autonomy]\n" + _superagi_prompt_block(autonomy_result),
            "[MetaGPT Dev]\n" + _metagpt_prompt_block(metagpt_result),
            "[Agentic Improve]\n" + _agentic_prompt_block(agentic_result),
            "[Mode Recall]\n- " + "\n- ".join(mode_lines),
            "[Letta Recall]\n" + _compact_text_for_prompt(letta_recall.get("summary") or "No episodic recalls.", limit=520),
            "[Phidata RAG]\n" + _compact_text_for_prompt(phidata_context.get("summary") or "No RAG context.", limit=420),
            "[Praison Reflection]\n" + _praison_prompt_block(praison_reflect),
            "[System Health]\n" + str(health_report.get("summary") or "Agents: status unavailable."),
            "[Profile Recall]\n- " + "\n- ".join(runtime_lines) + "\n" + profile_lines,
        ]
    )
    max_prompt_chars = _chat_prompt_max_chars()
    if max_prompt_chars and len(base_prompt) > max_prompt_chars:
        base_prompt = base_prompt[: max_prompt_chars - 1].rstrip() + "…"
    elapsed_s = round(perf_counter() - started_at, 4)
    analysis["prompt_build_latency_s"] = elapsed_s
    _LOG.info("latency: %.4f sec", elapsed_s)
    return apply_variation(base_prompt, analysis), analysis


def build_chat_system_prompt(
    memories: list[dict],
    response_style_hint: str | None,
    *,
    user_message: str,
    history: list[dict],
    owner_direct_mode: bool = True,
    tone_analysis: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    return build_dynamic_prompt(
        memories,
        response_style_hint,
        user_message=user_message,
        history=history,
        owner_direct_mode=owner_direct_mode,
        tone_analysis=tone_analysis,
    )


def _parse_history_arg(raw: str | None) -> list[dict]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def _parse_memories_arg(raw: str | None) -> list[dict]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Astra tone analysis helper")
    parser.add_argument("--message", required=True, help="Current user message")
    parser.add_argument("--history-json", default="", help="JSON array of chat history objects")
    parser.add_argument("--memories-json", default="", help="JSON array of profile memory objects")
    args = parser.parse_args()

    history = _parse_history_arg(args.history_json)
    memories = _parse_memories_arg(args.memories_json)
    analysis = analyze_tone(
        args.message,
        history,
        memories=memories,
    )
    _, runtime_analysis = build_dynamic_prompt(
        memories,
        None,
        user_message=args.message,
        history=history,
        owner_direct_mode=True,
        tone_analysis=analysis,
    )
    payload = {
        "analysis": runtime_analysis,
        "path": runtime_analysis.get("path"),
        "prompt_build_latency_s": runtime_analysis.get("prompt_build_latency_s"),
        "parallel_mode": (runtime_analysis.get("parallel_think") or {}).get("mode"),
        "workflow_mode": (runtime_analysis.get("workflow_graph") or {}).get("mode"),
        "workflow_executed": bool((runtime_analysis.get("workflow_graph") or {}).get("executed")),
        "conversation_mode": (runtime_analysis.get("autogen_chat") or {}).get("mode"),
        "conversation_executed": bool((runtime_analysis.get("autogen_chat") or {}).get("executed")),
        "autonomy_mode": (runtime_analysis.get("superagi_autonomy") or {}).get("mode"),
        "autonomy_started": bool((runtime_analysis.get("superagi_autonomy") or {}).get("started")),
        "metagpt_mode": (runtime_analysis.get("metagpt_dev") or {}).get("mode"),
        "metagpt_generated_code": bool((runtime_analysis.get("metagpt_dev") or {}).get("generated_code")),
        "self_improve_mode": bool((runtime_analysis.get("agentic_improve") or {}).get("self_improve")),
        "self_improve_updated": bool((runtime_analysis.get("agentic_improve") or {}).get("updated")),
        "reflection_boost": (runtime_analysis.get("praison_reflect") or {}).get("mode_boost"),
        "agents_health": (runtime_analysis.get("system_health") or {}).get("summary"),
        "agents_active_count": (runtime_analysis.get("system_health") or {}).get("active_count"),
        "tools_rag": (runtime_analysis.get("phidata_context") or {}).get("recommended_tools") or [],
        "memory_update": bool((runtime_analysis.get("letta_update") or {}).get("updated")),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
