from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib import error, request

"""
Lightweight local adaptation inspired by AutoGen agentchat primitives:
- tmp/autogen_code/python/packages/autogen-agentchat/src/autogen_agentchat/agents/_assistant_agent.py
- tmp/autogen_code/python/packages/autogen-agentchat/src/autogen_agentchat/agents/_user_proxy_agent.py

No external dependencies are required.
"""

_CONVERSATION_TOKENS = (
    "поговор",
    "диалог",
    "обсуд",
    "чате",
    "chat",
    "conversation",
    "brainstorm",
    "вместе подумаем",
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower().replace("ё", "е"))


def _history_dialog_tail(history: list[dict[str, Any]], limit: int = 6) -> list[dict[str, str]]:
    tail: list[dict[str, str]] = []
    if not isinstance(history, list):
        return tail

    for item in history[-16:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        tail.append({"role": role, "content": content.strip()})
    return tail[-limit:]


def is_conversation_task(
    task: str,
    *,
    tone_analysis: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> bool:
    text = _normalized(task)
    if not text:
        return False

    token_hits = sum(1 for token in _CONVERSATION_TOKENS if token in text)
    words = [part for part in text.split(" ") if part]
    signals = tone_analysis.get("signals") if isinstance(tone_analysis, dict) else {}

    question = int(signals.get("question", 0)) if isinstance(signals, dict) else 0
    trust = int(signals.get("trust_language", 0)) if isinstance(signals, dict) else 0
    reflective = int(signals.get("reflective_cues", 0)) if isinstance(signals, dict) else 0
    uncertainty = int(signals.get("uncertainty", 0)) if isinstance(signals, dict) else 0

    score = 0
    score += 3 if token_hits >= 1 else 0
    score += 1 if token_hits >= 2 else 0
    score += 1 if question >= 1 else 0
    score += 1 if trust >= 1 else 0
    score += 1 if reflective >= 1 else 0
    score += 1 if uncertainty >= 1 and len(words) >= 6 else 0
    score += 1 if len(words) >= 10 else 0

    dialog_tail = _history_dialog_tail(history or [], limit=8)
    if dialog_tail:
        roles = {item["role"] for item in dialog_tail}
        if {"user", "assistant"}.issubset(roles):
            score += 1
        if len(dialog_tail) >= 4:
            score += 1

    return score >= 3


@dataclass(slots=True)
class AssistantAgent:
    name: str
    system_message: str

    def respond(self, user_message: str, *, context: dict[str, Any], adapter: "OllamaAdapter") -> str:
        history_tail = context.get("history_tail") if isinstance(context.get("history_tail"), list) else []
        history_block = "\n".join(
            f"- {item.get('role')}: {str(item.get('content') or '')[:180]}"
            for item in history_tail
            if isinstance(item, dict)
        )
        user_prompt = (
            f"Task:\n{context.get('task')}\n\n"
            f"Current turn:\n{user_message}\n\n"
            f"Recent dialog:\n{history_block or '- empty'}\n\n"
            "Provide concise, practical continuation for a multi-agent conversation."
        )
        return adapter.complete(system_prompt=self.system_message, user_prompt=user_prompt)


@dataclass(slots=True)
class UserProxyAgent:
    name: str

    def seed_message(self, task: str, context: dict[str, Any]) -> str:
        history_tail = context.get("history_tail") if isinstance(context.get("history_tail"), list) else []
        if history_tail:
            last = history_tail[-1]
            return f"{task}\nУточнение из диалога: {str(last.get('content') or '')[:200]}"
        return task

    def follow_up(self, assistant_message: str, *, round_index: int) -> str:
        if round_index == 0:
            return f"Ок, продолжай и выдели ключевые риски. База: {assistant_message[:180]}"
        if round_index == 1:
            return f"Теперь дай компактный план действий по пунктам. Основа: {assistant_message[:180]}"
        return "Заверши диалог коротким итогом и ближайшим шагом."


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
        raw = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/generate",
            data=raw,
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


def _heuristic_assistant_reply(
    user_message: str,
    *,
    round_index: int,
) -> str:
    if round_index == 0:
        return (
            "Вижу направление диалога. Сначала синхронизируем цель, затем разобьём её на 2-3"
            " смысловых трека и выберем критерий готовности."
        )
    if round_index == 1:
        return (
            "Риски: неясные требования, плавающий scope, отсутствие тест-критериев."
            " Сразу фиксируем assumptions и проверяем их коротким циклом."
        )
    return (
        "Итог: сформирован общий план разговора с рисками и next step."
        " Дальше можно перейти к реализации первого шага."
    )


def _summarize_turns(turns: list[dict[str, Any]]) -> str:
    assistant_lines = [
        str(item.get("message") or "").strip()
        for item in turns
        if str(item.get("speaker") or "").lower() == "assistantagent"
    ]
    snippets = [line[:180] for line in assistant_lines if line][:3]
    if not snippets:
        return "Conversation executed without assistant output."
    return "\n".join(f"- {item}" for item in snippets)


def autogen_chat(
    task: str,
    history: list[dict[str, Any]] | None,
    *,
    tone_analysis: dict[str, Any] | None = None,
    rounds: int = 2,
) -> dict[str, Any]:
    history = history if isinstance(history, list) else []
    tone_analysis = tone_analysis if isinstance(tone_analysis, dict) else {}

    conversation = is_conversation_task(
        task,
        tone_analysis=tone_analysis,
        history=history,
    )
    if not conversation:
        return {
            "mode": "single",
            "conversation": False,
            "executed": False,
            "rounds": 0,
            "agents": [],
            "turns": [],
            "summary": "AutoGen chat not engaged.",
        }

    assistant = AssistantAgent(
        name="AssistantAgent",
        system_message=(
            "You are a collaborative assistant in an AutoGen-style dialog. "
            "Be concise, practical, and move the conversation to action."
        ),
    )
    user_proxy = UserProxyAgent(name="UserProxyAgent")
    adapter = OllamaAdapter(
        base_url=os.getenv("ASTRA_OLLAMA_URL", "http://127.0.0.1:11434"),
        model=os.getenv("ASTRA_OLLAMA_MODEL", "llama2-uncensored:7b"),
        timeout_s=float(os.getenv("ASTRA_AUTOGEN_TIMEOUT_S", "6")),
        enabled=_env_bool("ASTRA_AUTOGEN_OLLAMA", _env_bool("ASTRA_OLLAMA_ENABLE", False)),
    )

    history_tail = _history_dialog_tail(history, limit=6)
    context = {
        "task": (task or "").strip(),
        "history_tail": history_tail,
    }

    turn_limit = max(1, min(int(rounds), 4))
    turns: list[dict[str, Any]] = []
    user_message = user_proxy.seed_message((task or "").strip(), context)
    executed = False

    for round_index in range(turn_limit):
        turns.append(
            {
                "speaker": user_proxy.name,
                "message": user_message,
            }
        )
        try:
            assistant_message = assistant.respond(
                user_message,
                context=context,
                adapter=adapter,
            )
            source = "ollama"
        except Exception:
            assistant_message = _heuristic_assistant_reply(
                user_message,
                round_index=round_index,
            )
            source = "heuristic"

        turns.append(
            {
                "speaker": assistant.name,
                "message": assistant_message.strip(),
                "source": source,
            }
        )
        executed = True
        user_message = user_proxy.follow_up(assistant_message, round_index=round_index)

    return {
        "mode": "conversation",
        "conversation": True,
        "executed": executed,
        "rounds": turn_limit,
        "agents": [user_proxy.name, assistant.name],
        "turns": turns[:10],
        "summary": _summarize_turns(turns),
    }


__all__ = [
    "AssistantAgent",
    "UserProxyAgent",
    "autogen_chat",
    "is_conversation_task",
]
