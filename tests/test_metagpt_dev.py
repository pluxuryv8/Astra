from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.agent import build_chat_system_prompt
from memory import letta_bridge


def test_metagpt_dev_enabled_for_dev_task(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "letta_metagpt.sqlite3"
    monkeypatch.setenv("ASTRA_LETTA_DB_PATH", str(db_path))
    letta_bridge.reset_for_tests(db_path)

    prompt, analysis = build_chat_system_prompt(
        [],
        None,
        user_message="Напиши модуль для Астры и добавь тесты к нему.",
        history=[{"role": "user", "content": "Нужен dev_task pipeline."}],
        owner_direct_mode=True,
    )

    assert analysis["dev_task"] is True
    assert analysis["metagpt_dev"]["mode"] == "dev"
    assert analysis["metagpt_dev"]["executed"] is True
    assert bool(analysis["metagpt_dev"]["generated_code"]) is True
    assert "[MetaGPT Dev]" in prompt


def test_metagpt_dev_disabled_for_regular_task(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "letta_metagpt_off.sqlite3"
    monkeypatch.setenv("ASTRA_LETTA_DB_PATH", str(db_path))
    letta_bridge.reset_for_tests(db_path)

    prompt, analysis = build_chat_system_prompt(
        [],
        None,
        user_message="Поговорим о задаче и рисках.",
        history=[],
        owner_direct_mode=True,
    )

    assert analysis["dev_task"] is False
    assert analysis["metagpt_dev"]["mode"] == "single"
    assert "[MetaGPT Dev]" in prompt
