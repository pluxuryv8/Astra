from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from apps.api.auth import require_auth
from apps.api.models import ApprovalDecisionRequest, RunCreate
from core.agent import (
    analyze_tone,
    build_dynamic_prompt as build_agent_dynamic_prompt,
    build_tone_profile_memory_payload,
    merge_memory_payloads,
)
from core.brain.router import get_brain
from core.brain.types import LLMRequest
from core.chat_context import (
    build_chat_messages,
    build_user_profile_context,
)
from core.event_bus import emit
from core.intent_router import INTENT_ACT, INTENT_ASK, INTENT_CHAT, IntentDecision, IntentRouter
from core.llm_routing import ContextItem
from core.memory.interpreter import MemoryInterpretationError, interpret_user_message_for_memory
from core.skill_context import SkillContext
from core.semantic.decision import SemanticDecisionError
from core.skills.result_types import ArtifactCandidate, SkillResult, SourceCandidate
from memory.db import now_iso
from memory import store
from skills.memory_save import skill as memory_save_skill
from skills.web_research import skill as web_research_skill

router = APIRouter(prefix="/api/v1", tags=["runs"], dependencies=[Depends(require_auth)])

CHAT_HISTORY_TURNS = 20
_APP_BASE_DIR = Path(__file__).resolve().parents[3]
_SOFT_RETRY_PROMPT = "Продолжи ответ точно по запросу владельца, полностью и без добавлений."
_SOFT_RETRY_PROMPT_LANG_RU = (
    "Перепиши ответ полностью на русском языке, строго по запросу владельца, без добавлений и без английских вставок."
)
_SOFT_RETRY_PROMPT_OFF_TOPIC = (
    "Ответ не по теме. Ответь строго на вопрос владельца, по существу, без смены темы и без лишних отступлений."
)
_SOFT_RETRY_UNWANTED_PREFIXES = (
    "как ии", "как ai", "как языков", "извините",
    "я не могу", "я не должен", "против правил", "это нарушает",
    "согласно политике", "ограничения безопасности"
)
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_RELEVANCE_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+")
_FIRST_PERSON_RU_RE = re.compile(r"\b(я|мне|меня|мой|моя|моё|мои|мною)\b", flags=re.IGNORECASE)
_FIRST_PERSON_NARRATIVE_RU_RE = re.compile(
    r"\b(был|была|было|попал|попала|пришел|пришла|думал|думала|вспомнил|вспомнила|расскажу)\b",
    flags=re.IGNORECASE,
)
_RELEVANCE_STOPWORDS = {
    "как", "что", "это", "где", "когда", "почему", "зачем", "или", "и", "а", "но", "же",
    "ли", "по", "на", "в", "с", "к", "из", "о", "об", "для", "про", "у", "от", "до",
    "the", "and", "or", "for", "with", "from", "into", "about", "this", "that", "what", "how",
}
_TOPIC_ANCHOR_EXCLUDE = {
    "пытали", "пытать", "пытался", "пыталась",
    "сюжет", "история", "знаешь", "знаете",
    "объясни", "объяснить", "расскажи", "рассказать",
    "сделай", "сделать", "можно", "нужно", "помоги", "помочь",
    "why", "how", "what", "explain", "tell", "help",
}
_AUTO_WEB_RESEARCH_INFO_QUERY_RE = re.compile(
    r"\b("
    r"кто|что|где|когда|почему|зачем|как|сколько|какой|какая|какие|чей|чья|чьи|"
    r"знаешь|знаете|расскажи|объясни|объяснить|сюжет|история|факт|факты|"
    r"who|what|where|when|why|how|explain|tell|fact|facts"
    r")\b",
    flags=re.IGNORECASE,
)
_AUTO_WEB_RESEARCH_UNCERTAIN_RE = re.compile(
    r"\b("
    r"не знаю|не уверен|не слышал|не слышала|не помню|не могу подтвердить|"
    r"возможно|наверное|предполагаю|скорее всего|может быть|"
    r"not sure|i don't know|i am not sure|maybe|probably|i guess|i think"
    r")\b",
    flags=re.IGNORECASE,
)
_AUTO_WEB_RESEARCH_ERROR_CODES = {
    "chat_empty_response",
    "connection_error",
    "http_error",
    "invalid_json",
    "model_not_found",
    "chat_llm_unhandled_error",
}
_FAST_CHAT_ACTION_RE = re.compile(
    r"\b("
    r"напомни|через\s+\d+|открой|запусти|выполни|кликни|нажми|перейди|удали|очисти|"
    r"отправь|оплати|переведи|создай\s+напомин|deploy|terminal|командн\w+\s+строк\w+|"
    r"браузер|browser|file|файл|папк\w+"
    r")\b",
    flags=re.IGNORECASE,
)
_FAST_CHAT_MEMORY_RE = re.compile(
    r"\b("
    r"запомни|сохрани\s+в\s+память|добавь\s+в\s+память|меня\s+\S+\s+зовут|меня\s+зовут|мо[её]\s+имя|"
    r"называй\s+меня|предпочитаю|remember\s+this|my\s+name\s+is|save\s+to\s+memory"
    r")\b",
    flags=re.IGNORECASE,
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _chat_temperature_default() -> float:
    value = _env_float("ASTRA_LLM_CHAT_TEMPERATURE", 0.35)
    return max(0.1, min(1.0, value))


def _chat_top_p_default() -> float:
    value = _env_float("ASTRA_LLM_CHAT_TOP_P", 0.9)
    return max(0.0, min(1.0, value))


def _chat_repeat_penalty_default() -> float:
    value = _env_float("ASTRA_LLM_CHAT_REPEAT_PENALTY", 1.15)
    return max(1.0, value)


def _chat_num_predict_default() -> int:
    value = _env_int("ASTRA_LLM_OLLAMA_NUM_PREDICT", 256)
    return max(64, min(2048, value))


def _owner_direct_mode_enabled() -> bool:
    return _env_bool("ASTRA_OWNER_DIRECT_MODE", True)


def _fast_chat_path_enabled() -> bool:
    return _env_bool("ASTRA_CHAT_FAST_PATH_ENABLED", True)


def _fast_chat_max_chars() -> int:
    value = _env_int("ASTRA_CHAT_FAST_PATH_MAX_CHARS", 220)
    return max(60, min(600, value))


def _chat_auto_web_research_enabled() -> bool:
    return _env_bool("ASTRA_CHAT_AUTO_WEB_RESEARCH_ENABLED", True)


def _chat_auto_web_research_max_rounds() -> int:
    value = _env_int("ASTRA_CHAT_AUTO_WEB_RESEARCH_MAX_ROUNDS", 2)
    return max(1, min(4, value))


def _chat_auto_web_research_max_sources_total() -> int:
    value = _env_int("ASTRA_CHAT_AUTO_WEB_RESEARCH_MAX_SOURCES", 6)
    return max(1, min(16, value))


def _chat_auto_web_research_max_pages_fetch() -> int:
    value = _env_int("ASTRA_CHAT_AUTO_WEB_RESEARCH_MAX_PAGES", 4)
    return max(1, min(12, value))


def _chat_auto_web_research_depth() -> str:
    value = (os.getenv("ASTRA_CHAT_AUTO_WEB_RESEARCH_DEPTH") or "brief").strip().lower()
    if value in {"brief", "normal", "deep"}:
        return value
    return "brief"


def _is_fast_chat_candidate(text: str, *, qa_mode: bool) -> bool:
    if qa_mode or not _fast_chat_path_enabled():
        return False
    query = (text or "").strip()
    if not query:
        return False
    if len(query) > _fast_chat_max_chars():
        return False
    words = [part for part in re.split(r"\s+", query) if part]
    if len(words) > 32:
        return False
    lowered = query.lower()
    if _FAST_CHAT_ACTION_RE.search(lowered):
        return False
    if _FAST_CHAT_MEMORY_RE.search(lowered):
        return False
    return True


def _get_engine(request: Request):
    engine = request.app.state.engine
    if not engine:
        raise RuntimeError("Движок запусков не инициализирован")
    return engine


def _is_qa_request(request: Request) -> bool:
    header = request.headers.get("X-Astra-QA-Mode", "").strip().lower()
    if header in {"1", "true", "yes", "on"}:
        return True
    return os.getenv("ASTRA_QA_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def _build_snapshot(run_id: str) -> dict:
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    plan = store.list_plan_steps(run_id)
    tasks = store.list_tasks(run_id)
    sources = store.list_sources(run_id)
    facts = store.list_facts(run_id)
    conflicts = store.list_conflicts(run_id)
    artifacts = store.list_artifacts(run_id)
    approvals = store.list_approvals(run_id)
    last_events = store.list_events(run_id, limit=200)

    if plan:
        total = len(plan)
        done = len([p for p in plan if p.get("status") == "done"])
    else:
        total = len(tasks)
        done = len([t for t in tasks if t.get("status") == "done"])

    open_conflicts = len([c for c in conflicts if c.get("status") == "open"])

    timestamps = [s.get("retrieved_at") for s in sources if s.get("retrieved_at")]
    timestamps = [t for t in timestamps if t]
    freshness = None
    if timestamps:
        freshness = {
            "min": min(timestamps),
            "max": max(timestamps),
            "count": len(timestamps),
        }

    metrics = {
        "coverage": {"done": done, "total": total},
        "conflicts": open_conflicts,
        "freshness": freshness,
    }

    return {
        "run": run,
        "plan": plan,
        "tasks": tasks,
        "sources": sources,
        "facts": facts,
        "conflicts": conflicts,
        "artifacts": artifacts,
        "approvals": approvals,
        "metrics": metrics,
        "last_events": last_events,
    }


def _intent_summary(decision) -> str:
    parts = [f"intent={decision.intent}"]
    if decision.plan_hint:
        parts.append(f"plan_hint={','.join(decision.plan_hint)}")
    if decision.memory_item:
        parts.append("memory_item=1")
    return "; ".join(parts)


def _emit_intent_decided(run_id: str, decision, selected_mode: str | None) -> None:
    emit(
        run_id,
        "intent_decided",
        "Интент определён",
        {
            "intent": decision.intent,
            "confidence": decision.confidence,
            "reasons": decision.reasons,
            "danger_flags": decision.act_hint.danger_flags if decision.act_hint else [],
            "suggested_mode": decision.act_hint.suggested_run_mode if decision.act_hint else selected_mode,
            "selected_mode": selected_mode,
            "target": decision.act_hint.target if decision.act_hint else None,
            "decision_path": decision.decision_path,
            "summary": _intent_summary(decision),
        },
    )


def _semantic_resilience_decision(error_code: str) -> IntentDecision:
    # Semantic classification is infra and can fail independently from chat generation.
    # We degrade to CHAT to preserve a useful user response instead of returning 502.
    return IntentDecision(
        intent=INTENT_CHAT,
        confidence=0.0,
        reasons=["semantic_resilience", error_code],
        questions=[],
        needs_clarification=False,
        act_hint=None,
        plan_hint=["CHAT_RESPONSE"],
        memory_item=None,
        response_style_hint=None,
        user_visible_note="Семантическая классификация недоступна, отвечаю напрямую.",
        decision_path="semantic_resilience",
    )


def _chat_resilience_text(error_type: str | None) -> str:
    if error_type == "budget_exceeded":
        return "Лимит обращений к модели исчерпан для этого запуска. Попробуй ещё раз чуть позже."
    if error_type == "missing_api_key":
        return "Облачная модель недоступна: не задан OPENAI_API_KEY."
    if error_type and "llm_call_failed" in error_type:
        return "Локальная модель сейчас недоступна. Проверь Ollama и выбранную модель, затем повтори запрос."
    if error_type in {"model_not_found", "http_error", "connection_error", "invalid_json", "chat_empty_response"}:
        return "Локальная модель сейчас недоступна. Проверь Ollama и выбранную модель, затем повтори запрос."
    return "Не удалось получить ответ модели. Повтори запрос."


def _save_memory_payload(run: dict, payload: dict[str, Any] | None, settings: dict[str, Any]) -> None:
    if not payload:
        return
    ctx = SimpleNamespace(run=run, task={}, plan_step={}, settings=settings)
    memory_save_skill.run(payload, ctx)


def _save_memory_payload_async(run: dict, payload: dict[str, Any] | None, settings: dict[str, Any]) -> None:
    if not payload:
        return

    run_snapshot = dict(run)
    payload_snapshot = dict(payload)
    settings_snapshot = dict(settings)

    def _worker() -> None:
        try:
            _save_memory_payload(run_snapshot, payload_snapshot, settings_snapshot)
        except Exception as exc:  # noqa: BLE001
            emit(
                run_snapshot.get("id") or "memory_save",
                "llm_request_failed",
                "Memory save failed",
                {
                    "provider": "local",
                    "model_id": None,
                    "error_type": "memory_save_failed",
                    "http_status_if_any": None,
                    "retry_count": 0,
                },
                level="warning",
            )

    threading.Thread(
        target=_worker,
        daemon=True,
        name=f"memory-save-{(run_snapshot.get('id') or 'run')[:8]}",
    ).start()


def _style_hint_from_interpretation(memory_interpretation: dict[str, Any] | None) -> str | None:
    if not isinstance(memory_interpretation, dict):
        return None
    preferences = memory_interpretation.get("preferences")
    if not isinstance(preferences, list):
        return None
    hints: list[str] = []
    for item in preferences:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        value = item.get("value")
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        key = key.strip().lower()
        value = value.strip()
        if not value:
            continue
        if key == "style.brevity" and value.lower() in {"short", "brief", "compact"}:
            hints.append("Отвечай коротко и по делу.")
        elif key == "style.tone":
            hints.append(f"Тон ответа: {value}.")
        elif key == "user.addressing.preference":
            hints.append(f"Формат обращения к пользователю: {value}.")
        elif key == "response.format":
            hints.append(f"Формат ответа: {value}.")
    unique = []
    for hint in hints:
        if hint not in unique:
            unique.append(hint)
    if not unique:
        return None
    return " ".join(unique[:3])


def _name_from_interpretation(memory_interpretation: dict[str, Any] | None) -> str | None:
    if not isinstance(memory_interpretation, dict):
        return None
    facts = memory_interpretation.get("facts")
    if not isinstance(facts, list):
        return None
    for item in facts:
        if not isinstance(item, dict):
            continue
        if item.get("key") != "user.name":
            continue
        value = item.get("value")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _memory_payload_from_interpretation(query_text: str, memory_interpretation: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(memory_interpretation, dict):
        return None
    if memory_interpretation.get("should_store") is not True:
        return None
    summary = memory_interpretation.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None
    title = memory_interpretation.get("title") if isinstance(memory_interpretation.get("title"), str) else "Профиль пользователя"
    return {
        "content": summary.strip(),
        "origin": "auto",
        "memory_payload": {
            "title": title.strip() or "Профиль пользователя",
            "summary": summary.strip(),
            "confidence": memory_interpretation.get("confidence"),
            "facts": memory_interpretation.get("facts") if isinstance(memory_interpretation.get("facts"), list) else [],
            "preferences": memory_interpretation.get("preferences")
            if isinstance(memory_interpretation.get("preferences"), list)
            else [],
            "possible_facts": memory_interpretation.get("possible_facts")
            if isinstance(memory_interpretation.get("possible_facts"), list)
            else [],
        },
    }


def _known_profile_payload(memories: list[dict]) -> dict[str, Any]:
    trimmed: list[dict[str, Any]] = []
    for item in memories[:20]:
        if not isinstance(item, dict):
            continue
        trimmed.append(
            {
                "title": item.get("title"),
                "content": item.get("content"),
                "meta": item.get("meta") if isinstance(item.get("meta"), dict) else {},
            }
        )
    return {"memories": trimmed}


def _style_hint_from_tone_analysis(tone_analysis: dict[str, Any] | None) -> str | None:
    if not isinstance(tone_analysis, dict):
        return None
    tone_type = str(tone_analysis.get("type") or "").strip().lower()
    mirror_level = str(tone_analysis.get("mirror_level") or "medium").strip().lower()

    if tone_type == "dry":
        return "Коротко и структурно: сначала ответ, затем шаги."
    if tone_type == "frustrated":
        return "Коротко валидируй состояние и сразу предложи конкретный план."
    if tone_type == "tired":
        return "Спокойный поддерживающий тон, без лишнего текста."
    if tone_type == "energetic":
        return "Живой темп и деловая конкретика."
    if tone_type == "crisis":
        return "Сначала стабилизация, затем короткий антикризисный план."
    if tone_type == "reflective":
        return "Спокойный вдумчивый тон с ясными выводами."
    if tone_type == "creative":
        return "Креативные варианты, но с прикладной структурой."
    if mirror_level == "low":
        return "Формально и точно, минимум разговорных вставок."
    return None


def _build_chat_system_prompt(
    memories: list[dict],
    response_style_hint: str | None,
    owner_direct_mode: bool | None = None,
    *,
    user_message: str = "",
    history: list[dict] | None = None,
    tone_analysis: dict[str, Any] | None = None,
) -> str:
    if owner_direct_mode is None:
        owner_direct_mode = _owner_direct_mode_enabled()
    prompt, _analysis = build_agent_dynamic_prompt(
        memories,
        response_style_hint,
        user_message=user_message,
        history=history or [],
        owner_direct_mode=owner_direct_mode,
        tone_analysis=tone_analysis,
    )
    if _CYRILLIC_RE.search(user_message or ""):
        prompt = (
            f"{prompt}\n\n"
            "[Language Lock]\n"
            "- Отвечай только на русском языке.\n"
            "- Не переключайся на английский без явной просьбы владельца.\n"
            "- Английские слова допустимы только для кода/терминов."
        )
    return prompt


def _is_likely_truncated_response(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if stripped.endswith(("...", "…", ":", ";", ",", "(", "[", "{", "—", "-")):
        return True
    if stripped.count("```") % 2 == 1:
        return True
    return False


def _is_ru_language_mismatch(user_text: str, response_text: str) -> bool:
    if not user_text.strip() or not response_text.strip():
        return False
    if not _CYRILLIC_RE.search(user_text):
        return False
    return not bool(_CYRILLIC_RE.search(response_text))


def _relevance_tokens(text: str) -> list[str]:
    return [token.lower() for token in _RELEVANCE_TOKEN_RE.findall(text or "")]


def _query_focus_tokens(text: str, *, limit: int = 8) -> list[str]:
    focus: list[str] = []
    seen: set[str] = set()
    for token in _relevance_tokens(text):
        if len(token) < 3 or token in _RELEVANCE_STOPWORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        focus.append(token)
        if len(focus) >= limit:
            break
    return focus


def _focus_overlap_count(focus_tokens: list[str], response_tokens: list[str]) -> int:
    if not focus_tokens or not response_tokens:
        return 0
    response_set = set(response_tokens)
    long_response_tokens = [token for token in response_set if len(token) >= 5]
    overlap = 0
    for focus in focus_tokens:
        if focus in response_set:
            overlap += 1
            continue
        if len(focus) < 5:
            continue
        stem = focus[:5]
        if any(token.startswith(stem) for token in long_response_tokens):
            overlap += 1
    return overlap


def _topic_anchor_tokens(focus_tokens: list[str]) -> list[str]:
    return [token for token in focus_tokens if token not in _TOPIC_ANCHOR_EXCLUDE]


def _is_likely_off_topic(user_text: str, response_text: str) -> bool:
    if not user_text.strip() or not response_text.strip():
        return False
    focus = _query_focus_tokens(user_text)
    if len(focus) < 2:
        return False
    response_tokens = _relevance_tokens(response_text)
    overlap = _focus_overlap_count(focus, response_tokens)
    query_words = [part for part in re.split(r"\s+", user_text.strip()) if part]
    anchor_focus = _topic_anchor_tokens(focus)
    if len(anchor_focus) >= 2:
        anchor_overlap = _focus_overlap_count(anchor_focus, response_tokens)
        if anchor_overlap == 0:
            return True
        if len(anchor_focus) >= 3 and len(query_words) <= 20 and anchor_overlap <= 1:
            return True
        critical_focus = [token for token in anchor_focus if len(token) >= 6]
        if critical_focus and _focus_overlap_count(critical_focus, response_tokens) == 0:
            return True
        if len(critical_focus) >= 2:
            critical_overlap = _focus_overlap_count(critical_focus, response_tokens)
            if critical_overlap <= len(critical_focus) - 1 and len(query_words) <= 20:
                return True
    if overlap == 0:
        return True
    return len(focus) >= 4 and len(query_words) <= 16 and overlap <= 1


def _is_unprompted_first_person_narrative(user_text: str, response_text: str) -> bool:
    if not response_text.strip():
        return False
    if _FIRST_PERSON_RU_RE.search(user_text):
        return False
    first_person_hits = _FIRST_PERSON_RU_RE.findall(response_text)
    if len(first_person_hits) < 1:
        return False
    return bool(_FIRST_PERSON_NARRATIVE_RU_RE.search(response_text))


def _has_unwanted_prefix(text: str) -> bool:
    lowered = text.strip().lower()
    return any(lowered.startswith(prefix) for prefix in _SOFT_RETRY_UNWANTED_PREFIXES)


def _soft_retry_reason(user_text: str, text: str) -> str | None:
    if _has_unwanted_prefix(text):
        return "unwanted_prefix"
    if _is_ru_language_mismatch(user_text, text):
        return "ru_language_mismatch"
    if _is_unprompted_first_person_narrative(user_text, text):
        return "off_topic"
    if _is_likely_off_topic(user_text, text):
        return "off_topic"
    if _is_likely_truncated_response(text):
        return "truncated"
    return None


def _soft_retry_prompt(reason: str) -> str:
    if reason == "ru_language_mismatch":
        return _SOFT_RETRY_PROMPT_LANG_RU
    if reason == "off_topic":
        return _SOFT_RETRY_PROMPT_OFF_TOPIC
    return _SOFT_RETRY_PROMPT


def _last_user_message(messages: list[dict[str, Any]] | None) -> str:
    if not messages:
        return ""
    for item in reversed(messages):
        if str(item.get("role", "")).strip().lower() != "user":
            continue
        content = item.get("content")
        return content.strip() if isinstance(content, str) else ""
    return ""


def _call_chat_base_fallback(brain, request: LLMRequest, ctx) -> Any:
    # Switch purpose so router picks base chat model instead of tiered fast/complex model.
    fallback_request = replace(request, purpose="chat_response_base_fallback")
    try:
        fallback_response = brain.call(fallback_request, ctx)
    except Exception:  # noqa: BLE001
        return None
    if fallback_response.status == "ok" and (fallback_response.text or "").strip():
        return fallback_response
    return None


def _retry_off_topic_with_min_prompt(brain, request: LLMRequest, ctx, *, user_text: str) -> Any:
    if not user_text.strip():
        return None
    focused_messages = [
        {
            "role": "system",
            "content": (
                "Ответь строго по вопросу пользователя. Без смены темы, без мета-комментариев. "
                "Если не знаешь точный ответ, честно скажи это и попроси уточнение."
            ),
        },
        {"role": "user", "content": user_text.strip()},
    ]
    focused_request = replace(
        request,
        purpose="chat_response_base_fallback",
        messages=focused_messages,
    )
    try:
        focused_response = brain.call(focused_request, ctx)
    except Exception:  # noqa: BLE001
        return None
    text = focused_response.text or ""
    if focused_response.status == "ok" and text.strip() and _soft_retry_reason(user_text, text) != "off_topic":
        return focused_response
    return None


def _off_topic_guard_text(user_text: str) -> str:
    query = " ".join((user_text or "").split()).strip()
    if not query:
        return "Ответ ушёл от темы. Повтори вопрос одним предложением, отвечу строго по сути."
    return (
        f"Понял запрос: «{query}». Предыдущий ответ вышел не по теме. "
        "Могу дать короткий или подробный ответ строго по этому вопросу."
    )


def _rewrite_response_in_russian(brain, request: LLMRequest, ctx, *, user_text: str, draft_text: str) -> Any:
    rewrite_messages = [
        {
            "role": "system",
            "content": (
                "Ты редактор ответа ассистента. Перепиши ответ строго на русском языке, "
                "без английских вставок и без добавления новых фактов. "
                "Верни только итоговый ответ без заголовков, без префиксов и без служебных пометок."
            ),
        },
        {
            "role": "user",
            "content": (
                f"[Запрос пользователя]\n{user_text.strip()}\n\n"
                f"[Черновик ответа]\n{draft_text.strip()}\n\n"
                "Сделай итоговый ответ полностью на русском языке и выведи только финальный текст."
            ),
        },
    ]
    rewrite_request = replace(
        request,
        purpose="chat_response_base_fallback",
        messages=rewrite_messages,
    )
    try:
        rewrite_response = brain.call(rewrite_request, ctx)
    except Exception:  # noqa: BLE001
        return None
    text = rewrite_response.text or ""
    if rewrite_response.status == "ok" and text.strip() and _CYRILLIC_RE.search(text):
        return rewrite_response
    return None


def _call_chat_with_soft_retry(brain, request: LLMRequest, ctx) -> Any:
    response = brain.call(request, ctx)
    if response.status != "ok":
        return response

    if not (response.text or "").strip():
        fallback = _call_chat_base_fallback(brain, request, ctx)
        return fallback or response

    user_text = _last_user_message(request.messages)
    reason = _soft_retry_reason(user_text, response.text or "")
    if not reason:
        return response

    if reason == "off_topic":
        focused = _retry_off_topic_with_min_prompt(brain, request, ctx, user_text=user_text)
        if focused is not None:
            return focused

    if reason == "ru_language_mismatch":
        rewritten = _rewrite_response_in_russian(
            brain,
            request,
            ctx,
            user_text=user_text,
            draft_text=response.text or "",
        )
        if rewritten is not None:
            return rewritten

    retry_messages = list(request.messages or [])
    retry_messages.append({"role": "assistant", "content": response.text})
    retry_messages.append({"role": "user", "content": _soft_retry_prompt(reason)})
    retry_request = replace(request, messages=retry_messages)
    try:
        retry_response = brain.call(retry_request, ctx)
    except Exception:  # noqa: BLE001
        retry_response = response

    if retry_response.status == "ok" and (retry_response.text or "").strip():
        if reason == "off_topic" and _soft_retry_reason(user_text, retry_response.text or "") == "off_topic":
            fallback = _call_chat_base_fallback(brain, request, ctx)
            if fallback is not None and _soft_retry_reason(user_text, fallback.text or "") != "off_topic":
                return fallback
            return replace(retry_response, text=_off_topic_guard_text(user_text))
        return retry_response

    fallback = _call_chat_base_fallback(brain, request, ctx)
    if reason == "off_topic" and fallback is None:
        return replace(response, text=_off_topic_guard_text(user_text))
    return fallback or response


def _is_information_query(user_text: str) -> bool:
    query = (user_text or "").strip()
    if not query:
        return False
    lowered = query.lower()
    if _FAST_CHAT_ACTION_RE.search(lowered):
        return False
    if _FAST_CHAT_MEMORY_RE.search(lowered):
        return False
    if "?" in query:
        return True
    if _AUTO_WEB_RESEARCH_INFO_QUERY_RE.search(lowered):
        return True
    words = [part for part in re.split(r"\s+", query) if part]
    return len(words) >= 7


def _is_uncertain_response(text: str) -> bool:
    value = (text or "").strip()
    if not value:
        return True
    lowered = value.lower()
    if "предыдущий ответ вышел не по теме" in lowered:
        return True
    return bool(_AUTO_WEB_RESEARCH_UNCERTAIN_RE.search(lowered))


def _should_auto_web_research(user_text: str, response_text: str, *, error_type: str | None = None) -> bool:
    if not _chat_auto_web_research_enabled():
        return False
    if not _is_information_query(user_text):
        return False
    if error_type in _AUTO_WEB_RESEARCH_ERROR_CODES:
        return True
    answer = (response_text or "").strip()
    if not answer:
        return True
    if _soft_retry_reason(user_text, answer) in {"off_topic", "ru_language_mismatch"}:
        return True
    return _is_uncertain_response(answer)


def _source_value(source: SourceCandidate | dict[str, Any], key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def _artifact_value(artifact: ArtifactCandidate | dict[str, Any], key: str) -> Any:
    if isinstance(artifact, dict):
        return artifact.get(key)
    return getattr(artifact, key, None)


def _read_web_research_answer(result: SkillResult) -> str:
    artifacts = list(result.artifacts or [])
    artifacts.sort(key=lambda item: 0 if str(_artifact_value(item, "type") or "") == "web_research_answer_md" else 1)
    for artifact in artifacts:
        content_uri = str(_artifact_value(artifact, "content_uri") or "").strip()
        if not content_uri:
            continue
        path = Path(content_uri)
        if not path.is_absolute():
            path = _APP_BASE_DIR / path
        try:
            text = path.read_text(encoding="utf-8").strip()
        except Exception:  # noqa: BLE001
            continue
        if text:
            return text
    return ""


def _format_web_research_sources(sources: list[SourceCandidate | dict[str, Any]], *, limit: int = 5) -> str:
    lines: list[str] = []
    seen_urls: set[str] = set()
    for item in sources:
        url = str(_source_value(item, "url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        title = str(_source_value(item, "title") or "").strip()
        label = title or url
        lines.append(f"- {label} - {url}")
        if len(lines) >= limit:
            break
    return "\n".join(lines)


def _compose_web_research_chat_text(result: SkillResult) -> str:
    answer = _read_web_research_answer(result)
    if not answer:
        summary = str(result.what_i_did or "").strip()
        if summary:
            answer = f"{summary}\n\nЯ проверил источники и собрал данные из интернета."
    sources_block = _format_web_research_sources(list(result.sources or []))
    if sources_block and "источники:" not in answer.lower():
        answer = f"{answer.strip()}\n\nИсточники:\n{sources_block}".strip()
    return answer.strip()


def _persist_web_research_result(run_id: str, result: SkillResult) -> None:
    try:
        existing_source_urls = {
            str(item.get("url") or "").strip()
            for item in store.list_sources(run_id)
            if str(item.get("url") or "").strip()
        }
        sources_payload: list[dict[str, Any]] = []
        for source in result.sources or []:
            url = str(_source_value(source, "url") or "").strip()
            if not url or url in existing_source_urls:
                continue
            existing_source_urls.add(url)
            sources_payload.append(
                {
                    "id": str(uuid.uuid4()),
                    "url": url,
                    "title": _source_value(source, "title"),
                    "domain": _source_value(source, "domain"),
                    "quality": _source_value(source, "quality"),
                    "retrieved_at": _source_value(source, "retrieved_at") or now_iso(),
                    "snippet": _source_value(source, "snippet"),
                    "pinned": bool(_source_value(source, "pinned")),
                }
            )
        if sources_payload:
            store.insert_sources(run_id, sources_payload)
    except Exception:  # noqa: BLE001
        pass

    try:
        existing_artifact_uris = {
            str(item.get("content_uri") or "").strip()
            for item in store.list_artifacts(run_id)
            if str(item.get("content_uri") or "").strip()
        }
        artifacts_payload: list[dict[str, Any]] = []
        for artifact in result.artifacts or []:
            content_uri = str(_artifact_value(artifact, "content_uri") or "").strip()
            if not content_uri or content_uri in existing_artifact_uris:
                continue
            existing_artifact_uris.add(content_uri)
            artifacts_payload.append(
                {
                    "id": str(uuid.uuid4()),
                    "type": str(_artifact_value(artifact, "type") or "artifact"),
                    "title": str(_artifact_value(artifact, "title") or "Artifact"),
                    "content_uri": content_uri,
                    "created_at": _artifact_value(artifact, "created_at") or now_iso(),
                    "meta": _artifact_value(artifact, "meta") if isinstance(_artifact_value(artifact, "meta"), dict) else {},
                }
            )
        if artifacts_payload:
            store.insert_artifacts(run_id, artifacts_payload)
    except Exception:  # noqa: BLE001
        pass


def _emit_web_research_progress(run_id: str, events: list[dict[str, Any]] | None) -> None:
    for item in events or []:
        if not isinstance(item, dict):
            continue
        message = str(item.get("message") or "").strip()
        if not message:
            continue
        payload = {key: value for key, value in item.items() if key not in {"type", "message"}}
        emit(
            run_id,
            "task_progress",
            message,
            payload if isinstance(payload, dict) else {},
        )


def _run_auto_web_research(
    run: dict[str, Any],
    settings: dict[str, Any] | None,
    *,
    query_text: str,
    response_style_hint: str | None,
) -> dict[str, Any] | None:
    run_id = str(run.get("id") or "").strip()
    if not run_id:
        return None

    step_id = f"chat-web-research-step:{run_id}"
    task_id = f"chat-web-research-task:{run_id}"
    step = {
        "id": step_id,
        "run_id": run_id,
        "kind": "WEB_RESEARCH",
        "skill_name": "web_research",
        "title": "Chat auto web research",
    }
    task = {"id": task_id, "run_id": run_id}
    ctx = SkillContext(
        run=run,
        plan_step=step,
        task=task,
        settings=settings if isinstance(settings, dict) else {},
        base_dir=str(_APP_BASE_DIR),
    )
    inputs: dict[str, Any] = {
        "query": query_text.strip(),
        "mode": "deep",
        "depth": _chat_auto_web_research_depth(),
        "max_rounds": _chat_auto_web_research_max_rounds(),
        "max_sources_total": _chat_auto_web_research_max_sources_total(),
        "max_pages_fetch": _chat_auto_web_research_max_pages_fetch(),
    }
    if isinstance(response_style_hint, str) and response_style_hint.strip():
        inputs["style_hint"] = response_style_hint.strip()

    emit(
        run_id,
        "task_progress",
        "Проверяю данные в интернете",
        {"phase": "chat_auto_web_research_started", "query": query_text.strip()},
    )
    started_at = time.time()
    try:
        result = web_research_skill.run(inputs, ctx)
    except Exception as exc:  # noqa: BLE001
        emit(
            run_id,
            "task_progress",
            "Auto web research не удался",
            {"phase": "chat_auto_web_research_failed", "error": str(exc)},
            level="warning",
        )
        return None
    latency_ms = int((time.time() - started_at) * 1000)
    _emit_web_research_progress(run_id, result.events)
    text = _compose_web_research_chat_text(result)
    if not text:
        emit(
            run_id,
            "task_progress",
            "Auto web research не дал итогового ответа",
            {"phase": "chat_auto_web_research_empty"},
            level="warning",
        )
        return None

    if _soft_retry_reason(query_text, text) == "off_topic":
        emit(
            run_id,
            "task_progress",
            "Auto web research вернул нерелевантный ответ",
            {"phase": "chat_auto_web_research_off_topic", "query": query_text.strip()},
            level="warning",
        )
        return None

    _persist_web_research_result(run_id, result)
    emit(
        run_id,
        "task_progress",
        "Auto web research завершён",
        {
            "phase": "chat_auto_web_research_done",
            "sources_count": len(result.sources or []),
            "latency_ms": latency_ms,
            "confidence": result.confidence,
        },
    )
    return {
        "text": text,
        "latency_ms": latency_ms,
        "sources_count": len(result.sources or []),
        "confidence": result.confidence,
    }


@router.post("/projects/{project_id}/runs")
def create_run(project_id: str, payload: RunCreate, request: Request):
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")

    # EN kept: значения режимов — публичный контракт API/клиента
    allowed_modes = {"plan_only", "research", "execute_confirm", "autopilot_safe"}
    if payload.mode not in allowed_modes:
        raise HTTPException(status_code=400, detail="Недопустимый режим запуска")

    qa_mode = _is_qa_request(request)
    run = store.create_run(
        project_id,
        payload.query_text,
        payload.mode,
        payload.parent_run_id,
        payload.purpose,
        meta={"intent": INTENT_ASK, "qa_mode": qa_mode, "intent_path": "pending"},
    )
    emit(
        run["id"],
        "run_created",
        "Запуск создан",
        {"project_id": project_id, "mode": run["mode"], "query_text": payload.query_text},
    )

    router = IntentRouter(qa_mode=qa_mode)
    settings = project.get("settings") or {}
    semantic_error_code: str | None = None
    if _is_fast_chat_candidate(payload.query_text, qa_mode=qa_mode):
        decision = IntentDecision(
            intent=INTENT_CHAT,
            confidence=0.55,
            reasons=["fast_chat_path"],
            questions=[],
            needs_clarification=False,
            act_hint=None,
            plan_hint=["CHAT_RESPONSE"],
            memory_item=None,
            response_style_hint=None,
            user_visible_note=None,
            decision_path="fast_chat_path",
        )
    else:
        try:
            decision = router.decide(payload.query_text, run_id=run["id"], settings=settings)
        except SemanticDecisionError as exc:
            semantic_error_code = exc.code
            emit(
                run["id"],
                "llm_request_failed",
                "Semantic decision failed",
                {
                    "provider": "local",
                    "model_id": None,
                    "error_type": exc.code,
                    "http_status_if_any": None,
                    "retry_count": 0,
                },
            )
            decision = _semantic_resilience_decision(exc.code)
        except Exception:  # noqa: BLE001
            semantic_error_code = "semantic_decision_unhandled_error"
            emit(
                run["id"],
                "llm_request_failed",
                "Semantic decision failed",
                {
                    "provider": "local",
                    "model_id": None,
                    "error_type": "semantic_decision_unhandled_error",
                    "http_status_if_any": None,
                    "retry_count": 0,
                },
            )
            decision = _semantic_resilience_decision(semantic_error_code)

    semantic_resilience = decision.decision_path == "semantic_resilience"
    fast_chat_path = decision.decision_path == "fast_chat_path"
    profile_memories = store.list_user_memories(limit=50)
    profile_context = build_user_profile_context(profile_memories)
    history = store.list_recent_chat_turns(run.get("parent_run_id"), limit_turns=12)
    tone_analysis = analyze_tone(payload.query_text, history, memories=profile_memories)
    memory_interpretation: dict[str, Any] | None = None
    memory_interpretation_error: str | None = None
    if semantic_resilience:
        memory_interpretation_error = "memory_interpreter_skipped_semantic_resilience"
    elif fast_chat_path:
        memory_interpretation_error = "memory_interpreter_skipped_fast_path"
    else:
        try:
            memory_interpretation = interpret_user_message_for_memory(
                payload.query_text,
                history,
                _known_profile_payload(profile_memories),
                brain=get_brain(),
                run_id=run["id"],
                settings=settings,
            )
        except MemoryInterpretationError as exc:
            memory_interpretation_error = exc.code
            emit(
                run["id"],
                "llm_request_failed",
                "Memory interpretation failed",
                {
                    "provider": "local",
                    "model_id": None,
                    "error_type": exc.code,
                    "http_status_if_any": None,
                    "retry_count": 0,
                },
            )
        except Exception:  # noqa: BLE001
            memory_interpretation_error = "memory_interpreter_unhandled_error"
            emit(
                run["id"],
                "llm_request_failed",
                "Memory interpretation failed",
                {
                    "provider": "local",
                    "model_id": None,
                    "error_type": "memory_interpreter_unhandled_error",
                    "http_status_if_any": None,
                    "retry_count": 0,
                },
            )

    interpreted_style_hint = _style_hint_from_interpretation(memory_interpretation)
    tone_style_hint = _style_hint_from_tone_analysis(tone_analysis)
    profile_style_hints = profile_context.get("style_hints") if isinstance(profile_context.get("style_hints"), list) else []
    profile_style_hint = " ".join(profile_style_hints[:3]) if profile_style_hints else None
    effective_response_style_hint = decision.response_style_hint or interpreted_style_hint or tone_style_hint or profile_style_hint
    interpreted_user_name = _name_from_interpretation(memory_interpretation)
    if not interpreted_user_name:
        profile_name = profile_context.get("user_name")
        if isinstance(profile_name, str) and profile_name.strip():
            interpreted_user_name = profile_name.strip()
    memory_payload = _memory_payload_from_interpretation(payload.query_text, memory_interpretation)
    tone_memory_payload = None
    if memory_payload is None and bool((tone_analysis or {}).get("self_improve")):
        tone_memory_payload = build_tone_profile_memory_payload(payload.query_text, tone_analysis, profile_memories)
    memory_payload = merge_memory_payloads(memory_payload, tone_memory_payload)

    selected_mode = "plan_only"
    selected_purpose = payload.purpose
    if decision.intent == INTENT_ACT:
        selected_mode = payload.mode
        if decision.act_hint and decision.act_hint.suggested_run_mode == "execute_confirm":
            selected_mode = "execute_confirm"
        if selected_mode not in allowed_modes:
            selected_mode = payload.mode
    elif decision.intent == INTENT_CHAT:
        selected_mode = "plan_only"
        selected_purpose = payload.purpose or "chat_only"
    elif decision.intent == INTENT_ASK:
        selected_mode = "plan_only"
        selected_purpose = payload.purpose or "clarify"

    meta = {
        "intent": decision.intent,
        "intent_confidence": decision.confidence,
        "intent_reasons": decision.reasons,
        "intent_questions": decision.questions,
        "needs_clarification": decision.needs_clarification,
        "qa_mode": qa_mode,
        "act_hint": decision.act_hint.to_dict() if decision.act_hint else None,
        "danger_flags": decision.act_hint.danger_flags if decision.act_hint else [],
        "suggested_run_mode": decision.act_hint.suggested_run_mode if decision.act_hint else None,
        "target": decision.act_hint.target if decision.act_hint else None,
        "intent_path": decision.decision_path,
        "plan_hint": decision.plan_hint,
        "memory_item": decision.memory_item,
        "memory_interpretation": memory_interpretation,
        "memory_interpretation_error": memory_interpretation_error,
        "response_style_hint": effective_response_style_hint,
        "tone_analysis": tone_analysis,
        "character_mode": tone_analysis.get("primary_mode") if isinstance(tone_analysis, dict) else None,
        "supporting_mode": tone_analysis.get("supporting_mode") if isinstance(tone_analysis, dict) else None,
        "mode_history": tone_analysis.get("mode_history") if isinstance(tone_analysis, dict) else None,
        "user_visible_note": decision.user_visible_note,
        "user_name": interpreted_user_name,
        "semantic_error_code": semantic_error_code,
    }
    updated = store.update_run_meta_and_mode(
        run["id"],
        mode=selected_mode,
        purpose=selected_purpose,
        meta=meta,
    )
    if not updated:
        raise HTTPException(status_code=500, detail="Не удалось обновить запуск после semantic decision")
    run = updated

    _emit_intent_decided(run["id"], decision, selected_mode)

    if decision.intent == INTENT_ACT:
        try:
            engine = _get_engine(request)
            plan_steps = engine.create_plan(run)
        except Exception as exc:  # noqa: BLE001
            store.update_run_status(run["id"], "failed")
            emit(run["id"], "run_failed", "Запуск завершён с ошибкой", {"error": str(exc)}, level="error")
            raise
        return {"kind": "act", "intent": decision.to_dict(), "run": run, "plan": plan_steps}

    if decision.intent == INTENT_CHAT:
        if semantic_resilience:
            fallback_error = semantic_error_code or "semantic_resilience"
            fallback_text = _chat_resilience_text(fallback_error)
            emit(
                run["id"],
                "chat_response_generated",
                "Ответ сформирован (degraded)",
                {
                    "provider": "local",
                    "model_id": None,
                    "latency_ms": None,
                    "text": fallback_text,
                    "degraded": True,
                    "error_type": fallback_error,
                    "http_status_if_any": None,
                },
            )
            _save_memory_payload_async(run, memory_payload, settings)
            return {"kind": "chat", "intent": decision.to_dict(), "run": run, "chat_response": fallback_text}

        brain = get_brain()
        ctx = SimpleNamespace(run=run, task={}, plan_step={}, settings=settings)
        memories = store.list_user_memories(limit=50)
        history = store.list_recent_chat_turns(run.get("parent_run_id"), limit_turns=CHAT_HISTORY_TURNS)
        tone_analysis = analyze_tone(payload.query_text, history, memories=memories)
        system_text = _build_chat_system_prompt(
            memories,
            effective_response_style_hint,
            user_message=payload.query_text,
            history=history,
            tone_analysis=tone_analysis,
        )
        llm_request = LLMRequest(
            purpose="chat_response",
            task_kind="chat",
            messages=build_chat_messages(system_text, history, payload.query_text),
            context_items=[ContextItem(content=payload.query_text, source_type="user_prompt", sensitivity="personal")],
            max_tokens=_chat_num_predict_default(),
            temperature=_chat_temperature_default(),
            top_p=_chat_top_p_default(),
            repeat_penalty=_chat_repeat_penalty_default(),
            run_id=run["id"],
        )
        fallback_text: str | None = None
        fallback_provider = "local"
        fallback_model_id = None
        fallback_latency_ms = None
        fallback_error_type: str | None = None
        fallback_http_status: int | None = None
        try:
            response = _call_chat_with_soft_retry(brain, llm_request, ctx)
        except Exception as exc:  # noqa: BLE001
            fallback_error_type = str(getattr(exc, "error_type", "chat_llm_unhandled_error"))
            fallback_http_status = getattr(exc, "status_code", None)
            fallback_provider = str(getattr(exc, "provider", "local") or "local")
            fallback_model_id = getattr(exc, "model_id", None)
            fallback_text = _chat_resilience_text(fallback_error_type)
            if fallback_error_type == "chat_llm_unhandled_error":
                emit(
                    run["id"],
                    "llm_request_failed",
                    "Chat LLM failed",
                    {
                        "provider": fallback_provider,
                        "model_id": fallback_model_id,
                        "error_type": fallback_error_type,
                        "http_status_if_any": fallback_http_status,
                        "retry_count": 0,
                    },
                )
        else:
            if response.status != "ok" or not (response.text or "").strip():
                fallback_error_type = response.error_type or "chat_empty_response"
                fallback_provider = response.provider or "local"
                fallback_model_id = response.model_id
                fallback_latency_ms = response.latency_ms
                fallback_text = _chat_resilience_text(fallback_error_type)

        if fallback_text is not None:
            if _should_auto_web_research(payload.query_text, fallback_text, error_type=fallback_error_type):
                researched = _run_auto_web_research(
                    run,
                    settings,
                    query_text=payload.query_text,
                    response_style_hint=effective_response_style_hint,
                )
                if researched is not None:
                    emit(
                        run["id"],
                        "chat_response_generated",
                        "Ответ сформирован (web research)",
                        {
                            "provider": "web_research",
                            "model_id": "web_research",
                            "latency_ms": researched.get("latency_ms"),
                            "text": researched.get("text"),
                            "degraded": False,
                            "sources_count": researched.get("sources_count"),
                            "confidence": researched.get("confidence"),
                        },
                    )
                    _save_memory_payload_async(run, memory_payload, settings)
                    return {
                        "kind": "chat",
                        "intent": decision.to_dict(),
                        "run": run,
                        "chat_response": researched.get("text"),
                    }
            emit(
                run["id"],
                "chat_response_generated",
                "Ответ сформирован (degraded)",
                {
                    "provider": fallback_provider,
                    "model_id": fallback_model_id,
                    "latency_ms": fallback_latency_ms,
                    "text": fallback_text,
                    "degraded": True,
                    "error_type": fallback_error_type,
                    "http_status_if_any": fallback_http_status,
                },
            )
            _save_memory_payload_async(run, memory_payload, settings)
            return {"kind": "chat", "intent": decision.to_dict(), "run": run, "chat_response": fallback_text}

        if _should_auto_web_research(payload.query_text, response.text or "", error_type=None):
            researched = _run_auto_web_research(
                run,
                settings,
                query_text=payload.query_text,
                response_style_hint=effective_response_style_hint,
            )
            if researched is not None:
                emit(
                    run["id"],
                    "chat_response_generated",
                    "Ответ сформирован (web research)",
                    {
                        "provider": "web_research",
                        "model_id": "web_research",
                        "latency_ms": researched.get("latency_ms"),
                        "text": researched.get("text"),
                        "degraded": False,
                        "sources_count": researched.get("sources_count"),
                        "confidence": researched.get("confidence"),
                    },
                )
                _save_memory_payload_async(run, memory_payload, settings)
                return {
                    "kind": "chat",
                    "intent": decision.to_dict(),
                    "run": run,
                    "chat_response": researched.get("text"),
                }

        emit(
            run["id"],
            "chat_response_generated",
            "Ответ сформирован",
            {
                "provider": response.provider,
                "model_id": response.model_id,
                "latency_ms": response.latency_ms,
                "text": response.text,
            },
        )
        _save_memory_payload_async(run, memory_payload, settings)
        return {"kind": "chat", "intent": decision.to_dict(), "run": run, "chat_response": response.text}

    if decision.intent == INTENT_ASK:
        emit(
            run["id"],
            "clarify_requested",
            "Запрошено уточнение",
            {"questions": decision.questions},
        )
        _save_memory_payload_async(run, memory_payload, settings)
        return {"kind": "clarify", "intent": decision.to_dict(), "run": run, "questions": decision.questions}

    raise HTTPException(status_code=500, detail="Intent routing failed")


@router.post("/runs/{run_id}/plan")
def create_plan(run_id: str, request: Request):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")

    engine = _get_engine(request)
    steps = engine.create_plan(run)
    return steps


@router.post("/runs/{run_id}/start")
def start_run(run_id: str, request: Request):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")

    engine = _get_engine(request)

    thread = threading.Thread(target=engine.start_run, args=(run_id,), daemon=True)
    thread.start()

    return {"status": "запущено"}


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, request: Request):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")

    engine = _get_engine(request)
    engine.cancel_run(run_id)
    return {"status": "отменено"}


@router.post("/runs/{run_id}/pause")
def pause_run(run_id: str, request: Request):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    engine = _get_engine(request)
    engine.pause_run(run_id)
    return {"status": "пауза"}


@router.post("/runs/{run_id}/resume")
def resume_run(run_id: str, request: Request):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    engine = _get_engine(request)
    engine.resume_run(run_id)
    return {"status": "возобновлено"}


@router.post("/runs/{run_id}/tasks/{task_id}/retry")
def retry_task(run_id: str, task_id: str, request: Request):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    task = store.get_task(task_id)
    if not task or task.get("run_id") != run_id:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    engine = _get_engine(request)
    thread = threading.Thread(target=engine.retry_task, args=(run_id, task_id), daemon=True)
    thread.start()
    return {"status": "повтор_запущен"}


@router.post("/runs/{run_id}/steps/{step_id}/retry")
def retry_step(run_id: str, step_id: str, request: Request):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    step = store.get_plan_step(step_id)
    if not step or step.get("run_id") != run_id:
        raise HTTPException(status_code=404, detail="Шаг плана не найден")
    engine = _get_engine(request)
    thread = threading.Thread(target=engine.retry_step, args=(run_id, step_id), daemon=True)
    thread.start()
    return {"status": "повтор_запущен"}


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    return run


@router.get("/runs/{run_id}/plan")
def get_plan(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    return store.list_plan_steps(run_id)


@router.get("/runs/{run_id}/tasks")
def get_tasks(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    return store.list_tasks(run_id)


@router.get("/runs/{run_id}/sources")
def get_sources(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    return store.list_sources(run_id)


@router.get("/runs/{run_id}/facts")
def get_facts(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    return store.list_facts(run_id)


@router.get("/runs/{run_id}/conflicts")
def get_conflicts(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    return store.list_conflicts(run_id)


@router.get("/runs/{run_id}/artifacts")
def get_artifacts(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    return store.list_artifacts(run_id)


@router.get("/runs/{run_id}/snapshot")
def get_snapshot(run_id: str):
    return _build_snapshot(run_id)


@router.get("/runs/{run_id}/snapshot/download")
def download_snapshot(run_id: str):
    snapshot = _build_snapshot(run_id)
    payload = json.dumps(snapshot, ensure_ascii=False)
    headers = {"Content-Disposition": f"attachment; filename=снимок_{run_id}.json"}
    return Response(payload, media_type="application/json", headers=headers)


@router.get("/runs/{run_id}/approvals")
def list_approvals(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    return store.list_approvals(run_id)


@router.post("/approvals/{approval_id}/approve")
def approve(approval_id: str, payload: ApprovalDecisionRequest | None = None):
    decision = payload.decision.model_dump(exclude_none=True) if payload and payload.decision else None
    approval = store.update_approval_status(approval_id, "approved", "user", decision=decision)
    if not approval:
        raise HTTPException(status_code=404, detail="Подтверждение не найдено")
    emit(
        approval["run_id"],
        "approval_approved",
        "Подтверждение принято",
        {"approval_id": approval_id, "decision": decision},
        task_id=approval["task_id"],
    )
    return approval


@router.post("/approvals/{approval_id}/reject")
def reject(approval_id: str):
    approval = store.update_approval_status(approval_id, "rejected", "user")
    if not approval:
        raise HTTPException(status_code=404, detail="Подтверждение не найдено")
    emit(
        approval["run_id"],
        "approval_rejected",
        "Подтверждение отклонено",
        {"approval_id": approval_id},
        task_id=approval["task_id"],
    )
    return approval


@router.post("/runs/{run_id}/conflicts/{conflict_id}/resolve")
def resolve_conflict(run_id: str, conflict_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    conflict = store.get_conflict(conflict_id)
    if not conflict:
        raise HTTPException(status_code=404, detail="Конфликт не найден")
    query_text = f"Разрешить конфликт по {conflict['fact_key']}"
    sub_run = store.create_run(run["project_id"], query_text, run["mode"], parent_run_id=run_id, purpose="conflict_resolution")
    emit(
        sub_run["id"],
        "run_created",
        "Запуск создан",
        {"project_id": run["project_id"], "mode": sub_run["mode"], "query_text": query_text},
    )
    return sub_run
