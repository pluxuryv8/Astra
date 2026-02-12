from __future__ import annotations

import base64
import json
import os
import threading
import time
from pathlib import Path

from core.executor.computer_executor import ComputerExecutor, ExecutorConfig
from memory import store

ROOT = Path(__file__).resolve().parents[1]


class StubBrain:
    def __init__(self, actions: list[dict]):
        self.actions = actions
        self.calls = 0

    def call(self, request, ctx=None):
        from core.brain.types import LLMResponse

        idx = min(self.calls, len(self.actions) - 1)
        payload = self.actions[idx]
        self.calls += 1
        return LLMResponse(
            text=json.dumps(payload, ensure_ascii=False),
            usage=None,
            provider="local",
            model_id="stub",
            latency_ms=1,
            cache_hit=False,
            route_reason="stub",
        )


class StubBridge:
    def __init__(self, captures: list[dict]):
        self.captures = list(captures)
        self.actions: list[dict] = []

    def autopilot_capture(self, max_width=1280, quality=60):
        if self.captures:
            return self.captures.pop(0)
        return {"image_base64": "", "width": 1, "height": 1}

    def autopilot_act(self, action, image_width, image_height):
        self.actions.append(action)
        return {"status": "ok"}


def _prepare_store(tmp_path: Path):
    os.environ["ASTRA_DATA_DIR"] = str(tmp_path)
    store.reset_for_tests()
    store.init(tmp_path, ROOT / "memory" / "migrations")


def _make_run():
    project = store.create_project("executor", [], {})
    run = store.create_run(project["id"], "Проверь окно", "execute_confirm")
    run["settings"] = {}
    return run


def _make_step(run_id: str, requires_approval: bool = False, danger_flags: list[str] | None = None):
    danger_flags = danger_flags or (["delete_file"] if requires_approval else [])
    step = {
        "id": "step-1",
        "run_id": run_id,
        "step_index": 0,
        "title": "Тестовый шаг",
        "skill_name": "autopilot_computer",
        "inputs": {},
        "depends_on": [],
        "status": "created",
        "kind": "COMPUTER_ACTIONS",
        "success_criteria": "Экран изменился",
        "danger_flags": danger_flags,
        "requires_approval": requires_approval,
        "artifacts_expected": [],
    }
    store.insert_plan_steps(run_id, [step])
    return step


def _make_task(run_id: str, step_id: str):
    task = store.create_task(run_id, step_id, attempt=1)
    store.update_task_status(task["id"], "running")
    return task


def test_executor_executes_single_action(tmp_path):
    _prepare_store(tmp_path)
    run = _make_run()
    step = _make_step(run["id"])
    task = _make_task(run["id"], step["id"])

    img_a = base64.b64encode(b"a").decode("utf-8")
    img_b = base64.b64encode(b"b").decode("utf-8")
    bridge = StubBridge([
        {"image_base64": img_a, "width": 2, "height": 2},
        {"image_base64": img_b, "width": 2, "height": 2},
        {"image_base64": img_b, "width": 2, "height": 2},
    ])
    brain = StubBrain([
        {"action_type": "click", "x": 1, "y": 1},
        {"action_type": "done"},
    ])
    config = ExecutorConfig(max_micro_steps=2, wait_timeout_ms=0, wait_poll_ms=0, wait_after_act_ms=0)
    executor = ComputerExecutor(ROOT, bridge=bridge, config=config, brain=brain)

    result = executor.execute_step(run, step, task)

    assert result.status == "done"
    assert len(bridge.actions) == 1

    events = store.list_events(run["id"], limit=200)
    event_types = {e["type"] for e in events}
    assert "step_execution_started" in event_types
    assert "micro_action_executed" in event_types
    assert "step_execution_finished" in event_types


def test_executor_stops_on_no_progress(tmp_path):
    _prepare_store(tmp_path)
    run = _make_run()
    step = _make_step(run["id"])
    task = _make_task(run["id"], step["id"])

    img_a = base64.b64encode(b"a").decode("utf-8")
    bridge = StubBridge([
        {"image_base64": img_a, "width": 2, "height": 2},
        {"image_base64": img_a, "width": 2, "height": 2},
        {"image_base64": img_a, "width": 2, "height": 2},
    ])
    brain = StubBrain([{ "action_type": "click", "x": 1, "y": 1 }])
    config = ExecutorConfig(max_micro_steps=1, max_no_progress=1, wait_timeout_ms=0, wait_poll_ms=0, wait_after_act_ms=0)
    executor = ComputerExecutor(ROOT, bridge=bridge, config=config, brain=brain)
    executor._request_user_help = lambda *args, **kwargs: False  # type: ignore

    result = executor.execute_step(run, step, task)

    assert result.status == "failed"
    events = store.list_events(run["id"], limit=200)
    event_types = {e["type"] for e in events}
    assert "verification_result" in event_types
    assert "step_execution_finished" in event_types


