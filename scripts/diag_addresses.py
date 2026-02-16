#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

from lib.address_resolver import port_from_url, resolve_api_base_url, resolve_bridge_base_url

ROOT = Path(__file__).resolve().parents[1]


def _load_token_candidates() -> list[str]:
    candidates: list[str] = []
    for env_name in ("ASTRA_SESSION_TOKEN",):
        value = (os.getenv(env_name) or "").strip()
        if value:
            candidates.append(value)

    data_dir = Path(os.getenv("ASTRA_DATA_DIR", ROOT / ".astra"))
    file_candidates = [
        data_dir / "auth.token",
        ROOT / ".astra" / "doctor.token",
        ROOT / ".astra" / "smoke.token",
        ROOT / ".astra" / "qa.token",
    ]
    for path in file_candidates:
        if not path.exists():
            continue
        value = path.read_text(encoding="utf-8").strip()
        if value:
            candidates.append(value)
    unique: list[str] = []
    for token in candidates:
        if token not in unique:
            unique.append(token)
    return unique


def _headers(token: str | None) -> dict[str, str]:
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def _pick_run_id(session: requests.Session, api_base: str, headers: dict[str, str]) -> str | None:
    projects_resp = session.get(f"{api_base}/projects", headers=headers, timeout=5)
    if projects_resp.status_code != 200:
        raise RuntimeError(f"GET /projects -> HTTP {projects_resp.status_code}")
    projects = projects_resp.json()
    if not isinstance(projects, list):
        raise RuntimeError("GET /projects -> invalid JSON payload")
    for project in projects:
        project_id = project.get("id") if isinstance(project, dict) else None
        if not project_id:
            continue
        runs_resp = session.get(f"{api_base}/projects/{project_id}/runs?limit=1", headers=headers, timeout=5)
        if runs_resp.status_code != 200:
            continue
        runs = runs_resp.json()
        if isinstance(runs, list) and runs:
            run = runs[0]
            run_id = run.get("id") if isinstance(run, dict) else None
            if run_id:
                return run_id
    return None


def main() -> int:
    failures: list[str] = []
    session = requests.Session()

    try:
        api_base = resolve_api_base_url()
        bridge_base = resolve_bridge_base_url()
    except ValueError as exc:
        print(f"FAIL {exc}")
        return 1

    api_port = os.getenv("ASTRA_API_PORT")
    if api_port:
        url_port = port_from_url(api_base)
        if url_port is not None and str(url_port) != api_port:
            failures.append(f"ASTRA_API_PORT={api_port} != ASTRA_API_BASE_URL port {url_port}")

    bridge_port = os.getenv("ASTRA_BRIDGE_PORT") or os.getenv("ASTRA_DESKTOP_BRIDGE_PORT")
    if bridge_port:
        url_port = port_from_url(bridge_base)
        if url_port is not None and str(url_port) != bridge_port:
            failures.append(f"ASTRA_BRIDGE_PORT={bridge_port} != ASTRA_BRIDGE_BASE_URL port {url_port}")

    auth_status_url = f"{api_base}/auth/status"
    bridge_permissions_url = f"{bridge_base}/autopilot/permissions"

    print(f"API_BASE_URL={api_base}")
    print(f"API_AUTH_STATUS_URL={auth_status_url}")
    print(f"BRIDGE_BASE_URL={bridge_base}")
    print(f"BRIDGE_PERMISSIONS_URL={bridge_permissions_url}")

    token: str | None = None
    token_required = False
    try:
        auth_status_resp = session.get(auth_status_url, timeout=5)
        if auth_status_resp.status_code != 200:
            failures.append(f"GET /auth/status -> HTTP {auth_status_resp.status_code}")
        else:
            payload = auth_status_resp.json()
            token_required = bool(payload.get("token_required"))
            print(f"API_AUTH_MODE={payload.get('auth_mode', 'unknown')}")
            print(f"API_TOKEN_REQUIRED={'true' if token_required else 'false'}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"GET /auth/status failed: {exc}")

    if token_required:
        tokens = _load_token_candidates()
        if tokens:
            token = tokens[0]
            bootstrap_resp = session.post(f"{api_base}/auth/bootstrap", json={"token": token}, timeout=5)
            if bootstrap_resp.status_code not in {200, 409}:
                failures.append(f"POST /auth/bootstrap -> HTTP {bootstrap_resp.status_code}")
        else:
            failures.append("token_required=true but no ASTRA_SESSION_TOKEN/auth.token available")

    headers = _headers(token)

    sse_run_id: str | None = None
    try:
        sse_run_id = _pick_run_id(session, api_base, headers)
    except Exception as exc:  # noqa: BLE001
        failures.append(str(exc))

    if sse_run_id:
        sse_url = f"{api_base}/runs/{sse_run_id}/events?once=1"
        if token:
            sse_url = f"{sse_url}&token={token}"
    else:
        sse_url = f"{api_base}/runs/__diag_missing_run__/events?once=1"
        if token:
            sse_url = f"{sse_url}&token={token}"
    print(f"SSE_URL={sse_url}")

    try:
        sse_resp = session.get(
            sse_url,
            headers=headers if token else None,
            timeout=5,
            stream=True,
        )
        sse_body = sse_resp.text[:200]
        if sse_run_id and sse_resp.status_code != 200:
            failures.append(f"SSE once -> HTTP {sse_resp.status_code}")
        if not sse_run_id and sse_resp.status_code != 404:
            failures.append(f"SSE path probe expected 404 (no runs), got HTTP {sse_resp.status_code}")
        print(f"SSE_HTTP_STATUS={sse_resp.status_code}")
        if sse_body:
            compact = sse_body.replace("\n", "|")
            print(f"SSE_SAMPLE={compact}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"SSE request failed: {exc}")

    try:
        bridge_resp = session.get(bridge_permissions_url, timeout=5)
        print(f"BRIDGE_HTTP_STATUS={bridge_resp.status_code}")
        if bridge_resp.status_code != 200:
            failures.append(f"Bridge permissions -> HTTP {bridge_resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"Bridge permissions request failed: {exc}")

    if failures:
        print("\nFAILURES:")
        for item in failures:
            print(f"- {item}")
        return 1

    print("\nOK address diagnostics passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
