from __future__ import annotations

import os
from urllib.parse import urlparse, urlunparse

DEFAULT_API_PORT = "8055"
DEFAULT_BRIDGE_PORT = "43124"
DEFAULT_API_BASE_URL = f"http://127.0.0.1:{DEFAULT_API_PORT}/api/v1"
DEFAULT_BRIDGE_BASE_URL = f"http://127.0.0.1:{DEFAULT_BRIDGE_PORT}"


def normalize_base_url(value: str, label: str, required_prefix: str | None = None) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"invalid {label}: {value}")
    path = parsed.path.rstrip("/")
    if required_prefix and not path.startswith(required_prefix):
        raise ValueError(f"invalid {label} path: expected prefix {required_prefix}, got {path or '/'}")
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def resolve_api_base_url(env: dict[str, str] | None = None) -> str:
    env_map = env or os.environ
    candidate = env_map.get("ASTRA_API_BASE_URL") or env_map.get("ASTRA_API_BASE")
    if not candidate:
        candidate = f"http://127.0.0.1:{env_map.get('ASTRA_API_PORT', DEFAULT_API_PORT)}/api/v1"
    return normalize_base_url(candidate, "ASTRA_API_BASE_URL", "/api/v1")


def resolve_bridge_base_url(env: dict[str, str] | None = None) -> str:
    env_map = env or os.environ
    candidate = env_map.get("ASTRA_BRIDGE_BASE_URL")
    if not candidate:
        bridge_port = env_map.get("ASTRA_BRIDGE_PORT") or env_map.get("ASTRA_DESKTOP_BRIDGE_PORT")
        if bridge_port:
            candidate = f"http://127.0.0.1:{bridge_port}"
    if not candidate:
        candidate = DEFAULT_BRIDGE_BASE_URL
    return normalize_base_url(candidate, "ASTRA_BRIDGE_BASE_URL")


def port_from_url(url: str) -> int | None:
    parsed = urlparse(url)
    if parsed.port is not None:
        return parsed.port
    if parsed.scheme == "https":
        return 443
    if parsed.scheme == "http":
        return 80
    return None

