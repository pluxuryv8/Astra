from __future__ import annotations

import json
from pathlib import Path

from core.event_bus import get_allowed_event_types


def test_event_types_match_schemas():
    root = Path(__file__).resolve().parents[1]
    schema_dir = root / "schemas" / "events"
    schema_files = {p.name[:-len(".schema.json")] for p in schema_dir.glob("*.schema.json")}

    event_schema = json.loads((root / "schemas" / "event.schema.json").read_text(encoding="utf-8"))
    enum_types = set(event_schema["properties"]["type"]["enum"])

    assert schema_files, "Не найдены schema файлы для событий"
    assert schema_files == enum_types
    assert schema_files == get_allowed_event_types()
