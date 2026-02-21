from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlparse

SOURCE_TYPES = {
    "user_prompt",
    "web_page_text",
    "telegram_text",
    "file_content",
    "app_ui_text",
    "screenshot_text",
    "system_note",
    "internal_summary",
}

SENSITIVITIES = {
    "public",
    "personal",
    "financial",
    "confidential",
}

ROUTE_LOCAL = "LOCAL"


@dataclass
class ContextItem:
    content: Any
    source_type: str
    sensitivity: str
    provenance: str | None = None

    def __post_init__(self) -> None:
        if self.source_type not in SOURCE_TYPES:
            raise ValueError(f"Unsupported source_type: {self.source_type}")
        if self.sensitivity not in SENSITIVITIES:
            raise ValueError(f"Unsupported sensitivity: {self.sensitivity}")


@dataclass
class PolicyFlags:
    strict_local: bool = True
    max_item_chars: int = 2000

    @classmethod
    def from_settings(cls, settings: dict | None) -> "PolicyFlags":
        cfg = (settings or {}).get("privacy") or (settings or {}).get("routing") or {}
        return cls(
            strict_local=bool(cfg.get("strict_local", True)),
            max_item_chars=int(cfg.get("max_item_chars", 2000)),
        )


@dataclass
class RoutingDecision:
    route: str
    reason: str
    required_approval: str | None
    redaction_plan: dict[str, Any]


@dataclass
class SanitizationResult:
    items: list[ContextItem]
    removed_counts_by_source: dict[str, int]
    redacted_count: int
    total_chars: int
    truncated: bool


_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passphrase)\s*[:=]\s*([^\s\"']+)"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-\._~\+\/]+=*"),
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
]


def _redact_secrets(text: str) -> tuple[str, int]:
    total = 0
    value = text
    for pattern in _SECRET_PATTERNS:
        value, count = pattern.subn("[REDACTED]", value)
        total += count
    return value, total


def _estimate_length(value: Any) -> int:
    if isinstance(value, str):
        return len(value)
    if isinstance(value, dict):
        total = 0
        for item in value.values():
            total += _estimate_length(item)
        return total
    if isinstance(value, list):
        return sum(_estimate_length(item) for item in value)
    return len(str(value))


def _truncate_string(value: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value
    return value[:max_chars]


def _sanitize_value(value: Any, max_chars: int) -> tuple[Any, int, bool]:
    if isinstance(value, str):
        redacted, count = _redact_secrets(value)
        truncated = len(redacted) > max_chars
        return _truncate_string(redacted, max_chars), count, truncated
    if isinstance(value, dict):
        redacted_total = 0
        truncated_any = False
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(item, str):
                redacted, count = _redact_secrets(item)
                redacted_total += count
                truncated_any = truncated_any or len(redacted) > max_chars
                sanitized[key] = _truncate_string(redacted, max_chars)
            else:
                sanitized[key] = item
        return sanitized, redacted_total, truncated_any
    if isinstance(value, list):
        redacted_total = 0
        truncated_any = False
        sanitized_list = []
        for item in value:
            if isinstance(item, str):
                redacted, count = _redact_secrets(item)
                redacted_total += count
                truncated_any = truncated_any or len(redacted) > max_chars
                sanitized_list.append(_truncate_string(redacted, max_chars))
            else:
                sanitized_list.append(item)
        return sanitized_list, redacted_total, truncated_any
    return value, 0, False


def sanitize_context_items(items: list[ContextItem], allow_financial_file: bool, flags: PolicyFlags) -> SanitizationResult:
    removed_counts: dict[str, int] = {key: 0 for key in SOURCE_TYPES}
    sanitized_items: list[ContextItem] = []
    redacted_total = 0
    total_chars = 0
    truncated_any = False

    for item in items:
        if item.source_type in {"telegram_text", "screenshot_text"}:
            removed_counts[item.source_type] += 1
            continue
        if item.source_type == "file_content" and item.sensitivity == "financial" and not allow_financial_file:
            removed_counts[item.source_type] += 1
            continue

        sanitized_content, redacted_count, truncated = _sanitize_value(item.content, flags.max_item_chars)
        redacted_total += redacted_count
        truncated_any = truncated_any or truncated

        item_len = _estimate_length(sanitized_content)
        if item_len <= 0:
            removed_counts[item.source_type] += 1
            continue

        total_chars += item_len
        sanitized_items.append(
            ContextItem(
                content=sanitized_content,
                source_type=item.source_type,
                sensitivity=item.sensitivity,
                provenance=item.provenance,
            )
        )

    return SanitizationResult(
        items=sanitized_items,
        removed_counts_by_source=removed_counts,
        redacted_count=redacted_total,
        total_chars=total_chars,
        truncated=truncated_any,
    )


def summarize_items(items: Iterable[ContextItem]) -> dict[str, Any]:
    counts_by_source: dict[str, int] = {key: 0 for key in SOURCE_TYPES}
    counts_by_sensitivity: dict[str, int] = {key: 0 for key in SENSITIVITIES}
    for item in items:
        counts_by_source[item.source_type] = counts_by_source.get(item.source_type, 0) + 1
        counts_by_sensitivity[item.sensitivity] = counts_by_sensitivity.get(item.sensitivity, 0) + 1
    return {
        "by_source_type": counts_by_source,
        "by_sensitivity": counts_by_sensitivity,
    }


def decide_route(intent: str | None, items: list[ContextItem], flags: PolicyFlags, approved_scopes: set[str] | None = None) -> RoutingDecision:
    if flags.strict_local:
        return RoutingDecision(route=ROUTE_LOCAL, reason="strict_local", required_approval=None, redaction_plan={})

    has_telegram = any(item.source_type == "telegram_text" for item in items)
    if has_telegram:
        return RoutingDecision(route=ROUTE_LOCAL, reason="telegram_text_present", required_approval=None, redaction_plan={"drop": ["telegram_text"]})

    has_screenshot_text = any(item.source_type == "screenshot_text" for item in items)
    if has_screenshot_text:
        return RoutingDecision(route=ROUTE_LOCAL, reason="screenshot_text_present", required_approval=None, redaction_plan={"drop": ["screenshot_text"]})

    return RoutingDecision(route=ROUTE_LOCAL, reason="default_local", required_approval=None, redaction_plan={})


def _is_local_endpoint(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return False
    return host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def resolve_llm_settings(settings: dict, route: str) -> dict:
    llm_local = settings.get("llm_local") or settings.get("llm") or {}
    provider = str(llm_local.get("provider") or "local").strip().lower()
    endpoint = llm_local.get("base_url") or llm_local.get("endpoint")

    if provider not in {"local", "ollama"}:
        raise RuntimeError("Only local LLM provider is supported")
    if endpoint and not _is_local_endpoint(str(endpoint)):
        raise RuntimeError("Only local LLM endpoint is allowed")
    return llm_local
