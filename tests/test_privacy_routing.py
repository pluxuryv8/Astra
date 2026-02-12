from __future__ import annotations

from types import SimpleNamespace

from core.brain.router import BrainConfig, BrainRouter
from core.brain.types import LLMRequest
from core.llm_routing import (
    FINANCIAL_APPROVAL_SCOPE,
    ROUTE_CLOUD,
    ROUTE_LOCAL,
    ContextItem,
    PolicyFlags,
    decide_route,
    sanitize_context_items,
)


def _dummy_ctx(settings: dict):
    return SimpleNamespace(
        run={"id": "run-1"},
        task={"id": "task-1"},
        plan_step={"id": "step-1"},
        settings=settings,
        base_dir=".",
    )


def test_policy_telegram_forces_local():
    items = [ContextItem(content="hi", source_type="telegram_text", sensitivity="personal")]
    decision = decide_route(None, items, PolicyFlags())
    assert decision.route == ROUTE_LOCAL


def test_policy_web_only_cloud():
    items = [ContextItem(content="web", source_type="web_page_text", sensitivity="public")]
    decision = decide_route(None, items, PolicyFlags())
    assert decision.route == ROUTE_CLOUD


def test_policy_financial_file_requires_approval():
    items = [ContextItem(content="bank", source_type="file_content", sensitivity="financial")]
    decision = decide_route(None, items, PolicyFlags())
    assert decision.route == ROUTE_LOCAL
    assert decision.required_approval == FINANCIAL_APPROVAL_SCOPE


def test_policy_financial_file_with_approval_allows_cloud():
    items = [ContextItem(content="bank", source_type="file_content", sensitivity="financial")]
    decision = decide_route(None, items, PolicyFlags(), approved_scopes={FINANCIAL_APPROVAL_SCOPE})
    assert decision.route == ROUTE_CLOUD


def test_policy_mixed_web_and_telegram_local():
    items = [
        ContextItem(content="web", source_type="web_page_text", sensitivity="public"),
        ContextItem(content="chat", source_type="telegram_text", sensitivity="personal"),
    ]
    decision = decide_route(None, items, PolicyFlags())
    assert decision.route == ROUTE_LOCAL


def test_sanitizer_financial_file_with_approval():
    items = [ContextItem(content="bank", source_type="file_content", sensitivity="financial")]
    flags = PolicyFlags(max_cloud_chars=100, max_cloud_item_chars=50)
    result = sanitize_context_items(items, allow_financial_file=True, flags=flags)
    assert result.items
    assert result.removed_counts_by_source["file_content"] == 0


def test_audit_events_emitted(monkeypatch):
    events: list[str] = []

    def _emit(run_id, event_type, message, payload, level="info", task_id=None, step_id=None):
        events.append(event_type)
        return {}

    monkeypatch.setattr("core.brain.router.emit", _emit)

    cfg = BrainConfig.from_env()
    cfg.cloud_enabled = True
    cfg.auto_cloud_enabled = True
    router = BrainRouter(cfg)

    def _call_cloud(messages, request, model_id, start):
        return router._make_response(text="{}", provider="cloud", model_id=model_id, start_time=start)

    monkeypatch.setattr(router, "_call_cloud_with_retry", _call_cloud)

    ctx = _dummy_ctx({})
    items = [ContextItem(content="web", source_type="web_page_text", sensitivity="public")]

    def build_messages(_items):
        return [{"role": "user", "content": "ok"}]

    request = LLMRequest(
        purpose="test",
        context_items=items,
        render_messages=build_messages,
        run_id=ctx.run["id"],
        task_id=ctx.task["id"],
        step_id=ctx.plan_step["id"],
    )

    router.call(request, ctx)

    assert "llm_route_decided" in events
    assert "llm_request_sanitized" in events
    assert "llm_request_started" in events
    assert "llm_request_succeeded" in events
