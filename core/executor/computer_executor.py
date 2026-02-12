from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any

from core.brain import get_brain
from core.brain.types import LLMRequest, LLMResponse
from core.bridge.desktop_bridge import DesktopBridge
from core.event_bus import emit
from core.llm_routing import ContextItem
from memory import store


COMPUTER_STEP_KINDS = {
    "BROWSER_RESEARCH_UI",
    "COMPUTER_ACTIONS",
    "FILE_ORGANIZE",
    "CODE_ASSIST",
}

_ALLOWED_ACTIONS = {
    "move_mouse",
    "click",
    "double_click",
    "drag",
    "type",
    "key",
    "scroll",
    "wait",
    "done",
}


@dataclass
class ExecutorConfig:
    max_micro_steps: int = 30
    max_no_progress: int = 5
    max_total_time_s: int = 600
    wait_after_act_ms: int = 350
    wait_poll_ms: int = 500
    wait_timeout_ms: int = 4000
    max_action_retries: int = 1
    screenshot_width: int = 1280
    screenshot_quality: int = 60
    dry_run: bool = False

    @classmethod
    def from_env_and_settings(cls, settings: dict | None) -> "ExecutorConfig":
        cfg = (settings or {}).get("executor") or {}

        def _env_int(name: str, default: int) -> int:
            raw = os.getenv(name)
            if raw is None:
                return default
            try:
                return int(raw)
            except ValueError:
                return default

        def _env_bool(name: str, default: bool) -> bool:
            raw = os.getenv(name)
            if raw is None:
                return default
            return raw.strip().lower() in {"1", "true", "yes", "on"}

        return cls(
            max_micro_steps=_env_int("ASTRA_EXECUTOR_MAX_MICRO_STEPS", int(cfg.get("max_micro_steps", 30))),
            max_no_progress=_env_int("ASTRA_EXECUTOR_MAX_NO_PROGRESS", int(cfg.get("max_no_progress", 5))),
            max_total_time_s=_env_int("ASTRA_EXECUTOR_MAX_TOTAL_TIME_S", int(cfg.get("max_total_time_s", 600))),
            wait_after_act_ms=_env_int("ASTRA_EXECUTOR_WAIT_AFTER_ACT_MS", int(cfg.get("wait_after_act_ms", 350))),
            wait_poll_ms=_env_int("ASTRA_EXECUTOR_WAIT_POLL_MS", int(cfg.get("wait_poll_ms", 500))),
            wait_timeout_ms=_env_int("ASTRA_EXECUTOR_WAIT_TIMEOUT_MS", int(cfg.get("wait_timeout_ms", 4000))),
            max_action_retries=_env_int("ASTRA_EXECUTOR_MAX_ACTION_RETRIES", int(cfg.get("max_action_retries", 1))),
            screenshot_width=_env_int("ASTRA_EXECUTOR_SCREENSHOT_WIDTH", int(cfg.get("screenshot_width", 1280))),
            screenshot_quality=_env_int("ASTRA_EXECUTOR_SCREENSHOT_QUALITY", int(cfg.get("screenshot_quality", 60))),
            dry_run=_env_bool("ASTRA_EXECUTOR_DRY_RUN", bool(cfg.get("dry_run", False))),
        )


@dataclass
class Observation:
    hash: str
    width: int
    height: int
    ts: float


@dataclass
class StepResult:
    status: str
    reason: str
    micro_steps: int
    attempts: int
    last_observation: Observation | None


_MICRO_ACTION_SCHEMA = {
    "name": "micro_action",
    "schema": {
        "type": "object",
        "properties": {
            "action_type": {
                "type": "string",
                "enum": sorted(_ALLOWED_ACTIONS),
            },
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "start_x": {"type": "integer"},
            "start_y": {"type": "integer"},
            "end_x": {"type": "integer"},
            "end_y": {"type": "integer"},
            "text": {"type": "string"},
            "keys": {"type": "array", "items": {"type": "string"}},
            "dy": {"type": "integer"},
            "button": {"type": "string"},
            "ms": {"type": "integer"},
            "rationale": {"type": "string"},
            "expected_change": {"type": "string"},
        },
        "required": ["action_type"],
        "additionalProperties": False,
    },
}


