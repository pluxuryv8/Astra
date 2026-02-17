from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.agent import build_chat_system_prompt
from memory import letta_bridge


def test_parallel_think_enabled_for_complex_task(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "letta_parallel.sqlite3"
    monkeypatch.setenv("ASTRA_LETTA_DB_PATH", str(db_path))
    letta_bridge.reset_for_tests(db_path)

    message = (
        "Разбей сложную задачу на параллель: нужно продумать архитектуру, "
        "риск-анализ, тестовую стратегию и план внедрения по шагам."
    )
    history = [{"role": "user", "content": "Нам нужен стабильный прод."}]

    prompt, analysis = build_chat_system_prompt(
        [],
        None,
        user_message=message,
        history=history,
        owner_direct_mode=True,
    )

    assert analysis["task_complex"] is True
    assert analysis["parallel_think"]["mode"] == "parallel"
    assert "[Parallel Thinking]" in prompt


def test_parallel_think_disabled_for_simple_task(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "letta_simple.sqlite3"
    monkeypatch.setenv("ASTRA_LETTA_DB_PATH", str(db_path))
    letta_bridge.reset_for_tests(db_path)

    prompt, analysis = build_chat_system_prompt(
        [],
        None,
        user_message="Дай коротко формулу ковариации.",
        history=[],
        owner_direct_mode=True,
    )

    assert analysis["task_complex"] is False
    assert analysis["parallel_think"]["mode"] == "single"
    if analysis.get("path") == "fast":
        assert "[Parallel Thinking]" not in prompt
    else:
        assert "[Parallel Thinking]" in prompt
