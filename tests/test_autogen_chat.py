from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.agent import build_chat_system_prompt
from memory import letta_bridge


def test_autogen_chat_executes_for_conversation_task(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "letta_autogen.sqlite3"
    monkeypatch.setenv("ASTRA_LETTA_DB_PATH", str(db_path))
    letta_bridge.reset_for_tests(db_path)

    prompt, analysis = build_chat_system_prompt(
        [],
        None,
        user_message="Поговорим о задаче и обсудим варианты решения по шагам.",
        history=[
            {"role": "user", "content": "Нужно принять архитектурное решение."},
            {"role": "assistant", "content": "Ок, можем пройтись диалогом."},
        ],
        owner_direct_mode=True,
    )

    assert analysis["conversation"] is True
    assert analysis["autogen_chat"]["mode"] == "conversation"
    assert analysis["autogen_chat"]["executed"] is True
    assert "[AutoGen Chat]" in prompt


def test_autogen_chat_disabled_for_non_conversation_task(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "letta_autogen_off.sqlite3"
    monkeypatch.setenv("ASTRA_LETTA_DB_PATH", str(db_path))
    letta_bridge.reset_for_tests(db_path)

    prompt, analysis = build_chat_system_prompt(
        [],
        None,
        user_message="Дай формулу ковариации без пояснений.",
        history=[],
        owner_direct_mode=True,
    )

    assert analysis["conversation"] is False
    assert analysis["autogen_chat"]["mode"] == "single"
    if analysis.get("path") == "fast":
        assert "[AutoGen Chat]" not in prompt
    else:
        assert "[AutoGen Chat]" in prompt
