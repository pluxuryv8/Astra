from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.agent import build_chat_system_prompt
from memory import letta_bridge


def test_superagi_autonomy_enabled_for_autonomy_task(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "letta_superagi.sqlite3"
    monkeypatch.setenv("ASTRA_LETTA_DB_PATH", str(db_path))
    letta_bridge.reset_for_tests(db_path)

    prompt, analysis = build_chat_system_prompt(
        [],
        None,
        user_message="Включи автономию на 30 минут и запусти self-task scheduler.",
        history=[{"role": "user", "content": "Нужен автономный цикл без моего участия."}],
        owner_direct_mode=True,
    )

    assert analysis["autonomy"] is True
    assert analysis["superagi_autonomy"]["mode"] == "autonomy"
    assert analysis["superagi_autonomy"]["started"] is True
    assert "[SuperAGI Autonomy]" in prompt


def test_superagi_autonomy_disabled_for_regular_task(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "letta_superagi_off.sqlite3"
    monkeypatch.setenv("ASTRA_LETTA_DB_PATH", str(db_path))
    letta_bridge.reset_for_tests(db_path)

    prompt, analysis = build_chat_system_prompt(
        [],
        None,
        user_message="Дай короткий ответ по ковариации.",
        history=[],
        owner_direct_mode=True,
    )

    assert analysis["autonomy"] is False
    assert analysis["superagi_autonomy"]["mode"] == "single"
    assert "[SuperAGI Autonomy]" in prompt
