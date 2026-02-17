from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import agent_reflection
from core.agent import analyze_tone
from memory import letta_bridge


def test_praison_reflection_run_returns_mode_boost():
    result = agent_reflection.run(
        [{"role": "user", "content": "Нужно обсудить риски и план."}],
        user_message="Поговорим про задачу и как лучше ее вести дальше.",
        tone_analysis={
            "type": "reflective",
            "intensity": 0.62,
            "signals": {"question": 1},
            "recall": {"trend": "steady"},
            "task_complex": True,
            "workflow": False,
            "conversation": True,
        },
    )

    assert result["updated"] is True
    assert result["mode_boost"] in {"low", "medium", "high"}
    assert result["confidence"] > 0.0
    assert result["steps"]


def test_analyze_tone_includes_praison_reflect(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "letta_praison.sqlite3"
    monkeypatch.setenv("ASTRA_LETTA_DB_PATH", str(db_path))
    letta_bridge.reset_for_tests(db_path)

    analysis = analyze_tone(
        "Поговорим о задаче: нужно спокойно разобрать риски и сделать план.",
        [{"role": "user", "content": "Давай пройдем это через диалог."}],
    )

    assert analysis["conversation"] is True
    assert "praison_reflect" in analysis
    assert analysis["praison_reflect"]["updated"] is True
    assert analysis["praison_reflect"]["mode_boost"] in {"low", "medium", "high"}
    assert analysis["recall"]["praison_confidence"] >= 0.0
