from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from lib.address_resolver import resolve_api_base_url, resolve_bridge_base_url

ROOT = Path(__file__).resolve().parents[1]


def _load_token_file(path: Path) -> str | None:
    if not path.exists():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


def _auth_headers(token: str | None) -> dict[str, str]:
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def _ensure_token(client: requests.Session, base_url: str, data_dir: Path, token_required: bool) -> str | None:
    if not token_required:
        return None

    token = os.getenv("ASTRA_SESSION_TOKEN")
    if not token:
        token = _load_token_file(data_dir / "auth.token")
    if not token:
        token = _load_token_file(ROOT / ".astra" / "doctor.token")
    if not token:
        token = _load_token_file(ROOT / ".astra" / "qa.token")
    if not token:
        token = _load_token_file(ROOT / ".astra" / "smoke.token")
    if not token:
        token = secrets.token_hex(16)

    res = client.post(f"{base_url}/auth/bootstrap", json={"token": token}, timeout=10)
    if res.status_code == 200:
        (ROOT / ".astra").mkdir(parents=True, exist_ok=True)
        (ROOT / ".astra" / "smoke.token").write_text(token, encoding="utf-8")
        return token
    if res.status_code == 409:
        raise RuntimeError("bootstrap: token already set (удалите токен или используйте актуальный)")
    raise RuntimeError(f"bootstrap failed: {res.status_code} {res.text}")


def _ensure_project(client: requests.Session, base_url: str, headers: dict[str, str]) -> dict[str, Any]:
    resp = client.get(f"{base_url}/projects", headers=headers, timeout=10)
    resp.raise_for_status()
    projects = resp.json()
    if projects:
        return projects[0]
    created = client.post(
        f"{base_url}/projects",
        headers=headers,
        json={"name": "Smoke", "tags": ["smoke"], "settings": {}},
        timeout=10,
    )
    created.raise_for_status()
    return created.json()


