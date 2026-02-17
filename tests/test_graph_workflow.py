from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.agent import build_chat_system_prompt
from core.graph_workflow import graph_workflow
from memory import letta_bridge


def test_graph_workflow_executes_for_workflow_task(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "letta_graph.sqlite3"
    monkeypatch.setenv("ASTRA_LETTA_DB_PATH", str(db_path))
    letta_bridge.reset_for_tests(db_path)

    result = graph_workflow(
        "Построй workflow для задачи деплоя и проверок.",
        [{"role": "user", "content": "Нужна оркестрация этапов."}],
    )

    assert result["mode"] == "workflow"
    assert result["executed"] is True
    assert result["state"]["workflow_finished"] is True
    assert result["state"].get("decompose_output")


def test_prompt_contains_workflow_block(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "letta_prompt.sqlite3"
    monkeypatch.setenv("ASTRA_LETTA_DB_PATH", str(db_path))
    letta_bridge.reset_for_tests(db_path)

    prompt, analysis = build_chat_system_prompt(
        [],
        None,
        user_message="Построй workflow для задачи и распиши узлы графа.",
        history=[{"role": "user", "content": "Нужен stateful pipeline."}],
        owner_direct_mode=True,
    )

    assert analysis["workflow"] is True
    assert analysis["workflow_graph"]["executed"] is True
    assert "[Workflow Graph]" in prompt
