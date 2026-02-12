from __future__ import annotations

from typing import Any

APPROVAL_TYPES = {
    "SEND",
    "DELETE",
    "PAYMENT",
    "PUBLISH",
    "ACCOUNT_CHANGE",
    "CLOUD_FINANCIAL",
}

DANGER_TO_APPROVAL = {
    "send_message": "SEND",
    "delete_file": "DELETE",
    "payment": "PAYMENT",
    "publish": "PUBLISH",
    "account_settings": "ACCOUNT_CHANGE",
    "password": "ACCOUNT_CHANGE",
}

_APPROVAL_RISK = {
    "SEND": "Отправка сообщения/публикация",
    "DELETE": "Удаление или необратимое изменение",
    "PAYMENT": "Оплата/перевод/подписка",
    "PUBLISH": "Публикация контента",
    "ACCOUNT_CHANGE": "Изменение настроек аккаунта или безопасности",
    "CLOUD_FINANCIAL": "Передача финансовых данных в облако",
}

_SUGGESTED_ACTION = {
    "SEND": "Проверьте получателя и текст сообщения",
    "DELETE": "Подтвердите список удаляемых объектов",
    "PAYMENT": "Подтвердите сумму и получателя",
    "PUBLISH": "Подтвердите площадку и содержание",
    "ACCOUNT_CHANGE": "Подтвердите изменение настроек аккаунта",
    "CLOUD_FINANCIAL": "Подтвердите отправку финансовых данных в облако",
}


def approval_type_from_flags(flags: list[str] | None) -> str:
    flags = flags or []
    priority = ["payment", "delete_file", "send_message", "publish", "account_settings", "password"]
    for flag in priority:
        if flag in flags:
            return DANGER_TO_APPROVAL[flag]
    return "ACCOUNT_CHANGE"


def build_preview_for_step(run: dict, step: dict, approval_type: str) -> dict[str, Any]:
    summary = step.get("title") or run.get("query_text") or "Опасное действие"
    details: dict[str, Any] = {}

    if approval_type == "SEND":
        details = {
            "target_app": step.get("inputs", {}).get("app") or "UNKNOWN",
            "message_text": step.get("inputs", {}).get("message_text")
            or step.get("inputs", {}).get("text")
            or "UNKNOWN",
            "destination_hint": step.get("inputs", {}).get("destination") or "UNKNOWN",
        }
    elif approval_type == "DELETE":
        details = {
            "items": step.get("inputs", {}).get("items") or "UNKNOWN",
            "impact": step.get("inputs", {}).get("impact") or "UNKNOWN",
        }
    elif approval_type == "PAYMENT":
        details = {
            "amount": step.get("inputs", {}).get("amount") or "UNKNOWN",
            "currency": step.get("inputs", {}).get("currency") or "UNKNOWN",
            "merchant": step.get("inputs", {}).get("merchant") or "UNKNOWN",
        }
    elif approval_type == "PUBLISH":
        content = step.get("inputs", {}).get("content") or "UNKNOWN"
        if isinstance(content, str) and len(content) > 120:
            content = content[:120] + "…"
        details = {
            "platform_hint": step.get("inputs", {}).get("platform") or "UNKNOWN",
            "content_preview": content,
        }
    elif approval_type == "ACCOUNT_CHANGE":
        details = {
            "change": step.get("inputs", {}).get("change") or "UNKNOWN",
        }

    preview = {
        "summary": summary,
        "details": details,
        "risk": _APPROVAL_RISK.get(approval_type, "Опасное действие"),
        "suggested_user_action": _SUGGESTED_ACTION.get(approval_type, "Подтвердите выполнение"),
        "expires_in_ms": None,
    }
    return preview


def build_cloud_financial_preview(items: list[dict[str, Any]], redaction_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    files = []
    for item in items:
        if item.get("source_type") == "file_content":
            files.append(item.get("provenance") or "UNKNOWN")
    details = {
        "file_paths": files or ["UNKNOWN"],
        "content": "выжимка/фрагменты",
        "redaction_summary": redaction_summary or {},
    }
    return {
        "summary": "Отправка финансовых данных в облако",
        "details": details,
        "risk": _APPROVAL_RISK["CLOUD_FINANCIAL"],
        "suggested_user_action": _SUGGESTED_ACTION["CLOUD_FINANCIAL"],
        "expires_in_ms": None,
    }


def preview_summary(preview: dict[str, Any]) -> str:
    summary = preview.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary
    return "Approval required"


def proposed_actions_from_preview(approval_type: str, preview: dict[str, Any]) -> list[dict[str, Any]]:
    action: dict[str, Any] = {
        "type": approval_type,
        "summary": preview.get("summary") or "Approval required",
    }
    details = preview.get("details") or {}
    if isinstance(details, dict):
        if "message_text" in details and isinstance(details.get("message_text"), str):
            action["text"] = details.get("message_text")
    return [action]
