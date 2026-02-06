from __future__ import annotations

from pathlib import Path

from core.skills.schemas import load_schema, validate_inputs
from skills.computer import skill as computer_skill

ROOT = Path(__file__).resolve().parents[1]


class DummyBridge:
    def __init__(self):
        self.actions = None

    def computer_execute(self, actions):
        self.actions = actions
        return {"summary": "ok"}


def test_computer_skill_uses_steps(monkeypatch):
    inputs = {"steps": [{"action": "left_click", "coordinate": [10, 20]}]}
    schema = load_schema("schemas/skills/computer.inputs.schema.json", ROOT)
    validate_inputs(schema, inputs)

    dummy = DummyBridge()
    monkeypatch.setattr("skills.computer.skill.DesktopBridge", lambda: dummy)

    computer_skill.run(inputs, ctx=None)
    assert dummy.actions == inputs["steps"]
