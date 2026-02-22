from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apps.api.routes import runs as runs_route
from skills.web_research import skill as web_research


class FakeSearchClient:
    def __init__(self, responses: dict[str, list[dict]]):
        self.responses = responses

    def search(self, query: str, urls=None):  # noqa: ANN001
        return list(self.responses.get(query, []))


def _ctx(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        run={"id": "run-web-scenarios", "query_text": "initial query", "meta": {}},
        plan_step={"id": "step-1"},
        task={"id": "task-1"},
        settings={"search": {"provider": "ddgs"}},
        base_dir=str(tmp_path),
    )


def test_web_research_case_fresh_info_triggers_on_uncertain_answer(monkeypatch):
    monkeypatch.setenv("ASTRA_CHAT_AUTO_WEB_RESEARCH_ENABLED", "true")
    query = "Какие последние новости по OpenAI сегодня?"
    answer = "Не знаю точно, возможно появились новые обновления."

    should_research, reason = runs_route._auto_web_research_decision(query, answer, error_type=None)

    assert should_research is True
    assert reason in {"uncertain_response", "off_topic"}


def test_web_research_case_disputed_info_triggers(monkeypatch):
    monkeypatch.setenv("ASTRA_CHAT_AUTO_WEB_RESEARCH_ENABLED", "true")
    query = "Кто первым предложил эту теорию?"
    answer = "Версии расходятся, не могу подтвердить, кто прав."

    should_research, reason = runs_route._auto_web_research_decision(query, answer, error_type=None)

    assert should_research is True
    assert reason in {"uncertain_response", "off_topic"}


def test_web_research_case_off_topic_triggers(monkeypatch):
    monkeypatch.setenv("ASTRA_CHAT_AUTO_WEB_RESEARCH_ENABLED", "true")
    query = "Кто такой Кен Канеки?"
    answer = "Давай лучше обсудим продуктивность и тайм-менеджмент."

    should_research, reason = runs_route._auto_web_research_decision(query, answer, error_type=None)

    assert should_research is True
    assert reason == "off_topic"


def test_web_research_case_few_sources_returns_fallback_answer(monkeypatch, tmp_path: Path):
    ctx = _ctx(tmp_path)
    client = FakeSearchClient(
        {
            "initial query": [
                {"url": "https://example.org/a", "title": "A", "snippet": "snippet A"},
            ]
        }
    )
    monkeypatch.setattr(web_research, "build_search_client", lambda _settings: client)
    monkeypatch.setattr(
        web_research,
        "_fetch_and_extract_cached",
        lambda _ctx, *, run_id, candidate, timeout_s=15, max_bytes=2_000_000: {
            "url": candidate["url"],
            "title": candidate.get("title"),
            "domain": candidate.get("domain"),
            "snippet": candidate.get("snippet"),
            "final_url": candidate["url"],
            "extracted_text": "valid text about the topic",
            "error": None,
        },
    )
    monkeypatch.setattr(
        web_research,
        "_judge_research",
        lambda *_args, **_kwargs: {
            "decision": "NOT_ENOUGH",
            "score": 0.2,
            "why": "need more sources",
            "next_query": None,
            "missing_topics": ["sources"],
            "need_sources": 1,
            "used_urls": ["https://example.org/a"],
        },
    )

    result = web_research.run({"query": "initial query", "mode": "deep", "max_rounds": 1}, ctx)

    assert len(result.sources) == 1
    assert result.confidence == 0.35
    assert any("judge_next_query_missing" in item for item in result.assumptions)


def test_web_research_case_bad_source_is_filtered(monkeypatch, tmp_path: Path):
    ctx = _ctx(tmp_path)
    client = FakeSearchClient(
        {
            "initial query": [
                {"url": "https://www.baidu.com/s?wd=test", "title": "bad source", "snippet": "noise"},
            ]
        }
    )
    monkeypatch.setattr(web_research, "build_search_client", lambda _settings: client)

    result = web_research.run({"query": "initial query", "mode": "deep", "max_rounds": 1}, ctx)

    assert result.confidence == 0.0
    assert any("no_pages_fetched" in item for item in result.assumptions)

