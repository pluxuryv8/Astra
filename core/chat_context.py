from __future__ import annotations

import re

_SHORT_BREVITY_VALUES = {
    "short",
    "brief",
    "compact",
    "кратко",
    "коротко",
    "сжато",
}
_STRICT_TONE_VALUES = {
    "strict",
    "formal",
    "business",
    "строго",
    "строгий",
    "формально",
    "формальный",
    "деловой",
    "официальный",
    "официально",
    "сухой",
    "сухо",
}
_FRIENDLY_TONE_VALUES = {
    "friendly",
    "warm",
    "casual",
    "дружелюбно",
    "дружелюбный",
    "дружественно",
    "тепло",
    "мягко",
    "по-дружески",
}
_SUPPORTIVE_DIRECT_TONE_VALUES = {"supportive-direct"}
_CALM_SUPPORTIVE_TONE_VALUES = {"calm-supportive"}
_ENERGETIC_DIRECT_TONE_VALUES = {"energetic-direct"}


def _memory_meta(item: dict) -> dict:
    meta = item.get("meta")
    return meta if isinstance(meta, dict) else {}


def _summary_or_content(item: dict) -> str:
    meta = _memory_meta(item)
    summary = meta.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    content = item.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    title = item.get("title")
    if isinstance(title, str):
        return title.strip()
    return ""


def _extract_name_from_text(text: str) -> str | None:
    match = re.search(r"имя пользователя:\s*([A-Za-zА-Яа-яЁё-]{2,})", text, flags=re.IGNORECASE)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def _extract_name_from_memories(memories: list[dict]) -> str | None:
    for item in memories:
        meta = _memory_meta(item)
        facts = meta.get("facts")
        if isinstance(facts, list):
            for fact in facts:
                if not isinstance(fact, dict):
                    continue
                key = fact.get("key")
                value = fact.get("value")
                if key == "user.name" and isinstance(value, str) and value.strip():
                    return value.strip()
        text = _summary_or_content(item)
        if text:
            fallback = _extract_name_from_text(text)
            if fallback:
                return fallback
    return None


def style_hint_from_preference(key: str, value: str) -> str | None:
    key_norm = key.strip().lower()
    value_clean = value.strip()
    value_norm = re.sub(r"\s+", " ", value_clean.lower().replace("ё", "е"))
    if not value_clean:
        return None

    if key_norm == "style.brevity":
        if value_norm in _SHORT_BREVITY_VALUES:
            return "Отвечай коротко и по делу."
        return f"Уровень краткости: {value_clean}."

    if key_norm == "style.tone":
        if value_norm in _STRICT_TONE_VALUES:
            return "Стиль: строгий и точный, без лишней разговорности."
        if value_norm in _FRIENDLY_TONE_VALUES:
            return "Стиль: дружелюбный и поддерживающий."
        if value_norm in _SUPPORTIVE_DIRECT_TONE_VALUES:
            return "Тон ответа: поддерживающий и прямой."
        if value_norm in _CALM_SUPPORTIVE_TONE_VALUES:
            return "Тон ответа: спокойный и поддерживающий."
        if value_norm in _ENERGETIC_DIRECT_TONE_VALUES:
            return "Тон ответа: энергичный и прямой."
        return f"Тон ответа: {value_clean}."

    if key_norm == "style.mirror_level" and value_norm in {"low", "medium", "high"}:
        if value_norm == "low":
            return "Зеркалинг минимальный: акцент на точность."
        if value_norm == "high":
            return "Зеркалинг высокий: адаптируй ритм и лексику."
        return "Зеркалинг умеренный: деловой и человечный баланс."

    if key_norm == "user.addressing.preference":
        return f"Формат обращения к пользователю: {value_clean}."

    if key_norm == "response.format":
        return f"Формат ответа: {value_clean}."

    return None


def _style_hints_from_memories(memories: list[dict], limit: int = 4) -> list[str]:
    hints: list[str] = []
    seen: set[str] = set()
    for item in memories:
        meta = _memory_meta(item)
        preferences = meta.get("preferences")
        if not isinstance(preferences, list):
            continue
        for pref in preferences:
            if not isinstance(pref, dict):
                continue
            key = pref.get("key")
            value = pref.get("value")
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            hint = style_hint_from_preference(key, value)
            if not hint:
                continue

            if hint in seen:
                continue
            seen.add(hint)
            hints.append(hint)
            if len(hints) >= limit:
                return hints
    return hints


def build_profile_block(memories: list[dict], max_items: int = 12, max_chars: int = 1200) -> str | None:
    lines: list[str] = []
    total = 0
    for item in memories[:max_items]:
        content = _summary_or_content(item)
        if not content:
            continue
        content = " ".join(content.split())
        if len(content) > 220:
            content = content[:217] + "..."
        line = f"- {content}"
        if total + len(line) + 1 > max_chars:
            break
        lines.append(line)
        total += len(line) + 1
    if not lines:
        return None
    return "\n".join(lines)


def build_memory_dump_response(memories: list[dict], max_items: int = 20, max_chars: int = 1500) -> str:
    block = build_profile_block(memories, max_items=max_items, max_chars=max_chars)
    if not block:
        return "Пока ничего не помню о тебе. Можешь рассказать, как тебя называть или как тебе удобнее отвечать."
    return "Вот что я помню о тебе:\n" + block


def build_user_profile_context(memories: list[dict]) -> dict:
    return {
        "profile_block": build_profile_block(memories),
        "user_name": _extract_name_from_memories(memories),
        "style_hints": _style_hints_from_memories(memories),
    }


def build_chat_messages(system_text: str, history: list[dict], user_text: str) -> list[dict]:
    messages: list[dict] = [{"role": "system", "content": system_text}]
    for item in history:
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_text})
    return messages
