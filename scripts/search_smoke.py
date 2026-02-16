from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.providers.search_client import build_search_client


def _one_line(value: object) -> str:
    text = str(value or "").strip()
    return " ".join(text.split())


def main() -> None:
    settings = {"search": {"provider": "ddgs"}}
    client = build_search_client(settings)
    results = client.search("Esenin poems")[:3]

    print(f"results={len(results)}")
    for idx, item in enumerate(results, start=1):
        title = _one_line(item.get("title")) or "(no title)"
        url = _one_line(item.get("url")) or "(no url)"
        snippet = _one_line(item.get("snippet")) or "(no snippet)"
        print(f"{idx}. {title}")
        print(f"   url: {url}")
        print(f"   snippet: {snippet}")


if __name__ == "__main__":
    main()
