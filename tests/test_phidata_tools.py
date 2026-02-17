from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.agent import analyze_tone
from memory import letta_bridge
from skills import phidata_tools


def test_phidata_rag_recommends_web_tool():
    history = [
        {"role": "user", "content": "Найди источники по LangGraph."},
        {"role": "assistant", "content": "Могу включить web поиск."},
    ]
    context = phidata_tools.rag(history, query="Поиск источников и веб-материалов")
    assert context["hit_count"] >= 1
    assert "web_search" in context["recommended_tools"]


def test_phidata_rag_recommends_shell_tool():
    history = [{"role": "user", "content": "Запусти команду в terminal"}]
    context = phidata_tools.rag(history, query="Нужна shell команда")
    assert context["hit_count"] >= 1
    assert "shell" in context["recommended_tools"]


def test_analyze_tone_includes_phidata_context(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "letta_phidata.sqlite3"
    monkeypatch.setenv("ASTRA_LETTA_DB_PATH", str(db_path))
    letta_bridge.reset_for_tests(db_path)

    history = [
        {"role": "user", "content": "Нужен workflow и shell шаги для деплоя."},
        {"role": "assistant", "content": "Соберу граф и команды."},
    ]
    analysis = analyze_tone("Построй workflow и команды shell", history)

    assert analysis["workflow"] is True
    assert "phidata_context" in analysis
    assert analysis["phidata_context"]["hit_count"] >= 1
    assert analysis["recall"]["phidata_hits"] >= 1