_SYSTEM_PROMPT = (
    "Ты управляешь компьютером и предлагаешь одно атомарное действие за шаг. "
    "Верни JSON строго по схеме. Доступные action_type: move_mouse, click, double_click, "
    "drag, type, key, scroll, wait, done. "
    "Используй координаты (x, y) в системе изображения (width/height). "
    "Для drag укажи start_x/start_y и end_x/end_y. "
    "Для key используй keys (например [\"CMD\", \"L\"]). "
    "Если нужно подождать загрузку — action_type=wait и ms. "
    "Если считаешь шаг завершён — action_type=done. "
    "Не добавляй лишних полей и не пиши пояснений вне JSON."
)


class ComputerExecutor:
    def __init__(self, base_dir, bridge: DesktopBridge | None = None, config: ExecutorConfig | None = None, brain=None) -> None:
        self.base_dir = base_dir
        self.bridge = bridge or DesktopBridge()
        self.config = config
        self.brain = brain

    def execute_step(self, run: dict, step: dict, task: dict) -> StepResult:
        cfg = self.config or ExecutorConfig.from_env_and_settings(run.get("settings") or {})
        run_id = run["id"]
        step_id = step["id"]
        task_id = task["id"]

        emit(
            run_id,
            "step_execution_started",
            "Начат шаг исполнения",
            {"step_id": step_id, "kind": step.get("kind"), "title": step.get("title")},
            task_id=task_id,
            step_id=step_id,
        )

        if step.get("requires_approval") or step.get("danger_flags"):
            approved = self._request_step_approval(run, step, task)
            if not approved:
                emit(
                    run_id,
                    "step_execution_finished",
                    "Шаг остановлен из-за отказа",
                    {"status": "failed", "reason": "approval_rejected", "micro_steps": 0},
                    task_id=task_id,
                    step_id=step_id,
                )
                return StepResult("failed", "approval_rejected", 0, 1, None)

        last_observation: Observation | None = None
        last_action_summary: str | None = None
        no_progress = 0
        micro_steps = 0
        start_time = time.time()

        while micro_steps < cfg.max_micro_steps:
            if time.time() - start_time > cfg.max_total_time_s:
                emit(
                    run_id,
                    "step_execution_finished",
                    "Шаг остановлен по таймауту",
                    {"status": "failed", "reason": "max_time", "micro_steps": micro_steps},
                    task_id=task_id,
                    step_id=step_id,
                )
                return StepResult("failed", "max_time", micro_steps, 1, last_observation)

            obs_before = self._observe(run_id, step_id, task_id, "before", last_observation, cfg)

            action = None
            reason = {"provider": None, "reason": None}
            last_error: Exception | None = None
            for attempt in range(cfg.max_action_retries + 1):
                try:
                    action, reason = self._propose_action(run, step, task, obs_before, last_action_summary)
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < cfg.max_action_retries:
                        emit(
                            run_id,
                            "step_retrying",
                            "Повтор запроса действия",
                            {"attempt": attempt + 1, "reason": str(exc)},
                            task_id=task_id,
                            step_id=step_id,
                        )
                        continue

            if action is None:
                if self._request_user_help(run, step, task, reason=str(last_error or "action_missing")):
                    continue
                emit(
                    run_id,
                    "step_execution_finished",
                    "Шаг остановлен из-за ошибки планирования",
                    {"status": "failed", "reason": str(last_error or "action_missing"), "micro_steps": micro_steps},
                    task_id=task_id,
                    step_id=step_id,
                )
                return StepResult("failed", str(last_error or "action_missing"), micro_steps, 1, obs_before)
            action_type = action.get("type")

            emit(
                run_id,
                "micro_action_proposed",
                "Предложено действие",
                {
                    "action_type": action_type,
                    "action_summary": self._summarize_action(action),
                    "provider": reason.get("provider"),
                    "reason": reason.get("reason"),
                },
                task_id=task_id,
                step_id=step_id,
            )

            if action_type == "done":
                emit(
                    run_id,
                    "step_execution_finished",
                    "Шаг завершён",
                    {"status": "done", "reason": "model_done", "micro_steps": micro_steps},
                    task_id=task_id,
                    step_id=step_id,
                )
                return StepResult("done", "model_done", micro_steps, 1, obs_before)

            executed_ok = self._execute_action(action, obs_before, cfg)
            emit(
                run_id,
                "micro_action_executed",
                "Действие выполнено",
                {"action_type": action_type, "ok": executed_ok},
                task_id=task_id,
                step_id=step_id,
            )

            if not executed_ok:
                emit(
                    run_id,
                    "step_execution_finished",
                    "Шаг остановлен из-за ошибки действия",
                    {"status": "failed", "reason": "action_failed", "micro_steps": micro_steps},
                    task_id=task_id,
                    step_id=step_id,
                )
                return StepResult("failed", "action_failed", micro_steps, 1, obs_before)

            if action_type == "wait":
                time.sleep(float(action.get("ms") or cfg.wait_after_act_ms) / 1000)
            else:
                time.sleep(cfg.wait_after_act_ms / 1000)

            obs_after = self._observe(run_id, step_id, task_id, "after", obs_before, cfg)
            verify_result, verify_details, final_obs = self._verify_progress(run_id, step_id, task_id, obs_before, obs_after, cfg)
            emit(
                run_id,
                "verification_result",
                "Результат проверки",
                {"result": verify_result, "details": verify_details},
                task_id=task_id,
                step_id=step_id,
            )

            micro_steps += 1
            last_action_summary = self._summarize_action(action)
            last_observation = final_obs

            if verify_result == "pass_progress":
                no_progress = 0
            else:
                no_progress += 1
                emit(
                    run_id,
                    "step_retrying",
                    "Повтор шага",
                    {"attempt": no_progress, "reason": verify_result},
                    task_id=task_id,
                    step_id=step_id,
                )

            if no_progress >= cfg.max_no_progress:
                if self._request_user_help(run, step, task, reason=f"no_progress:{verify_result}"):
                    no_progress = 0
                else:
                    emit(
                        run_id,
                        "step_execution_finished",
                        "Шаг остановлен из-за отсутствия прогресса",
                        {"status": "failed", "reason": "no_progress", "micro_steps": micro_steps},
                        task_id=task_id,
                        step_id=step_id,
                    )
                    return StepResult("failed", "no_progress", micro_steps, 1, final_obs)

        emit(
            run_id,
            "step_execution_finished",
            "Шаг остановлен из-за лимита",
            {"status": "failed", "reason": "max_micro_steps", "micro_steps": micro_steps},
            task_id=task_id,
            step_id=step_id,
        )
        return StepResult("failed", "max_micro_steps", micro_steps, 1, last_observation)

    def _observe(self, run_id: str, step_id: str, task_id: str, phase: str, prev: Observation | None, cfg: ExecutorConfig) -> Observation:
        capture = self.bridge.autopilot_capture(max_width=cfg.screenshot_width, quality=cfg.screenshot_quality)
        image_b64 = capture.get("image_base64") or ""
        image_bytes = b""
        if image_b64:
            try:
                image_bytes = base64.b64decode(image_b64)
            except Exception:
                image_bytes = image_b64.encode("utf-8")
        digest = hashlib.sha256(image_bytes).hexdigest() if image_bytes else ""
        obs = Observation(
            hash=digest,
            width=int(capture.get("width") or 0),
            height=int(capture.get("height") or 0),
            ts=time.time(),
        )
        changed = bool(prev and prev.hash and obs.hash and prev.hash != obs.hash)
        emit(
            run_id,
            "observation_captured",
            "Снимок экрана",
            {
                "step_id": step_id,
                "phase": phase,
                "hash": obs.hash,
                "changed": changed,
                "width": obs.width,
                "height": obs.height,
            },
            task_id=task_id,
            step_id=step_id,
        )
        return obs

    def _propose_action(self, run: dict, step: dict, task: dict, obs: Observation, last_action: str | None) -> tuple[dict, dict[str, str]]:
        request = self._build_llm_request(run, step, task, obs, last_action)
        brain = self.brain or get_brain()
        response = brain.call(request, type("ctx", (), {"run": run, "task": task, "plan_step": step, "settings": run.get("settings") or {}}))

        if response.status == "budget_exceeded":
            raise RuntimeError("budget_exceeded")

        if response.status != "ok":
            raise RuntimeError(response.error_type or "llm_failed")

        parsed = self._parse_action_payload(response)
        return parsed, {"provider": response.provider, "reason": response.route_reason}

    def _build_llm_request(self, run: dict, step: dict, task: dict, obs: Observation, last_action: str | None) -> LLMRequest:
        step_inputs = step.get("inputs") or {}
        payload = {
            "user_goal": run.get("query_text"),
            "step": {
                "title": step.get("title"),
                "kind": step.get("kind"),
                "success_criteria": step.get("success_criteria"),
                "inputs": step_inputs,
            },
            "observation": {
                "screen_hash": obs.hash,
                "screen_width": obs.width,
                "screen_height": obs.height,
            },
            "last_action": last_action,
        }

        context_items = [
            ContextItem(
                content=run.get("query_text") or "",
                source_type="user_prompt",
                sensitivity="personal",
                provenance=f"run:{run.get('id')}",
            ),
            ContextItem(
                content={"step": payload["step"], "last_action": last_action},
                source_type="system_note",
                sensitivity="personal",
                provenance=f"step:{step.get('id')}",
            ),
            ContextItem(
                content=payload["observation"],
                source_type="system_note",
                sensitivity="personal",
                provenance="observation_summary",
            ),
        ]

        def render_messages(items: list[ContextItem]) -> list[dict[str, Any]]:
            user_goal = payload["user_goal"]
            step_payload = payload["step"]
            obs_payload = payload["observation"]
            last_action_payload = last_action
            for item in items:
                if item.source_type == "user_prompt":
                    user_goal = item.content
                elif item.source_type == "system_note" and isinstance(item.content, dict) and "step" in item.content:
                    step_payload = item.content.get("step", step_payload)
                    last_action_payload = item.content.get("last_action")
                elif item.source_type == "system_note" and isinstance(item.content, dict) and "screen_hash" in item.content:
                    obs_payload = item.content

            model_input = {
                "user_goal": user_goal,
                "step": step_payload,
                "observation": obs_payload,
                "last_action": last_action_payload,
                "constraints": {
                    "one_action_only": True,
                    "no_shell": True,
                    "no_batch": True,
                },
            }
            return [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(model_input, ensure_ascii=False)},
            ]

        return LLMRequest(
            purpose="computer_micro_plan",
            task_kind="autopilot",
            context_items=context_items,
            render_messages=render_messages,
            preferred_model_kind="chat",
            temperature=0.2,
            max_tokens=200,
            json_schema=_MICRO_ACTION_SCHEMA,
            run_id=run.get("id"),
            task_id=task.get("id"),
            step_id=step.get("id"),
        )

    def _parse_action_payload(self, response: LLMResponse) -> dict:
        raw = (response.text or "").strip()
        if not raw:
            return {"type": "wait", "ms": 500}
        try:
            payload = json.loads(raw)
        except Exception:
            payload = None

        if payload is None:
            payload = self._extract_json(raw)

        if not isinstance(payload, dict):
            raise RuntimeError("Invalid action payload")

        action = self._normalize_action(payload)
        if not action:
            raise RuntimeError("Invalid action payload")
        return action

    def _extract_json(self, text: str) -> dict | None:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            return None

    def _normalize_action(self, payload: dict) -> dict | None:
        action_type = payload.get("action_type") or payload.get("type")
        if action_type not in _ALLOWED_ACTIONS:
            return None
        if action_type == "done":
            return {"type": "done"}

        action: dict[str, Any] = {"type": action_type}
        if action_type in {"move_mouse", "click", "double_click"}:
            x = payload.get("x")
            y = payload.get("y")
            if x is None or y is None:
                return None
            action["x"] = int(x)
            action["y"] = int(y)
            if payload.get("button"):
                action["button"] = payload.get("button")
        elif action_type == "drag":
            for key in ("start_x", "start_y", "end_x", "end_y"):
                if payload.get(key) is None:
                    return None
            action["start_x"] = int(payload["start_x"])
            action["start_y"] = int(payload["start_y"])
            action["end_x"] = int(payload["end_x"])
            action["end_y"] = int(payload["end_y"])
        elif action_type == "type":
            text = payload.get("text")
            if not isinstance(text, str):
                return None
            action["text"] = text
        elif action_type == "key":
            keys = payload.get("keys") or payload.get("key")
            if isinstance(keys, str):
                keys = [keys]
            if not keys:
                return None
            action["keys"] = [str(k) for k in keys]
        elif action_type == "scroll":
            dy = payload.get("dy")
            if dy is None:
                return None
            action["dy"] = int(dy)
        elif action_type == "wait":
            action["ms"] = int(payload.get("ms") or 500)
        return action

    def _execute_action(self, action: dict, obs: Observation, cfg: ExecutorConfig) -> bool:
        action_type = action.get("type")
        if cfg.dry_run:
            return True
        if action_type == "wait":
            return True
        try:
            self.bridge.autopilot_act(action, image_width=obs.width, image_height=obs.height)
        except Exception:
            return False
        return True

    def _verify_progress(self, run_id: str, step_id: str, task_id: str, before: Observation, after: Observation, cfg: ExecutorConfig) -> tuple[str, dict, Observation]:
        if before.hash and after.hash and before.hash != after.hash:
            return "pass_progress", {"change": "hash_changed"}, after

        waited_ms = 0
        current = after
        while waited_ms < cfg.wait_timeout_ms:
            time.sleep(cfg.wait_poll_ms / 1000)
            waited_ms += cfg.wait_poll_ms
            current = self._observe(run_id, step_id, task_id, "wait", before, cfg)
            if before.hash and current.hash and before.hash != current.hash:
                emit(
                    run_id,
                    "step_waiting",
                    "Ожидание загрузки",
                    {"reason": "screen_change", "waited_ms": waited_ms},
                    task_id=task_id,
                    step_id=step_id,
                )
                return "pass_progress", {"waited_ms": waited_ms}, current

        emit(
            run_id,
            "step_waiting",
            "Ожидание без изменений",
            {"reason": "no_change", "waited_ms": waited_ms},
            task_id=task_id,
            step_id=step_id,
        )
        return "timeout", {"waited_ms": waited_ms}, current

    def _summarize_action(self, action: dict) -> str:
        action_type = action.get("type")
        if action_type == "type":
            text = action.get("text") or ""
            return f"type:{len(text)} chars"
        if action_type == "key":
            keys = action.get("keys") or []
            return "key:" + "+".join(keys)
        if action_type in {"click", "double_click", "move_mouse"}:
            return f"{action_type}({action.get('x')},{action.get('y')})"
        if action_type == "drag":
            return f"drag({action.get('start_x')},{action.get('start_y')})->({action.get('end_x')},{action.get('end_y')})"
        if action_type == "scroll":
            return f"scroll({action.get('dy')})"
        if action_type == "wait":
            return f"wait({action.get('ms')}ms)"
        return str(action_type)

    def _request_step_approval(self, run: dict, step: dict, task: dict) -> bool:
        run_id = run["id"]
        task_id = task["id"]
        step_id = step["id"]
        preview = {
            "title": step.get("title"),
            "kind": step.get("kind"),
            "danger_flags": step.get("danger_flags") or [],
        }
        approval = store.create_approval(
            run_id=run_id,
            task_id=task_id,
            scope="computer_step",
            title="Подтверждение действия",
            description="Требуется подтверждение для выполнения шага на компьютере.",
            proposed_actions=[preview],
        )
        emit(
            run_id,
            "approval_requested",
            "Запрошено подтверждение",
            {
                "approval_id": approval["id"],
                "scope": approval["scope"],
                "title": approval["title"],
                "description": approval["description"],
                "proposed_actions": approval["proposed_actions"],
            },
            task_id=task_id,
            step_id=step_id,
        )
        emit(
            run_id,
            "step_paused_for_approval",
            "Шаг ожидает подтверждение",
            {"approval_id": approval["id"], "preview": preview},
            task_id=task_id,
            step_id=step_id,
        )

        store.update_task_status(task_id, "waiting_approval")
        approval = self._wait_for_approval(run_id, approval["id"])
        emit(
            run_id,
            "approval_resolved",
            "Подтверждение завершено",
            {
                "approval_id": approval["id"],
                "status": approval["status"],
                "decision": approval.get("decision"),
            },
            task_id=task_id,
            step_id=step_id,
        )
        if approval["status"] != "approved":
            emit(
                run_id,
                "approval_rejected",
                "Подтверждение отклонено",
                {"approval_id": approval["id"]},
                task_id=task_id,
                step_id=step_id,
            )
            return False

        emit(
            run_id,
            "approval_approved",
            "Подтверждение принято",
            {"approval_id": approval["id"]},
            task_id=task_id,
            step_id=step_id,
        )
        store.update_task_status(task_id, "running")
        return True

    def _request_user_help(self, run: dict, step: dict, task: dict, reason: str) -> bool:
        run_id = run["id"]
        task_id = task["id"]
        step_id = step["id"]
        preview = {
            "title": step.get("title"),
            "kind": step.get("kind"),
            "reason": reason,
        }
        approval = store.create_approval(
            run_id=run_id,
            task_id=task_id,
            scope="executor_help",
            title="Нужно вмешательство",
            description="Executor не может продолжить без подтверждения пользователя.",
            proposed_actions=[preview],
        )
        emit(
            run_id,
            "approval_requested",
            "Запрошено подтверждение",
            {
                "approval_id": approval["id"],
                "scope": approval["scope"],
                "title": approval["title"],
                "description": approval["description"],
                "proposed_actions": approval["proposed_actions"],
            },
            task_id=task_id,
            step_id=step_id,
        )
        emit(
            run_id,
            "step_paused_for_approval",
            "Ожидание решения пользователя",
            {"approval_id": approval["id"], "preview": preview},
            task_id=task_id,
            step_id=step_id,
        )

        store.update_task_status(task_id, "waiting_approval")
        approval = self._wait_for_approval(run_id, approval["id"])
        emit(
            run_id,
            "approval_resolved",
            "Подтверждение завершено",
            {
                "approval_id": approval["id"],
                "status": approval["status"],
                "decision": approval.get("decision"),
            },
            task_id=task_id,
            step_id=step_id,
        )
        if approval["status"] != "approved":
            emit(
                run_id,
                "approval_rejected",
                "Подтверждение отклонено",
                {"approval_id": approval["id"]},
                task_id=task_id,
                step_id=step_id,
            )
            return False

        emit(
            run_id,
            "approval_approved",
            "Подтверждение принято",
            {"approval_id": approval["id"]},
            task_id=task_id,
            step_id=step_id,
        )
        store.update_task_status(task_id, "running")
        return True

    def _wait_for_approval(self, run_id: str, approval_id: str) -> dict:
        while True:
            approval = store.get_approval(approval_id)
            if not approval:
                raise RuntimeError("Подтверждение не найдено")
            if approval["status"] in ("approved", "rejected", "expired"):
                return approval
            run = store.get_run(run_id)
            if run and run.get("status") == "canceled":
                return store.update_approval_status(approval_id, "expired", "system") or approval
            time.sleep(0.5)
