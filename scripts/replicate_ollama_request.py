from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay a captured Ollama /api/chat payload.")
    parser.add_argument("artifact", help="Path to local_llm_failures artifact JSON")
    parser.add_argument(
        "--base-url",
        default=os.getenv("ASTRA_LLM_LOCAL_BASE_URL", "http://127.0.0.1:11434"),
        help="Ollama base URL (default: ASTRA_LLM_LOCAL_BASE_URL or http://127.0.0.1:11434)",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")
    args = parser.parse_args()

    artifact_path = Path(args.artifact)
    if not artifact_path.exists():
        print(f"Artifact not found: {artifact_path}")
        return 2

    data = json.loads(artifact_path.read_text(encoding="utf-8"))
    payload = data.get("request_payload")
    if not payload:
        print("Artifact missing request_payload")
        return 2

    url = args.base_url.rstrip("/") + "/api/chat"
    resp = httpx.post(url, json=payload, timeout=args.timeout)
    print(f"POST {url} -> {resp.status_code}")
    print(resp.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