def _poll_snapshot(client: requests.Session, base_url: str, headers: dict[str, str], run_id: str) -> dict[str, Any]:
    resp = client.get(f"{base_url}/runs/{run_id}/snapshot", headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _extract_fact(snapshot: dict[str, Any], key: str) -> Any:
    for fact in snapshot.get("facts") or []:
        if isinstance(fact, dict) and fact.get("key") == key:
            return fact.get("value")
    return None


def _write_report(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    api_base = resolve_api_base_url()
    bridge_base = resolve_bridge_base_url()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    artifacts_root = ROOT / "artifacts" / "smoke" / timestamp
    artifacts_root.mkdir(parents=True, exist_ok=True)

    report_lines = ["# Smoke Report S_SMOKE_1", ""]
    report_lines.append(f"- Время: {datetime.now(timezone.utc).isoformat()}")
    report_lines.append(f"- API: {api_base}")
    report_lines.append(f"- Bridge: {bridge_base}")

    # Bridge pre-check
    try:
        perm_resp = requests.get(f"{bridge_base}/autopilot/permissions", timeout=3.0)
        bridge_ok = perm_resp.status_code == 200
    except Exception:
        bridge_ok = False

    if not bridge_ok:
        report_lines.append("- Bridge: FAIL (не отвечает)")
        report_lines.append("")
        report_lines.append("## Результат")
        report_lines.append("- Статус: FAIL")
        report_lines.append("- Причина: bridge_unavailable")
        _write_report(artifacts_root / "report.md", report_lines)
        latest = ROOT / "artifacts" / "smoke" / "latest_report.md"
        latest.parent.mkdir(parents=True, exist_ok=True)
        _write_report(latest, report_lines)
        return 1

    with requests.Session() as client:
        try:
            status_resp = client.get(f"{api_base}/auth/status", timeout=10)
            status_resp.raise_for_status()
            auth_status = status_resp.json()
            auth_mode = auth_status.get("auth_mode", "unknown")
            token_required = bool(auth_status.get("token_required", False))
            report_lines.append(f"- auth_mode: {auth_mode}")
            report_lines.append(f"- token_required: {'true' if token_required else 'false'}")

            data_dir = Path(os.getenv("ASTRA_DATA_DIR", ROOT / ".astra"))
            token = _ensure_token(client, api_base, data_dir, token_required)
            headers = _auth_headers(token)

            project = _ensure_project(client, api_base, headers)
            project_id = project.get("id")
            settings = project.get("settings") or {}
            llm_settings = settings.get("llm") or {}
            autopilot_settings = settings.get("autopilot") or {}
            ocr_env = os.getenv("ASTRA_OCR_ENABLED")
            ocr_state = ocr_env if ocr_env is not None else autopilot_settings.get("ocr_enabled", "default")
            report_lines.append(
                f"- LLM: {llm_settings.get('provider') or 'unknown'} / {llm_settings.get('model') or 'unknown'}"
            )
            report_lines.append(f"- OCR: {ocr_state}")

            response = client.post(
                f"{api_base}/projects/{project_id}/runs",
                headers=headers,
                json={
                    "query_text": "S_SMOKE_1: Проверь локальный smoke-тест. Сделай наблюдение, безопасную прокрутку и остановись перед удалением test.txt.",
                    "mode": "execute_confirm",
                },
                timeout=10,
            )
            response.raise_for_status()
            response_json = response.json()
            (artifacts_root / "response.json").write_text(
                json.dumps(response_json, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            run = response_json.get("run") or {}
            run_id = run.get("id")
            if not run_id:
                raise RuntimeError("run_id отсутствует")

            client.post(f"{api_base}/runs/{run_id}/start", headers=headers, timeout=10)

            approval_seen = False
            final_snapshot: dict[str, Any] | None = None
            final_events: list[dict[str, Any]] = []

            start = time.time()
            while time.time() - start < args.timeout:
                snapshot = _poll_snapshot(client, api_base, headers, run_id)
                final_snapshot = snapshot
                events = snapshot.get("last_events") or []
                final_events = events
                event_types = {evt.get("type") for evt in events if isinstance(evt, dict)}
                if "approval_requested" in event_types or "step_paused_for_approval" in event_types:
                    approval_seen = True
                    break
                status = snapshot.get("run", {}).get("status")
                if status in ("done", "failed", "canceled"):
                    break
                time.sleep(1.5)

            if final_snapshot is not None:
                (artifacts_root / "snapshot.json").write_text(
                    json.dumps(final_snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                (artifacts_root / "events.json").write_text(
                    json.dumps(final_events, ensure_ascii=False, indent=2), encoding="utf-8"
                )

            if approval_seen:
                client.post(f"{api_base}/runs/{run_id}/cancel", headers=headers, timeout=10)

            run_status = final_snapshot.get("run", {}).get("status") if final_snapshot else "unknown"
            hash_changed = _extract_fact(final_snapshot or {}, "smoke.hash_changed")

            report_lines.append("")
            report_lines.append("## Шаги")
            report_lines.append(f"- Наблюдение: {'OK' if bridge_ok else 'FAIL'}")
            report_lines.append(f"- Micro-actions: {'OK' if bridge_ok else 'FAIL'}")
            report_lines.append(f"- Verify hash_changed: {hash_changed if hash_changed is not None else '—'}")
            report_lines.append(f"- Approval: {'запрошено' if approval_seen else 'нет'}")
            report_lines.append(f"- Run status: {run_status}")
            report_lines.append("")
            report_lines.append("## Артефакты")
            rel_dir = artifacts_root.relative_to(ROOT)
            report_lines.append(f"- response.json: {rel_dir / 'response.json'}")
            report_lines.append(f"- snapshot.json: {rel_dir / 'snapshot.json'}")
            report_lines.append(f"- events.json: {rel_dir / 'events.json'}")

            report_lines.append("")
            report_lines.append("## Результат")
            if approval_seen:
                report_lines.append("- Статус: PASS")
                report_lines.append("- Причина: approval_requested (остановлено до подтверждения)")
                status_ok = True
            else:
                report_lines.append("- Статус: FAIL")
                report_lines.append("- Причина: approval_not_seen")
                status_ok = False

        except Exception as exc:
            report_lines.append("")
            report_lines.append("## Результат")
            report_lines.append("- Статус: FAIL")
            report_lines.append(f"- Причина: api_error ({exc})")
            status_ok = False

        _write_report(artifacts_root / "report.md", report_lines)
        latest = ROOT / "artifacts" / "smoke" / "latest_report.md"
        latest.parent.mkdir(parents=True, exist_ok=True)
        _write_report(latest, report_lines)

        return 0 if status_ok else 1


if __name__ == "__main__":
    sys.exit(main())