def test_executor_requires_approval(tmp_path):
    _prepare_store(tmp_path)
    run = _make_run()
    step = _make_step(run["id"], requires_approval=True)
    task = _make_task(run["id"], step["id"])

    img_a = base64.b64encode(b"a").decode("utf-8")
    img_b = base64.b64encode(b"b").decode("utf-8")
    bridge = StubBridge([
        {"image_base64": img_a, "width": 2, "height": 2},
        {"image_base64": img_b, "width": 2, "height": 2},
        {"image_base64": img_b, "width": 2, "height": 2},
    ])
    brain = StubBrain([{ "action_type": "click", "x": 1, "y": 1 }, { "action_type": "done" }])
    config = ExecutorConfig(max_micro_steps=2, wait_timeout_ms=0, wait_poll_ms=0, wait_after_act_ms=0)
    executor = ComputerExecutor(ROOT, bridge=bridge, config=config, brain=brain)

    result_holder: dict[str, object] = {}

    def run_exec():
        result_holder["result"] = executor.execute_step(run, step, task)

    thread = threading.Thread(target=run_exec)
    thread.start()

    approval_id = None
    for _ in range(20):
        approvals = store.list_approvals(run["id"])
        if approvals:
            approval_id = approvals[0]["id"]
            break
        time.sleep(0.05)

    assert approval_id is not None
    assert bridge.actions == []
    store.update_approval_status(approval_id, "approved", "test")

    thread.join(timeout=2)
    result = result_holder.get("result")
    assert result is not None
    assert getattr(result, "status") == "done"

    events = store.list_events(run["id"], limit=200)
    event_types = {e["type"] for e in events}
    assert "approval_requested" in event_types
    assert "step_paused_for_approval" in event_types


def test_executor_reject_stops(tmp_path):
    _prepare_store(tmp_path)
    run = _make_run()
    step = _make_step(run["id"], requires_approval=True)
    task = _make_task(run["id"], step["id"])

    img_a = base64.b64encode(b"a").decode("utf-8")
    bridge = StubBridge([
        {"image_base64": img_a, "width": 2, "height": 2},
    ])
    brain = StubBrain([{ "action_type": "done" }])
    config = ExecutorConfig(max_micro_steps=1, wait_timeout_ms=0, wait_poll_ms=0, wait_after_act_ms=0)
    executor = ComputerExecutor(ROOT, bridge=bridge, config=config, brain=brain)

    result_holder: dict[str, object] = {}

    def run_exec():
        result_holder["result"] = executor.execute_step(run, step, task)

    thread = threading.Thread(target=run_exec)
    thread.start()

    approval_id = None
    for _ in range(20):
        approvals = store.list_approvals(run["id"])
        if approvals:
            approval_id = approvals[0]["id"]
            break
        time.sleep(0.05)

    assert approval_id is not None
    store.update_approval_status(approval_id, "rejected", "test")

    thread.join(timeout=2)
    result = result_holder.get("result")
    assert result is not None
    assert getattr(result, "status") == "failed"
    assert bridge.actions == []

    events = store.list_events(run["id"], limit=200)
    event_types = {e["type"] for e in events}
    assert "step_cancelled_by_user" in event_types


def test_password_flag_requires_user_action(tmp_path):
    _prepare_store(tmp_path)
    run = _make_run()
    step = _make_step(run["id"], requires_approval=True, danger_flags=["password"])
    task = _make_task(run["id"], step["id"])

    bridge = StubBridge([])
    brain = StubBrain([{ "action_type": "type", "text": "secret" }])
    config = ExecutorConfig(max_micro_steps=1, wait_timeout_ms=0, wait_poll_ms=0, wait_after_act_ms=0)
    executor = ComputerExecutor(ROOT, bridge=bridge, config=config, brain=brain)

    result_holder: dict[str, object] = {}

    def run_exec():
        result_holder["result"] = executor.execute_step(run, step, task)

    thread = threading.Thread(target=run_exec)
    thread.start()

    approval_id = None
    for _ in range(20):
        approvals = store.list_approvals(run["id"])
        if approvals:
            approval_id = approvals[0]["id"]
            break
        time.sleep(0.05)

    assert approval_id is not None
    store.update_approval_status(approval_id, "approved", "test")

    thread.join(timeout=2)
    result = result_holder.get("result")
    assert result is not None
    assert getattr(result, "status") == "done"
    assert bridge.actions == []

    events = store.list_events(run["id"], limit=200)
    event_types = {e["type"] for e in events}
    assert "user_action_required" in event_types
