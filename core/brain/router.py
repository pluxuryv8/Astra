from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Iterable

from core.brain.providers import LocalLLMProvider, ProviderError
from core.brain.types import LLMRequest, LLMResponse
from core.event_bus import emit
from core.llm_routing import (
    ROUTE_LOCAL,
    ContextItem,
    PolicyFlags,
    decide_route,
)


@dataclass
class BrainConfig:
    local_base_url: str
    local_chat_model: str
    local_chat_fast_model: str | None
    local_chat_complex_model: str | None
    local_code_model: str
    local_timeout_s: int
    local_ollama_num_ctx: int
    local_ollama_num_predict: int
    local_fast_query_max_chars: int
    local_fast_query_max_words: int
    local_complex_query_min_chars: int
    local_complex_query_min_words: int
    max_concurrency: int
    chat_priority_extra_slots: int
    chat_tier_timeout_s: int
    budget_per_run: int | None
    budget_per_step: int | None

    @classmethod
    def from_env(cls) -> "BrainConfig":
        def _env_int(name: str, default: int | None) -> int | None:
            raw = os.getenv(name)
            if raw is None:
                return default
            try:
                return int(raw)
            except ValueError:
                return default

        def _env_str(name: str, default: str | None = None) -> str | None:
            raw = os.getenv(name)
            if raw is None:
                return default
            value = raw.strip()
            return value or default

        return cls(
            local_base_url=os.getenv("ASTRA_LLM_LOCAL_BASE_URL", "http://127.0.0.1:11434"),
            local_chat_model=os.getenv("ASTRA_LLM_LOCAL_CHAT_MODEL", "llama2-uncensored:7b"),
            local_chat_fast_model=_env_str("ASTRA_LLM_LOCAL_CHAT_MODEL_FAST", "llama2-uncensored:7b"),
            local_chat_complex_model=_env_str(
                "ASTRA_LLM_LOCAL_CHAT_MODEL_COMPLEX",
                "wizardlm-uncensored:13b",
            ),
            local_code_model=os.getenv("ASTRA_LLM_LOCAL_CODE_MODEL", "deepseek-coder-v2:16b-lite-instruct-q8_0"),
            local_timeout_s=max(1, _env_int("ASTRA_LLM_LOCAL_TIMEOUT_S", 30) or 30),
            local_ollama_num_ctx=max(1024, _env_int("ASTRA_LLM_OLLAMA_NUM_CTX", 4096) or 4096),
            local_ollama_num_predict=max(64, _env_int("ASTRA_LLM_OLLAMA_NUM_PREDICT", 256) or 256),
            local_fast_query_max_chars=max(20, _env_int("ASTRA_LLM_FAST_QUERY_MAX_CHARS", 120) or 120),
            local_fast_query_max_words=max(3, _env_int("ASTRA_LLM_FAST_QUERY_MAX_WORDS", 18) or 18),
            local_complex_query_min_chars=max(40, _env_int("ASTRA_LLM_COMPLEX_QUERY_MIN_CHARS", 260) or 260),
            local_complex_query_min_words=max(8, _env_int("ASTRA_LLM_COMPLEX_QUERY_MIN_WORDS", 45) or 45),
            max_concurrency=_env_int("ASTRA_LLM_MAX_CONCURRENCY", 1) or 1,
            chat_priority_extra_slots=max(0, _env_int("ASTRA_LLM_CHAT_PRIORITY_EXTRA_SLOTS", 1) or 0),
            chat_tier_timeout_s=max(5, _env_int("ASTRA_LLM_CHAT_TIER_TIMEOUT_S", 20) or 20),
            budget_per_run=_env_int("ASTRA_LLM_BUDGET_PER_RUN", None),
            budget_per_step=_env_int("ASTRA_LLM_BUDGET_PER_STEP", None),
        )


