from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class ProviderResult:
    text: str
    usage: dict | None
    raw: dict


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, provider: str, status_code: int | None = None, error_type: str | None = None) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.error_type = error_type or "provider_error"


class LocalLLMProvider:
    def __init__(self, base_url: str, chat_model: str, code_model: str, timeout_s: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.chat_model = chat_model
        self.code_model = code_model
        self.timeout_s = timeout_s

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model_kind: str = "chat",
        temperature: float = 0.2,
        max_tokens: int | None = None,
        json_schema: dict | None = None,
        tools: list[dict] | None = None,
    ) -> ProviderResult:
        model = self.code_model if model_kind == "code" else self.chat_model
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = int(max_tokens)

        if json_schema or tools:
            payload["tools"] = tools or []
            payload["format"] = json_schema if json_schema else None

        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout_s,
            )
        except requests.RequestException as exc:
            raise ProviderError(f"Local LLM request failed: {exc}", provider="local", error_type="connection_error") from exc

        if resp.status_code >= 400:
            raise ProviderError(
                f"Local LLM HTTP {resp.status_code}",
                provider="local",
                status_code=resp.status_code,
                error_type="http_error",
            )

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise ProviderError("Local LLM returned invalid JSON", provider="local", status_code=resp.status_code, error_type="invalid_json") from exc

        message = data.get("message") or {}
        text = message.get("content") or ""
        usage = {
            "prompt_eval_count": data.get("prompt_eval_count"),
            "eval_count": data.get("eval_count"),
            "total_duration": data.get("total_duration"),
        }
        return ProviderResult(text=text, usage=usage, raw=data)


class CloudLLMProvider:
    def __init__(self, base_url: str, api_key: str, timeout_s: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        json_schema: dict | None = None,
        tools: list[dict] | None = None,
    ) -> ProviderResult:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)
        if json_schema:
            payload["response_format"] = {"type": "json_schema", "json_schema": json_schema}
        if tools:
            payload["tools"] = tools

        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout_s,
            )
        except requests.RequestException as exc:
            raise ProviderError(f"Cloud LLM request failed: {exc}", provider="cloud", error_type="connection_error") from exc

        if resp.status_code >= 400:
            raise ProviderError(
                f"Cloud LLM HTTP {resp.status_code}",
                provider="cloud",
                status_code=resp.status_code,
                error_type="http_error",
            )

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise ProviderError("Cloud LLM returned invalid JSON", provider="cloud", status_code=resp.status_code, error_type="invalid_json") from exc

        text = ""
        if "choices" in data:
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = data.get("usage")
        return ProviderResult(text=text, usage=usage, raw=data)
