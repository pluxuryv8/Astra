from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import core.intent_router as intent_router
from apps.api.main import create_app
from apps.api.routes import runs as runs_route
from core.assistant_phrases import contains_rude_words
from core.brain.types import LLMResponse
from core.semantic.decision import SemanticDecision
from memory import store


class _GoldenBrain:
    def __init__(self, responses: dict[str, str]) -> None:
        self._responses = dict(responses)
        self.calls: list[Any] = []

    def call(self, request, ctx=None):  # noqa: ANN001, ANN002
        self.calls.append(request)
        user_text = ""
        for message in reversed(request.messages or []):
            if str(message.get("role", "")).strip().lower() != "user":
                continue
            content = message.get("content")
            if isinstance(content, str):
                user_text = content.strip()
            break

        text = self._responses.get(user_text, "Краткий итог: нет ответа.")
        return LLMResponse(
            text=text,
            usage=None,
            provider="local",
            model_id="golden-fake",
            latency_ms=3,
            cache_hit=False,
            route_reason="golden",
            status="ok",
            error_type=None,
        )


def _init_store(tmp_path: Path) -> None:
    os.environ["ASTRA_DATA_DIR"] = str(tmp_path)
    os.environ["ASTRA_CHAT_FAST_PATH_ENABLED"] = "false"
    os.environ["ASTRA_CHAT_AUTO_WEB_RESEARCH_ENABLED"] = "false"
    store.reset_for_tests()
    store.init(tmp_path, ROOT / "memory" / "migrations")


def _load_auth_token() -> str | None:
    data_dir = Path(os.environ.get("ASTRA_DATA_DIR", ROOT / ".astra"))
    token_path = data_dir / "auth.token"
    if not token_path.exists():
        return None
    token = token_path.read_text(encoding="utf-8").strip()
    return token or None


def _bootstrap(client: TestClient, token: str = "test-token") -> dict[str, str]:
    file_token = _load_auth_token()
    effective_token = file_token or token
    res = client.post("/api/v1/auth/bootstrap", json={"token": effective_token})
    if res.status_code == 409 and file_token:
        effective_token = file_token
    return {"Authorization": f"Bearer {effective_token}"}


def _semantic_chat_decision() -> SemanticDecision:
    return SemanticDecision(
        intent="CHAT",
        confidence=0.95,
        memory_item=None,
        plan_hint=[],
        response_style_hint=None,
        user_visible_note=None,
        raw={},
    )


def _memory_interpretation_stub() -> dict[str, Any]:
    return {
        "should_store": False,
        "confidence": 0.2,
        "facts": [],
        "preferences": [],
        "title": "Профиль пользователя",
        "summary": "",
        "possible_facts": [],
    }


def _extract_numbered_steps(text: str) -> list[tuple[int, str]]:
    items: list[tuple[int, str]] = []
    for match in re.finditer(r"(?m)^\s*(\d+)[.)]\s+(.+)$", text):
        items.append((int(match.group(1)), match.group(2).strip()))
    return items


def _assert_steps_quality(text: str) -> None:
    steps = _extract_numbered_steps(text)
    assert len(steps) >= 3, text
    assert steps[0][0] == 1, text
    numbers = [num for num, _ in steps]
    assert numbers == list(range(1, len(numbers) + 1)), text
    for _num, body in steps:
        assert len(body) >= 20, text
        assert not contains_rude_words(body), text


def test_golden_complex_chat_cases_are_structured_and_clean(monkeypatch, tmp_path: Path):
    _init_store(tmp_path)

    cases = [
        {
            "query": "Составь подробный план тренировок на месяц с этапами, рисками и метриками прогресса.",
            "raw_answer": (
                "<think>черновик</think>\n"
                "Краткий итог: За 12 недель можно начать устойчивое снижение веса без экстремальных мер.\n\n"
                "1. Сначала рассчитай дневную норму калорий и выставь дефицит 15%.\n"
                "2. Запланируй 3 силовые тренировки и 2 кардио-сессии в неделю.\n"
                "3. Каждое воскресенье фиксируй вес, талию и среднюю активность за неделю.\n"
                "###!!!###"
            ),
            "must_have": ["дефицит", "тренировки", "фиксируй"],
        },
        {
            "query": "Сделай пошаговый план миграции API с монолита на микросервисы с контролем рисков.",
            "raw_answer": (
                "Final answer: Краткий итог: Миграцию делаем волнами, чтобы не ломать прод.\n"
                "1. Зафиксируй текущие API-контракты и базовые метрики ошибок/латентности.\n"
                "2. Выдели первый сервис вокруг одного bounded context и настрой обратную совместимость.\n"
                "2. Выдели первый сервис вокруг одного bounded context и настрой обратную совместимость.\n"
                "3. Включай трафик через canary и расширяй долю после зелёных метрик."
            ),
            "must_have": ["контракты", "canary", "метрик"],
        },
        {
            "query": "Составь детальный антикризисный план на 14 дней с приоритетами и контролем выполнения.",
            "raw_answer": (
                "Краткий итог: Нужен короткий антикризисный план на 14 дней.\n"
                "Ты дебил, если этого не понимаешь.\n"
                "1. Заморозь необязательные расходы и зафиксируй обязательные платежи.\n"
                "2. Договорись о переносе сроков с двумя ключевыми кредиторами.\n"
                "3. Обновляй cash-flow ежедневно и корректируй лимиты."
            ),
            "must_have": ["расход", "кредитор", "cash-flow"],
        },
    ]

    brain = _GoldenBrain({item["query"]: item["raw_answer"] for item in cases})
    monkeypatch.setattr(runs_route, "get_brain", lambda: brain)
    monkeypatch.setattr(
        runs_route,
        "interpret_user_message_for_memory",
        lambda *args, **kwargs: _memory_interpretation_stub(),
    )
    monkeypatch.setattr(
        intent_router,
        "decide_semantic",
        lambda *args, **kwargs: _semantic_chat_decision(),
    )

    client = TestClient(create_app())
    headers = _bootstrap(client)
    project = client.post("/api/v1/projects", json={"name": "golden-complex-chat", "tags": [], "settings": {}}, headers=headers).json()
    project_id = project["id"]

    for case in cases:
        response = client.post(
            f"/api/v1/projects/{project_id}/runs",
            json={"query_text": case["query"], "mode": "plan_only"},
            headers=headers,
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["kind"] == "chat"

        clean = str(payload.get("chat_response") or "")
        clean_lower = clean.lower()
        assert clean.startswith("Краткий итог:"), clean
        assert "<think>" not in clean_lower, clean
        assert "final answer" not in clean_lower, clean
        assert "###!!!###" not in clean, clean
        assert not contains_rude_words(clean_lower), clean

        for token in case["must_have"]:
            assert token in clean_lower, clean

        _assert_steps_quality(clean)

        run_snapshot = store.get_run(payload["run"]["id"])
        runtime_metrics = (run_snapshot or {}).get("meta", {}).get("runtime_metrics", {})
        assert runtime_metrics.get("chat_response_mode") == "step_by_step_plan"
        assert runtime_metrics.get("chat_inference_profile") == "complex"