class BrainQueue:
    def __init__(self, max_concurrency: int, *, chat_priority_extra_slots: int = 0) -> None:
        self.max_concurrency = max(1, int(max_concurrency))
        self.chat_priority_extra_slots = max(0, int(chat_priority_extra_slots))
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._chat_queue: deque[object] = deque()
        self._default_queue: deque[object] = deque()
        self._token_is_chat: dict[object, bool] = {}
        self._inflight = 0

    def _can_acquire(self, token: object) -> bool:
        is_chat = self._token_is_chat.get(token, False)
        if is_chat:
            if not self._chat_queue or self._chat_queue[0] is not token:
                return False
            max_for_chat = self.max_concurrency + self.chat_priority_extra_slots
            return self._inflight < max_for_chat

        if self._chat_queue:
            return False
        if not self._default_queue or self._default_queue[0] is not token:
            return False
        return self._inflight < self.max_concurrency

    def acquire(self, *, prioritize_chat: bool = False):
        token = object()
        with self._condition:
            self._token_is_chat[token] = prioritize_chat
            if prioritize_chat:
                self._chat_queue.append(token)
            else:
                self._default_queue.append(token)
            while not self._can_acquire(token):
                self._condition.wait()
            if prioritize_chat:
                self._chat_queue.popleft()
            else:
                self._default_queue.popleft()
            self._token_is_chat.pop(token, None)
            self._inflight += 1
        return token

    def release(self, token: object) -> None:
        with self._condition:
            self._inflight = max(0, self._inflight - 1)
            self._condition.notify_all()


