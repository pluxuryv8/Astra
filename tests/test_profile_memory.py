from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apps.api.routes import runs as runs_route
from core.chat_context import build_memory_dump_response
from core.skill_context import SkillContext
from memory import store
from skills.memory_save import skill as memory_skill


def _init_store(tmp_path: Path):
    os.environ["ASTRA_DATA_DIR"] = str(tmp_path)
    store.reset_for_tests()
    store.init(tmp_path, ROOT / "memory" / "migrations")


def test_memory_save_name(tmp_path: Path):
    _init_store(tmp_path)
    project = store.create_project("Mem", [], {})
    run = store.create_run(project["id"], "кстати, меня Михаил зовут", "execute_confirm")

    step = {
        "id": "step-memory",
        "run_id": run["id"],
        "step_index": 0,
        "title": "Сохранить в память",
        "skill_name": "memory_save",
        "inputs": {"content": run["query_text"], "facts": ["Имя пользователя: Михаил."]},
        "depends_on": [],
        "status": "created",
        "kind": "MEMORY_COMMIT",
        "success_criteria": "ok",
        "danger_flags": [],
        "requires_approval": False,
        "artifacts_expected": [],
    }
    store.insert_plan_steps(run["id"], [step])
    task = store.create_task(run["id"], step["id"], attempt=1)

    ctx = SkillContext(run=run, plan_step=step, task=task, settings={}, base_dir=str(ROOT))
    memory_skill.run(step["inputs"], ctx)

    items = store.list_user_memories()
    assert any("Михаил" in item.get("content", "") for item in items)


def test_memory_dump_uses_profile_items(tmp_path: Path):
    _init_store(tmp_path)
    store.create_user_memory(None, "Имя пользователя: Михаил.", [])
    store.create_user_memory(None, "Предпочтение пользователя: короткие ответы.", [])

    items = store.list_user_memories()
    response = build_memory_dump_response(items)

    assert "Вот что я помню о тебе" in response
    assert "Михаил" in response
    assert "короткие ответы" in response


def test_memory_dump_empty():
    response = build_memory_dump_response([])
    assert "Пока ничего не помню" in response


def test_chat_system_prompt_uses_name_and_style_from_profile(tmp_path: Path):
    _init_store(tmp_path)
    store.create_user_memory(
        "Профиль пользователя",
        "Пользователь представился как Михаил.",
        [],
        meta={
            "summary": "Пользователь представился как Михаил.",
            "facts": [{"key": "user.name", "value": "Михаил", "confidence": 0.95, "evidence": "меня зовут Михаил"}],
            "preferences": [{"key": "style.brevity", "value": "short", "confidence": 0.86}],
        },
    )
    memories = store.list_user_memories()
    prompt = runs_route._build_chat_system_prompt(memories, None)
    assert "Имя пользователя: Михаил." in prompt
    assert "Отвечай коротко и по делу." in prompt


def test_chat_system_prompt_owner_direct_mode_toggle(monkeypatch):
    monkeypatch.setenv("ASTRA_OWNER_DIRECT_MODE", "true")
    prompt_direct = runs_route._build_chat_system_prompt([], None)
    assert "Режим владельца: ON." in prompt_direct

    monkeypatch.setenv("ASTRA_OWNER_DIRECT_MODE", "false")
    prompt_default = runs_route._build_chat_system_prompt([], None)
    assert "Режим владельца: OFF." in prompt_default


def test_chat_inference_defaults(monkeypatch):
    monkeypatch.delenv("ASTRA_LLM_CHAT_TEMPERATURE", raising=False)
    monkeypatch.delenv("ASTRA_LLM_CHAT_TOP_P", raising=False)
    monkeypatch.delenv("ASTRA_LLM_CHAT_REPEAT_PENALTY", raising=False)
    monkeypatch.delenv("ASTRA_LLM_OLLAMA_NUM_PREDICT", raising=False)

    assert runs_route._chat_temperature_default() == 0.35
    assert runs_route._chat_top_p_default() == 0.9
    assert runs_route._chat_repeat_penalty_default() == 1.15
    assert runs_route._chat_num_predict_default() == 256


def test_chat_soft_retry_heuristics():
    assert runs_route._soft_retry_reason("Сделай это", "Как ИИ я не могу помочь в этом.") == "unwanted_prefix"
    assert runs_route._soft_retry_reason("Сделай это", "Сделай следующее...") == "truncated"
    assert runs_route._soft_retry_reason("Привет, как дела?", "Hello there") == "ru_language_mismatch"
    assert (
        runs_route._soft_retry_reason(
            "Как пытали канеки Кена в токийском гуле",
            "Давайте сначала поговорим о текущей проблеме.",
        )
        == "off_topic"
    )
    assert (
        runs_route._soft_retry_reason(
            "Как пытали канеки Кена в токийском гуле",
            "В 1980 году я попал на вечеринку в Токио и пытался выпить из канеки Кена.",
        )
        == "off_topic"
    )
    assert (
        runs_route._soft_retry_reason(
            "Как пытали канеки Кена в токийском гуле",
            "Пока не слышала, но предполагаю, что это было намного интереснее, чем обычный гул.",
        )
        == "off_topic"
    )
    assert (
        runs_route._soft_retry_reason(
            "А сюжет хентая эйфория знаешь?",
            "Хентай - жанр с элементами фантастического сюжета и различными стилями.",
        )
        == "off_topic"
    )
    assert runs_route._soft_retry_reason("Привет, как дела?", "Привет! Всё нормально.") is None


def test_auto_web_research_trigger_heuristics(monkeypatch):
    monkeypatch.setenv("ASTRA_CHAT_AUTO_WEB_RESEARCH_ENABLED", "true")

    assert runs_route._should_auto_web_research(
        "А сюжет хентая эйфория знаешь?",
        "Хентай - жанр с элементами фантастического сюжета и различными стилями.",
        error_type=None,
    )
    assert runs_route._should_auto_web_research(
        "Кто такой Кен Канеки?",
        "Не знаю точно, возможно это персонаж аниме.",
        error_type=None,
    )
    assert not runs_route._should_auto_web_research(
        "привет",
        "Не знаю.",
        error_type=None,
    )
