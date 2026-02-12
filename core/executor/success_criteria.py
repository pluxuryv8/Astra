from __future__ import annotations

import re
from typing import Any


def parse_success_criteria(text: str | None) -> list[dict[str, Any]]:
    if not text:
        return []
    checks: list[dict[str, Any]] = []
    parts = re.split(r"[\n;]+", text)
    for raw in parts:
        line = raw.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered.startswith("contains:"):
            value = line.split(":", 1)[1].strip()
            if value:
                checks.append({"type": "contains_text", "value": value, "case_sensitive": False})
        elif lowered.startswith("not_contains:") or lowered.startswith("not contains:"):
            value = line.split(":", 1)[1].strip()
            if value:
                checks.append({"type": "not_contains_text", "value": value})
        elif lowered.startswith("regex:"):
            value = line.split(":", 1)[1].strip()
            if value:
                checks.append({"type": "regex_match", "pattern": value})
    return checks


def normalize_success_checks(success_checks: Any, success_criteria: str | None) -> list[dict[str, Any]]:
    if isinstance(success_checks, list) and success_checks:
        return [check for check in success_checks if isinstance(check, dict)]
    return parse_success_criteria(success_criteria)


def _contains(text: str, value: str, case_sensitive: bool) -> bool:
    if case_sensitive:
        return value in text
    return value.lower() in text.lower()


def _eval_check(check: dict[str, Any], text: str) -> bool:
    kind = check.get("type")
    if kind == "contains_text":
        value = str(check.get("value") or "")
        if not value:
            return False
        case_sensitive = bool(check.get("case_sensitive"))
        return _contains(text, value, case_sensitive)
    if kind == "not_contains_text":
        value = str(check.get("value") or "")
        if not value:
            return False
        return value.lower() not in text.lower()
    if kind == "regex_match":
        pattern = str(check.get("pattern") or "")
        if not pattern:
            return False
        try:
            return re.search(pattern, text) is not None
        except re.error:
            return False
    if kind == "any_of":
        nested = check.get("checks") or []
        if not isinstance(nested, list):
            return False
        return any(_eval_check(item, text) for item in nested if isinstance(item, dict))
    if kind == "all_of":
        nested = check.get("checks") or []
        if not isinstance(nested, list):
            return False
        return all(_eval_check(item, text) for item in nested if isinstance(item, dict))
    return False


def evaluate_success_checks(checks: list[dict[str, Any]], text: str) -> bool:
    if not checks:
        return False
    return all(_eval_check(check, text) for check in checks)
