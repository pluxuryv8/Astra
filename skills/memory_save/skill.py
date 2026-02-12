from __future__ import annotations

from core.event_bus import emit
from core.skills.result_types import SkillResult
from memory import store


def run(inputs: dict, ctx) -> SkillResult:
    run_id = ctx.run["id"]
    raw_content = inputs.get("content") if isinstance(inputs, dict) else None
    content = raw_content.strip() if isinstance(raw_content, str) else ""
    title = inputs.get("title") if isinstance(inputs, dict) and isinstance(inputs.get("title"), str) else None
    tags = inputs.get("tags") if isinstance(inputs, dict) and isinstance(inputs.get("tags"), list) else None
    if not content:
        content = (ctx.run.get("query_text") or "").strip()

    emit(
        run_id,
        "memory_save_requested",
        "Запрошено сохранение в память",
        {"from": "user_command", "preview_len": len(content)},
        task_id=ctx.task.get("id"),
        step_id=ctx.plan_step.get("id"),
    )

    memory = store.create_user_memory(title, content, tags, source="user_command")

    emit(
        run_id,
        "memory_saved",
        "Память сохранена",
        {"memory_id": memory["id"], "title": memory["title"], "len": len(memory["content"]), "tags_count": len(memory["tags"] or [])},
        task_id=ctx.task.get("id"),
        step_id=ctx.plan_step.get("id"),
    )

    return SkillResult(
        what_i_did="Запись пользователя сохранена в постоянную память.",
        confidence=1.0,
    )
