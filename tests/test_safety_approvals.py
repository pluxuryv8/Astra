from __future__ import annotations

from core.safety.approvals import build_preview_for_step


def test_send_preview_includes_message_text():
    run = {"query_text": "Отправь сообщение"}
    step = {
        "title": "Send message",
        "inputs": {
            "app": "telegram",
            "message_text": "hello",
            "destination": "@alice",
        },
    }

    preview = build_preview_for_step(run, step, "SEND")

    assert preview["details"]["target_app"] == "telegram"
    assert preview["details"]["message_text"] == "hello"
    assert preview["details"]["destination_hint"] == "@alice"
