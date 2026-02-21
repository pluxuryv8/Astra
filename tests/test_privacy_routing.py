from __future__ import annotations

from core.brain.providers import ProviderResult
from core.brain.router import BrainConfig, BrainRouter
from core.brain.types import LLMRequest
from core.llm_routing import ROUTE_LOCAL, ContextItem, PolicyFlags, decide_route, sanitize_context_items


def test_policy_telegram_forces_local():
    items = [ContextItem(content="hi", source_type="telegram_text", sensitivity="personal")]
    decision = decide_route(None, items, PolicyFlags())
    assert decision.route == ROUTE_LOCAL


def test_policy_web_only_stays_local():
    items = [ContextItem(content="web", source_type="web_page_text", sensitivity="public")]
    decision = decide_route(None, items, PolicyFlags())
    assert decision.route == ROUTE_LOCAL


def test_policy_financial_file_stays_local_without_approval():
    items = [ContextItem(content="bank", source_type="file_content", sensitivity="financial")]
    decision = decide_route(None, items, PolicyFlags())
    assert decision.route == ROUTE_LOCAL
    assert decision.required_approval is None


def test_policy_mixed_web_and_telegram_local():
    items = [
        ContextItem(content="web", source_type="web_page_text", sensitivity="public"),
        ContextItem(content="chat", source_type="telegram_text", sensitivity="personal"),
    ]
    decision = decide_route(None, items, PolicyFlags())
    assert decision.route == ROUTE_LOCAL


def test_policy_screenshot_text_forces_local():
    items = [ContextItem(content="ocr", source_type="screenshot_text", sensitivity="confidential")]
    decision = decide_route(None, items, PolicyFlags())
    assert decision.route == ROUTE_LOCAL


def test_sanitizer_financial_file_with_explicit_allow():
    items = [ContextItem(content="bank", source_type="file_content", sensitivity="financial")]
    flags = PolicyFlags(max_item_chars=50)
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
    router = BrainRouter(cfg)

    monkeypatch.setattr(router, "_call_local", lambda *_args, **_kwargs: ProviderResult(text="{}", usage=None, raw={}, model_id=None))

    items = [ContextItem(content="web", source_type="web_page_text", sensitivity="public")]

    def build_messages(_items):
        return [{"role": "user", "content": "ok"}]

    request = LLMRequest(
        purpose="test",
        context_items=items,
        render_messages=build_messages,
        run_id="run-1",
        task_id="task-1",
        step_id="step-1",
    )

    router.call(request, None)

    assert "llm_route_decided" in events
    assert "llm_request_started" in events
    assert "llm_request_succeeded" in events
