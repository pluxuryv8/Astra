from __future__ import annotations

from typing import Any, Protocol

import requests


class LLMClient(Protocol):
    def chat(self, messages: list[dict[str, Any]], model: str | None = None, temperature: float = 0.2, json_schema: dict | None = None, tools: list[dict] | None = None) -> dict:
        ...


class LocalLLMClient:
    def __init__(self, base_url: str, model: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat(self, messages: list[dict[str, Any]], model: str | None = None, temperature: float = 0.2, json_schema: dict | None = None, tools: list[dict] | None = None) -> dict:
        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        if json_schema:
            payload["format"] = json_schema
        if tools:
            payload["tools"] = tools

        resp = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()


def build_llm_client(settings: dict) -> LLMClient:
    llm_settings = settings.get("llm") or settings.get("llm_local") or {}
    provider = str(llm_settings.get("provider") or "local").strip().lower()

    if provider not in {"local", "ollama"}:
        raise RuntimeError("Поддерживается только локальная LLM (Ollama)")

    base_url = llm_settings.get("base_url") or llm_settings.get("endpoint")
    if not base_url:
        raise RuntimeError("Не настроено")

    return LocalLLMClient(str(base_url), llm_settings.get("model"))