class BrainRouter:
    def __init__(self, config: BrainConfig | None = None) -> None:
        self.config = config or BrainConfig.from_env()
        self.queue = BrainQueue(
            self.config.max_concurrency,
            chat_priority_extra_slots=self.config.chat_priority_extra_slots,
        )
        self._cache: dict[str, dict[str, LLMResponse]] = {}
        self._run_counts: dict[str, int] = {}
        self._step_counts: dict[tuple[str, str], int] = {}
        self._local_failures: dict[tuple[str, str], int] = {}

    def call(self, request: LLMRequest, ctx=None) -> LLMResponse:
        run_id = request.run_id or (ctx.run.get("id") if ctx else None)
        task_id = request.task_id or (ctx.task.get("id") if ctx else None)
        step_id = request.step_id or (ctx.plan_step.get("id") if ctx else None)

        if self._is_qa_mode(ctx):
            model_id = "qa_stub"
            self._emit(
                run_id,
                "llm_route_decided",
                "LLM route decided",
                {
                    "route": ROUTE_LOCAL,
                    "reason": "qa_mode",
                    "provider": "local",
                    "model_id": model_id,
                    "items_summary_by_source_type": self._items_summary_by_source(request.context_items or []),
                },
                task_id=task_id,
                step_id=step_id,
            )
            self._emit(
                run_id,
                "llm_request_started",
                "LLM request started",
                {"provider": "local", "model_id": model_id},
                task_id=task_id,
                step_id=step_id,
            )
            response = LLMResponse(
                text=self._qa_response(request),
                usage=None,
                provider="local",
                model_id=model_id,
                latency_ms=0,
                cache_hit=True,
                route_reason="qa_mode",
            )
            self._emit(
                run_id,
                "llm_request_succeeded",
                "LLM request succeeded",
                {
                    "provider": response.provider,
                    "model_id": response.model_id,
                    "latency_ms": response.latency_ms,
                    "usage_if_available": response.usage,
                    "cache_hit": True,
                },
                task_id=task_id,
                step_id=step_id,
            )
            return response

        policy_flags = PolicyFlags.from_settings(ctx.settings if ctx else {})

        context_items = request.context_items or []
        decision = decide_route(request.purpose, context_items, policy_flags)

        route = decision.route
        route_reason = decision.reason

        if decision.reason in ("telegram_text_present", "strict_local"):
            route = ROUTE_LOCAL
            route_reason = decision.reason

        provider_name = "local"
        model_id = self._select_model(route, request, ctx)

        final_items = context_items

        items_summary = self._items_summary_by_source(context_items)
        self._emit(
            run_id,
            "llm_route_decided",
            "LLM route decided",
            {
                "route": route,
                "reason": route_reason,
                "provider": provider_name,
                "model_id": model_id,
                "items_summary_by_source_type": items_summary,
            },
            task_id=task_id,
            step_id=step_id,
        )

        messages = self._build_messages(request, final_items)
        cache_key = self._cache_key(route, model_id, request, messages)
        cached = self._cache_get(run_id, cache_key)
        if cached:
            self._emit(
                run_id,
                "llm_request_started",
                "LLM request started",
                {"provider": cached.provider, "model_id": cached.model_id},
                task_id=task_id,
                step_id=step_id,
            )
            self._emit(
                run_id,
                "llm_request_succeeded",
                "LLM request succeeded",
                {
                    "provider": cached.provider,
                    "model_id": cached.model_id,
                    "latency_ms": 0,
                    "usage_if_available": cached.usage,
                    "cache_hit": True,
                },
                task_id=task_id,
                step_id=step_id,
            )
            return cached

        if run_id:
            budget = self._check_budget(run_id, step_id)
            if budget is not None:
                budget_name, limit, current = budget
                self._emit(
                    run_id,
                    "llm_budget_exceeded",
                    "LLM budget exceeded",
                    {
                        "budget_name": budget_name,
                        "limit": limit,
                        "current": current,
                    },
                    task_id=task_id,
                    step_id=step_id,
                )
                return LLMResponse(
                    text="",
                    usage=None,
                    provider=provider_name,
                    model_id=model_id,
                    latency_ms=0,
                    cache_hit=False,
                    route_reason=route_reason,
                    status="budget_exceeded",
                    error_type="budget_exceeded",
                )

        prioritize_chat = request.purpose == "chat_response" and request.preferred_model_kind == "chat"
        token = self.queue.acquire(prioritize_chat=prioritize_chat)
        start = time.time()
        try:
            self._emit(
                run_id,
                "llm_request_started",
                "LLM request started",
                {"provider": provider_name, "model_id": model_id},
                task_id=task_id,
                step_id=step_id,
            )

            result = self._call_local(messages, request, model_id)
            response = LLMResponse(
                text=result.text,
                usage=result.usage,
                provider="local",
                model_id=result.model_id or model_id,
                latency_ms=int((time.time() - start) * 1000),
                cache_hit=False,
                route_reason=route_reason,
                raw=result.raw,
            )
            self._note_local_result(run_id, request.preferred_model_kind, response)

            self._emit(
                run_id,
                "llm_request_succeeded",
                "LLM request succeeded",
                {
                    "provider": response.provider,
                    "model_id": response.model_id,
                    "latency_ms": response.latency_ms,
                    "usage_if_available": response.usage,
                    "cache_hit": response.cache_hit,
                },
                task_id=task_id,
                step_id=step_id,
            )

            self._cache_set(run_id, cache_key, response)
            self._increment_budget(run_id, step_id)
            return response
        except ProviderError as exc:
            self._emit(
                run_id,
                "llm_request_failed",
                "LLM request failed",
                {
                    "provider": exc.provider,
                    "model_id": model_id,
                    "error_type": exc.error_type,
                    "http_status_if_any": exc.status_code,
                    "retry_count": getattr(exc, "retry_count", 0),
                },
                task_id=task_id,
                step_id=step_id,
            )
            if exc.provider == "local" and exc.artifact_path:
                self._emit(
                    run_id,
                    "local_llm_http_error",
                    "Local LLM HTTP error",
                    {
                        "status": exc.status_code,
                        "model_id": model_id,
                        "artifact_path": exc.artifact_path,
                    },
                    task_id=task_id,
                    step_id=step_id,
                )
            if route == ROUTE_LOCAL:
                self._note_local_failure(run_id, request.preferred_model_kind)
            raise
        finally:
            self.queue.release(token)

    def _call_local(self, messages: list[dict[str, Any]], request: LLMRequest, model_id: str) -> Any:
        provider = LocalLLMProvider(
            self.config.local_base_url,
            self.config.local_chat_model,
            self.config.local_code_model,
            timeout_s=self.config.local_timeout_s,
            default_num_ctx=self.config.local_ollama_num_ctx,
            default_num_predict=self.config.local_ollama_num_predict,
        )
        timeout_override: int | None = None
        if (
            request.preferred_model_kind == "chat"
            and request.purpose == "chat_response"
            and model_id != self.config.local_chat_model
        ):
            timeout_override = max(5, min(self.config.local_timeout_s, self.config.chat_tier_timeout_s))
        try:
            return provider.chat(
                messages,
                model=model_id,
                model_kind=request.preferred_model_kind,
                temperature=request.temperature,
                top_p=request.top_p,
                repeat_penalty=request.repeat_penalty,
                max_tokens=request.max_tokens,
                json_schema=request.json_schema,
                tools=request.tools,
                run_id=request.run_id,
                step_id=request.step_id,
                purpose=request.purpose,
                timeout_s=timeout_override,
            )
        except ProviderError as exc:
            # Tiered chat model can be absent/unstable locally; fall back to base chat model.
            if (
                request.preferred_model_kind == "chat"
                and model_id != self.config.local_chat_model
                and exc.error_type in {"model_not_found", "connection_error", "http_error", "invalid_json"}
            ):
                fallback_timeout_s = max(5, min(self.config.local_timeout_s, max(self.config.chat_tier_timeout_s, 35)))
                return provider.chat(
                    messages,
                    model=self.config.local_chat_model,
                    model_kind=request.preferred_model_kind,
                    temperature=request.temperature,
                    top_p=request.top_p,
                    repeat_penalty=request.repeat_penalty,
                    max_tokens=request.max_tokens,
                    json_schema=request.json_schema,
                    tools=request.tools,
                    run_id=request.run_id,
                    step_id=request.step_id,
                    purpose=request.purpose,
                    timeout_s=fallback_timeout_s,
                )
            raise

    def _make_response(
        self,
        *,
        text: str,
        provider: str,
        model_id: str,
        start_time: float,
        usage: dict | None = None,
        cache_hit: bool = False,
        route_reason: str = "local",
        raw: dict | None = None,
        retry_count: int = 0,
    ) -> LLMResponse:
        return LLMResponse(
            text=text,
            usage=usage,
            provider=provider,
            model_id=model_id,
            latency_ms=int((time.time() - start_time) * 1000),
            cache_hit=cache_hit,
            route_reason=route_reason,
            raw=raw,
            retry_count=retry_count,
        )

    def _build_messages(self, request: LLMRequest, items: list[ContextItem]) -> list[dict[str, Any]]:
        if request.render_messages:
            return request.render_messages(items)
        if request.messages:
            return request.messages
        raise ValueError("LLMRequest requires messages or render_messages")

    def _select_model(self, route: str, request: LLMRequest, ctx) -> str:
        if request.preferred_model_kind == "code":
            return self.config.local_code_model
        return self._select_local_chat_model(request)

    def _select_local_chat_model(self, request: LLMRequest) -> str:
        base_model = self.config.local_chat_model
        if request.preferred_model_kind != "chat":
            return base_model
        if request.purpose != "chat_response":
            return base_model

        query = self._last_user_message(request.messages)
        if not query:
            return base_model

        if self._is_fast_chat_query(query):
            return self.config.local_chat_fast_model or base_model
        if self._is_complex_chat_query(query):
            return self.config.local_chat_complex_model or base_model
        return base_model

    def _last_user_message(self, messages: list[dict[str, Any]] | None) -> str:
        if not messages:
            return ""
        for message in reversed(messages):
            if str(message.get("role", "")).strip().lower() != "user":
                continue
            content = message.get("content", "")
            if isinstance(content, str):
                return content.strip()
            try:
                return json.dumps(content, ensure_ascii=False)
            except Exception:
                return str(content)
        return ""

    def _is_fast_chat_query(self, query: str) -> bool:
        normalized = query.strip()
        if not normalized:
            return False
        words = [word for word in re.split(r"\s+", normalized) if word]
        lowered = normalized.lower()

        if len(normalized) > self.config.local_fast_query_max_chars:
            return False
        if len(words) > self.config.local_fast_query_max_words:
            return False
        if "\n" in normalized or "```" in normalized:
            return False
        if re.search(r"\b(код|code|python|javascript|sql|regex|архитект|пошаг|подроб|сравни|анализ)\b", lowered):
            return False
        return True

    def _is_complex_chat_query(self, query: str) -> bool:
        normalized = query.strip()
        if not normalized:
            return False
        words = [word for word in re.split(r"\s+", normalized) if word]
        lowered = normalized.lower()

        if len(normalized) >= self.config.local_complex_query_min_chars:
            return True
        if len(words) >= self.config.local_complex_query_min_words:
            return True
        if "```" in normalized:
            return True
        if re.search(r"\b(архитект|план|сравни|объясни|деталь|подроб|анализ|формул|доказ|рефактор)\b", lowered):
            return True
        return False

    def _items_length(self, items: Iterable[ContextItem]) -> int:
        total = 0
        for item in items:
            if isinstance(item.content, str):
                total += len(item.content)
            else:
                total += len(json.dumps(item.content, ensure_ascii=False))
        return total

    def _items_summary_by_source(self, items: Iterable[ContextItem]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            counts[item.source_type] = counts.get(item.source_type, 0) + 1
        return counts

    def _cache_key(self, route: str, model_id: str, request: LLMRequest, messages: list[dict[str, Any]]) -> str:
        payload = {
            "route": route,
            "model": model_id,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "repeat_penalty": request.repeat_penalty,
            "max_tokens": request.max_tokens,
            "messages": messages,
            "json_schema": request.json_schema,
            "tools": request.tools,
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _cache_get(self, run_id: str | None, key: str) -> LLMResponse | None:
        if not run_id:
            return None
        cached = self._cache.get(run_id, {}).get(key)
        if not cached:
            return None
        return LLMResponse(
            text=cached.text,
            usage=cached.usage,
            provider=cached.provider,
            model_id=cached.model_id,
            latency_ms=0,
            cache_hit=True,
            route_reason=cached.route_reason,
            status=cached.status,
            error_type=cached.error_type,
            http_status=cached.http_status,
            retry_count=cached.retry_count,
            raw=cached.raw,
        )

    def _cache_set(self, run_id: str | None, key: str, response: LLMResponse) -> None:
        if not run_id:
            return
        self._cache.setdefault(run_id, {})[key] = response

    def _check_budget(self, run_id: str, step_id: str | None) -> tuple[str, int, int] | None:
        if self.config.budget_per_run is not None:
            current_run = self._run_counts.get(run_id, 0)
            if current_run >= self.config.budget_per_run:
                return ("per_run", self.config.budget_per_run, current_run)
        if step_id and self.config.budget_per_step is not None:
            current_step = self._step_counts.get((run_id, step_id), 0)
            if current_step >= self.config.budget_per_step:
                return ("per_step", self.config.budget_per_step, current_step)
        return None

    def _increment_budget(self, run_id: str | None, step_id: str | None) -> None:
        if not run_id:
            return
        self._run_counts[run_id] = self._run_counts.get(run_id, 0) + 1
        if step_id:
            key = (run_id, step_id)
            self._step_counts[key] = self._step_counts.get(key, 0) + 1

    def _note_local_failure(self, run_id: str | None, kind: str) -> None:
        key = (run_id or "", kind)
        self._local_failures[key] = self._local_failures.get(key, 0) + 1

    def _note_local_result(self, run_id: str | None, kind: str, response: LLMResponse) -> None:
        key = (run_id or "", kind)
        if not response.text.strip():
            self._local_failures[key] = self._local_failures.get(key, 0) + 1
        else:
            self._local_failures[key] = 0

    def _emit(self, run_id: str | None, event_type: str, message: str, payload: dict[str, Any], *, task_id: str | None, step_id: str | None) -> None:
        if not run_id:
            return
        emit(run_id, event_type, message, payload, task_id=task_id, step_id=step_id)

    def _is_qa_mode(self, ctx) -> bool:
        raw = os.getenv("ASTRA_QA_MODE")
        if raw and raw.strip().lower() in {"1", "true", "yes", "on"}:
            return True
        if ctx and getattr(ctx, "run", None):
            meta = ctx.run.get("meta") or {}
            return bool(meta.get("qa_mode"))
        return False

    def _qa_response(self, request: LLMRequest) -> str:
        if request.json_schema:
            return "{\"qa_mode\": true}"
        if request.messages:
            return "QA mode: response stub."
        return "QA mode"


_BRAIN_SINGLETON: BrainRouter | None = None


def get_brain() -> BrainRouter:
    global _BRAIN_SINGLETON
    if _BRAIN_SINGLETON is None:
        _BRAIN_SINGLETON = BrainRouter()
    return _BRAIN_SINGLETON
