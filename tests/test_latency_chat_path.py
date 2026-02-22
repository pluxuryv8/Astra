from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import core.intent_router as intent_router
from apps.api.main import create_app
from apps.api.routes import runs as runs_route
from core.brain.types import LLMResponse
from core.semantic.decision import SemanticDecision
from memory import store


class _LatencyBrain:
    _PROFILE_DELAY_MS = {
        "fast": 14,
        "balanced": 28,
        "complex": 52,
    }

    def call(self, request, ctx=None):  # noqa: ANN001, ANN002
        metadata = request.metadata if isinstance(request.metadata, dict) else {}
        profile = str(metadata.get("chat_inference_profile") or "balanced")
        response_mode = str(metadata.get("chat_response_mode") or "direct_answer")
        delay_ms = self._PROFILE_DELAY_MS.get(profile, self._PROFILE_DELAY_MS["balanced"])

        time.sleep(delay_ms / 1000.0)

        user_text = ""
        if isinstance(request.messages, list) and request.messages:
            last = request.messages[-1]
            if isinstance(last, dict):
                content = last.get("content")
                if isinstance(content, str):
                    user_text = content.strip()

        if response_mode == "step_by_step_plan":
            text = (
                f"Краткий итог: запрос обработан ({profile}).\n\n"
                f"1. Вход: {user_text}\n"
                "2. Выполни шаги по порядку."
            )
        else:
            text = f"Ответ по запросу ({profile}): {user_text}"

        return LLMResponse(
            text=text,
            usage=None,
            provider="local",
            model_id=f"fake-{profile}",
            latency_ms=delay_ms,
            cache_hit=False,
            route_reason="latency-test",
            status="ok",
            error_type=None,
        )


def _init_store(tmp_path: Path) -> None:
    os.environ["ASTRA_DATA_DIR"] = str(tmp_path)
    os.environ["ASTRA_CHAT_FAST_PATH_ENABLED"] = "false"
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


def _percentile(samples: list[float], ratio: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    if len(ordered) == 1:
        return ordered[0]
    index = ratio * (len(ordered) - 1)
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _latency_stats(samples: list[float]) -> dict[str, float]:
    if not samples:
        return {"count": 0.0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "min": 0.0, "max": 0.0}
    return {
        "count": float(len(samples)),
        "avg": sum(samples) / len(samples),
        "p50": _percentile(samples, 0.50),
        "p95": _percentile(samples, 0.95),
        "min": min(samples),
        "max": max(samples),
    }


def _run_latency_scenario(
    client: TestClient,
    headers: dict[str, str],
    project_id: str,
    *,
    query: str,
    runs: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for _ in range(runs):
        started = perf_counter()
        response = client.post(
            f"/api/v1/projects/{project_id}/runs",
            json={"query_text": query, "mode": "plan_only"},
            headers=headers,
        )
        elapsed_ms = (perf_counter() - started) * 1000.0

        assert response.status_code == 200
        payload = response.json()
        assert payload["kind"] == "chat"
        run_id = payload["run"]["id"]

        run_snapshot = store.get_run(run_id)
        runtime_metrics = (run_snapshot or {}).get("meta", {}).get("runtime_metrics", {})
        response_latency_ms = runtime_metrics.get("response_latency_ms")
        assert isinstance(response_latency_ms, int)
        results.append(
            {
                "elapsed_ms": elapsed_ms,
                "response_latency_ms": float(response_latency_ms),
                "profile": runtime_metrics.get("chat_inference_profile"),
                "response_mode": runtime_metrics.get("chat_response_mode"),
            }
        )
    return results


def _format_report(report: dict[str, dict[str, Any]], *, runs: int) -> str:
    lines = [f"Chat path latency report (runs={runs})"]
    for scenario in ("short", "medium", "complex"):
        item = report[scenario]
        elapsed = item["elapsed"]
        runtime = item["runtime"]
        lines.append(
            (
                f"- {scenario}: elapsed p50={elapsed['p50']:.1f}ms p95={elapsed['p95']:.1f}ms; "
                f"runtime p50={runtime['p50']:.1f}ms p95={runtime['p95']:.1f}ms; "
                f"profile={item['profiles']} mode={item['response_modes']}"
            )
        )
    return "\n".join(lines)


def _threshold_ms(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def test_chat_path_latency_p50_p95_report(monkeypatch, tmp_path: Path):
    _init_store(tmp_path)
    monkeypatch.setenv("ASTRA_CHAT_AUTO_WEB_RESEARCH_ENABLED", "false")
    monkeypatch.setenv("ASTRA_LLM_FAST_QUERY_MAX_CHARS", "80")
    monkeypatch.setenv("ASTRA_LLM_FAST_QUERY_MAX_WORDS", "8")
    monkeypatch.setenv("ASTRA_LLM_COMPLEX_QUERY_MIN_CHARS", "260")
    monkeypatch.setenv("ASTRA_LLM_COMPLEX_QUERY_MIN_WORDS", "45")
    monkeypatch.setattr(runs_route, "get_brain", lambda: _LatencyBrain())
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

    runs_per_scenario = int(_threshold_ms("ASTRA_TEST_CHAT_LATENCY_SAMPLES", 7))
    runs_per_scenario = max(3, min(30, runs_per_scenario))

    client = TestClient(create_app())
    headers = _bootstrap(client)
    project = client.post("/api/v1/projects", json={"name": "latency-chat", "tags": [], "settings": {}}, headers=headers).json()
    project_id = project["id"]

    scenario_queries = {
        "short": "2+2?",
        "medium": "Объясни простым языком, как вернуться к тренировкам после перерыва без перегруза в первые две недели.",
        "complex": "Составь подробный план тренировок на месяц с этапами, рисками и метриками прогресса.",
    }
    report: dict[str, dict[str, Any]] = {}
    for scenario, query in scenario_queries.items():
        results = _run_latency_scenario(client, headers, project_id, query=query, runs=runs_per_scenario)
        elapsed_samples = [float(item["elapsed_ms"]) for item in results]
        runtime_samples = [float(item["response_latency_ms"]) for item in results]
        profiles = sorted({str(item.get("profile") or "") for item in results})
        response_modes = sorted({str(item.get("response_mode") or "") for item in results})
        report[scenario] = {
            "elapsed": _latency_stats(elapsed_samples),
            "runtime": _latency_stats(runtime_samples),
            "profiles": profiles,
            "response_modes": response_modes,
        }

    report_text = _format_report(report, runs=runs_per_scenario)
    print(report_text)

    assert "fast" in report["short"]["profiles"], report_text
    assert "balanced" in report["medium"]["profiles"], report_text
    assert "complex" in report["complex"]["profiles"], report_text
    assert "step_by_step_plan" in report["complex"]["response_modes"], report_text

    short_p95_limit = _threshold_ms("ASTRA_TEST_CHAT_LATENCY_SHORT_P95_MS", 700.0)
    medium_p95_limit = _threshold_ms("ASTRA_TEST_CHAT_LATENCY_MEDIUM_P95_MS", 950.0)
    complex_p95_limit = _threshold_ms("ASTRA_TEST_CHAT_LATENCY_COMPLEX_P95_MS", 1400.0)

    assert report["short"]["elapsed"]["p95"] <= short_p95_limit, report_text
    assert report["medium"]["elapsed"]["p95"] <= medium_p95_limit, report_text
    assert report["complex"]["elapsed"]["p95"] <= complex_p95_limit, report_text
