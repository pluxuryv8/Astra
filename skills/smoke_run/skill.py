from __future__ import annotations

import base64
import hashlib
import time
from typing import Any

from core.bridge.desktop_bridge import DesktopBridge
from core.skills.result_types import FactCandidate, SkillResult


def _hash_image(image_base64: str) -> str:
    raw = base64.b64decode(image_base64.encode("utf-8"))
    return hashlib.sha256(raw).hexdigest()


def _event(message: str, current: int, total: int) -> dict[str, Any]:
    return {
        "message": message,
        "progress": {"current": current, "total": total, "unit": "шаг"},
    }


def run(inputs: dict, ctx) -> SkillResult:
    bridge = DesktopBridge()
    max_width = int(inputs.get("max_width") or 1280)
    quality = int(inputs.get("quality") or 60)
    scroll_dy = int(inputs.get("scroll_dy") or -180)

    events: list[dict[str, Any]] = []

    try:
        events.append(_event("Снимаю скриншот до действий", 1, 5))
        before = bridge.autopilot_capture(max_width=max_width, quality=quality)
        before_hash = _hash_image(before.get("image_base64", ""))
        width = int(before.get("width") or 0)
        height = int(before.get("height") or 0)

        if width > 0 and height > 0:
            events.append(_event("Двигаю курсор в безопасную область", 2, 5))
            bridge.autopilot_act(
                {"type": "move_mouse", "x": width // 2, "y": height // 2},
                image_width=width,
                image_height=height,
            )

        events.append(_event("Делаю безопасную прокрутку", 3, 5))
        bridge.autopilot_act(
            {"type": "scroll", "dy": scroll_dy},
            image_width=max(width, 1),
            image_height=max(height, 1),
        )
        time.sleep(0.2)

        events.append(_event("Снимаю скриншот после действий", 4, 5))
        after = bridge.autopilot_capture(max_width=max_width, quality=quality)
        after_hash = _hash_image(after.get("image_base64", ""))

    except Exception as exc:  # pragma: no cover - runtime path
        raise RuntimeError(f"bridge_error: {exc}") from exc

    changed = before_hash != after_hash
    events.append(_event(f"Проверка: hash_changed = {'да' if changed else 'нет'}", 5, 5))

    facts = [
        FactCandidate(key="smoke.hash_before", value=before_hash, confidence=1.0),
        FactCandidate(key="smoke.hash_after", value=after_hash, confidence=1.0),
        FactCandidate(key="smoke.hash_changed", value=changed, confidence=1.0),
    ]

    return SkillResult(
        what_i_did="Собран smoke-отчёт: наблюдение, безопасные действия, проверка изменений экрана.",
        events=events,
        facts=facts,
        confidence=0.8,
    )
