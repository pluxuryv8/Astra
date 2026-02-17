from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.agent import analyze_tone
from memory import letta_bridge


def test_letta_memory_update_and_recall(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "letta_recall.sqlite3"
    monkeypatch.setenv("ASTRA_LETTA_DB_PATH", str(db_path))
    letta_bridge.reset_for_tests(db_path)

    updated = letta_bridge.update(
        user_message="У нас падает деплой из-за некорректного nginx конфигурационного файла.",
        history=[],
        tone_analysis={"type": "frustrated", "task_complex": True},
        crew_result={"mode": "parallel"},
    )
    assert updated["updated"] is True

    recall = letta_bridge.retrieve(
        [{"role": "user", "content": "Помнишь проблему с nginx деплоем?"}],
        query="nginx деплой",
        limit=3,
    )
    assert recall["hit_count"] >= 1
    assert recall["summary"]


def test_analyze_tone_includes_letta_recall(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "letta_tone.sqlite3"
    monkeypatch.setenv("ASTRA_LETTA_DB_PATH", str(db_path))
    letta_bridge.reset_for_tests(db_path)

    letta_bridge.update(
        user_message="Фиксили конфликт миграций sqlite в рантайме.",
        history=[],
        tone_analysis={"type": "dry", "task_complex": False},
        crew_result={"mode": "single"},
    )

    analysis = analyze_tone(
        "Напомни про конфликт миграций sqlite.",
        [{"role": "user", "content": "Ранее обсуждали миграции."}],
    )
    assert "letta_recall" in analysis
    assert analysis["letta_recall"]["hit_count"] >= 1
