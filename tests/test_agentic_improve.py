from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import agentic_improve
from core.agent import build_chat_system_prompt, system_health_check
from memory import letta_bridge


def test_agentic_improve_feedback_loop_produces_preferences():
    result = agentic_improve.run(
        "Включи self_improve и адаптируй стиль по истории.",
        tone_analysis={
            "self_improve": True,
            "primary_mode": "Loyal/Reliable",
            "supporting_mode": "Practical/Solution",
            "response_shape": "balanced_direct",
            "mode_history": ["Loyal/Reliable", "Practical/Solution", "Loyal/Reliable"],
            "recall": {"trend": "steady"},
        },
        mode_history=["Loyal/Reliable", "Practical/Solution", "Loyal/Reliable"],
        history=[{"role": "user", "content": "Хочу, чтобы ты улучшался по моему фидбеку."}],
    )

    assert result["self_improve"] is True
    assert result["updated"] is True
    assert result["preferences"]
    assert "mode_history" in result["summary"]


def test_prompt_contains_agentic_block_when_self_improve_enabled(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "letta_agentic.sqlite3"
    monkeypatch.setenv("ASTRA_LETTA_DB_PATH", str(db_path))
    letta_bridge.reset_for_tests(db_path)

    prompt, analysis = build_chat_system_prompt(
        [],
        None,
        user_message="Запусти self_improve feedback loop и адаптируйся по mode history.",
        history=[
            {"role": "user", "content": "Ты был в режиме Loyal/Reliable."},
            {"role": "user", "content": "Теперь нужно больше Practical/Solution."},
        ],
        owner_direct_mode=True,
    )

    assert analysis["self_improve"] is True
    assert analysis["agentic_improve"]["self_improve"] is True
    assert "[Agentic Improve]" in prompt


def test_system_health_check_reports_nine_agents():
    health = system_health_check()
    assert health["total_agents"] == 9
    assert health["active_count"] == 9
    assert health["all_active"] is True
    assert "Agents: 9/9 active" == health["summary"]
