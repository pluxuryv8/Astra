from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

"""
Lightweight local bridge inspired by Letta memory blocks:
- tmp/letta/letta/schemas/block.py
- tmp/letta/letta/schemas/memory.py

Stores episodic memories in SQLite and provides retrieval/update APIs that can be
used directly from tone analysis and prompt assembly.
"""


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _tokens(value: str) -> set[str]:
    return {part for part in re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_+-]+", _normalized(value)) if len(part) >= 3}


def _default_db_path() -> Path:
    override = os.getenv("ASTRA_LETTA_DB_PATH", "").strip()
    if override:
        return Path(override)
    return Path(".astra") / "letta_episodic.sqlite3"


def _history_to_query(history: list[dict[str, Any]], limit: int = 5) -> str:
    lines: list[str] = []
    for item in history[-12:]:
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "").lower() != "user":
            continue
        content = item.get("content")
        if isinstance(content, str) and content.strip():
            lines.append(content.strip())
    return "\n".join(lines[-limit:])


@dataclass(slots=True)
class MemoryBlock:
    label: str
    value: str
    summary: str
    tags: list[str]
    metadata: dict[str, Any]
    created_at: str


class LettaBridge:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or _default_db_path()
        self._lock = threading.Lock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS episodic_blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    digest TEXT NOT NULL UNIQUE,
                    label TEXT NOT NULL,
                    value TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    meta_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_episodic_created_at
                ON episodic_blocks(created_at DESC);
                """
            )

    def retrieve(
        self,
        history: list[dict[str, Any]] | None,
        *,
        query: str | None = None,
        limit: int = 3,
        scan_limit: int = 200,
    ) -> dict[str, Any]:
        history = history if isinstance(history, list) else []
        query_text = (query or "").strip() or _history_to_query(history)
        query_tokens = _tokens(query_text)

        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT label, value, summary, tags_json, meta_json, created_at
                FROM episodic_blocks
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, scan_limit),),
            ).fetchall()

        scored: list[tuple[float, sqlite3.Row]] = []
        for index, row in enumerate(rows):
            value = str(row["value"] or "")
            summary = str(row["summary"] or "")
            hay_tokens = _tokens(f"{summary} {value}")
            overlap = len(query_tokens.intersection(hay_tokens)) if query_tokens else 0
            recency = max(0.0, 1.0 - (index / max(1, len(rows))))
            score = float(overlap) + recency * 0.35
            if query_tokens and overlap == 0:
                continue
            scored.append((score, row))

        if not query_tokens:
            scored = [(1.0, row) for row in rows]

        scored.sort(key=lambda item: item[0], reverse=True)
        selected = scored[: max(1, limit)]

        blocks: list[dict[str, Any]] = []
        for score, row in selected:
            try:
                tags = json.loads(str(row["tags_json"] or "[]"))
            except json.JSONDecodeError:
                tags = []
            try:
                metadata = json.loads(str(row["meta_json"] or "{}"))
            except json.JSONDecodeError:
                metadata = {}

            blocks.append(
                {
                    "label": str(row["label"] or "episode"),
                    "value": str(row["value"] or ""),
                    "summary": str(row["summary"] or ""),
                    "tags": tags if isinstance(tags, list) else [],
                    "metadata": metadata if isinstance(metadata, dict) else {},
                    "created_at": str(row["created_at"] or ""),
                    "score": round(score, 4),
                }
            )

        summary = "\n".join(f"- {item['summary']}" for item in blocks if item.get("summary"))
        return {
            "query": query_text,
            "hit_count": len(blocks),
            "blocks": blocks,
            "summary": summary[:1800],
        }

    def update(
        self,
        *,
        user_message: str,
        history: list[dict[str, Any]] | None = None,
        tone_analysis: dict[str, Any] | None = None,
        crew_result: dict[str, Any] | None = None,
        assistant_message: str | None = None,
    ) -> dict[str, Any]:
        history = history if isinstance(history, list) else []
        text = (user_message or "").strip()
        if not text:
            return {"updated": False, "reason": "empty_user_message"}

        tail = _history_to_query(history, limit=2)
        compact_assistant = (assistant_message or "").strip()

        memory_blob = "\n".join(part for part in [text, compact_assistant, tail] if part).strip()
        memory_blob = memory_blob[:2400]
        if not memory_blob:
            return {"updated": False, "reason": "empty_blob"}

        summary = re.sub(r"\s+", " ", text)[:240]
        digest = hashlib.sha1(memory_blob.encode("utf-8")).hexdigest()  # noqa: S324

        tags: list[str] = ["episodic"]
        tone_type = ""
        if isinstance(tone_analysis, dict):
            tone_type = str(tone_analysis.get("type") or "").strip().lower()
        if tone_type:
            tags.append(f"tone:{tone_type}")
        if isinstance(crew_result, dict) and str(crew_result.get("mode") or "") == "parallel":
            tags.append("parallel")

        metadata = {
            "tone": tone_type or None,
            "task_complex": bool((tone_analysis or {}).get("task_complex")) if isinstance(tone_analysis, dict) else False,
            "parallel_mode": str((crew_result or {}).get("mode") or "single"),
        }

        created_at = _utc_now()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO episodic_blocks (
                    digest, label, value, summary, tags_json, meta_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    digest,
                    "episode",
                    memory_blob,
                    summary,
                    json.dumps(tags, ensure_ascii=False),
                    json.dumps(metadata, ensure_ascii=False),
                    created_at,
                ),
            )
            created = cur.rowcount > 0
            max_items = max(10, int(os.getenv("ASTRA_LETTA_MAX_EPISODES", "300")))
            conn.execute(
                """
                DELETE FROM episodic_blocks
                WHERE id NOT IN (
                    SELECT id FROM episodic_blocks ORDER BY id DESC LIMIT ?
                )
                """,
                (max_items,),
            )

        return {
            "updated": created,
            "digest": digest,
            "summary": summary,
            "tags": tags,
            "created_at": created_at,
        }


_DEFAULT_BRIDGE: LettaBridge | None = None


def _get_bridge() -> LettaBridge:
    global _DEFAULT_BRIDGE
    desired = _default_db_path()
    if _DEFAULT_BRIDGE is None or _DEFAULT_BRIDGE.db_path != desired:
        _DEFAULT_BRIDGE = LettaBridge(desired)
    return _DEFAULT_BRIDGE


def retrieve(
    history: list[dict[str, Any]] | None,
    *,
    query: str | None = None,
    limit: int = 3,
) -> dict[str, Any]:
    return _get_bridge().retrieve(history, query=query, limit=limit)


def update(
    *,
    user_message: str,
    history: list[dict[str, Any]] | None = None,
    tone_analysis: dict[str, Any] | None = None,
    crew_result: dict[str, Any] | None = None,
    assistant_message: str | None = None,
) -> dict[str, Any]:
    return _get_bridge().update(
        user_message=user_message,
        history=history,
        tone_analysis=tone_analysis,
        crew_result=crew_result,
        assistant_message=assistant_message,
    )


def reset_for_tests(db_path: Path) -> LettaBridge:
    global _DEFAULT_BRIDGE
    _DEFAULT_BRIDGE = LettaBridge(db_path)
    return _DEFAULT_BRIDGE


__all__ = ["LettaBridge", "MemoryBlock", "retrieve", "update", "reset_for_tests"]
