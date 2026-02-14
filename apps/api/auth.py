from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import os
import secrets
from pathlib import Path

from fastapi import HTTPException, Request, status

from memory import store

logger = logging.getLogger("astra.auth")

ALLOWED_AUTH_MODES = {"local", "strict"}


def get_auth_mode() -> str:
    auth_mode = os.environ.get("ASTRA_AUTH_MODE", "local").lower()
    return auth_mode if auth_mode in ALLOWED_AUTH_MODES else "local"


def _log_denied(request: Request, reason: str) -> None:
    logger.warning("auth_denied reason=%s method=%s path=%s", reason, request.method, request.url.path)


def _hash_token(token: str, salt: str) -> str:
    return hashlib.sha256((salt + token).encode("utf-8")).hexdigest()


def _ensure_salt() -> str:
    return os.urandom(16).hex()


def _token_file_path(data_dir: Path) -> Path:
    return data_dir / "auth.token"


def _read_token_file(data_dir: Path) -> str | None:
    path = _token_file_path(data_dir)
    if not path.exists():
        return None
    try:
        token = path.read_text(encoding="utf-8").strip()
        return token or None
    except OSError:
        return None


def _write_token_file(data_dir: Path, token: str) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = _token_file_path(data_dir)
    path.write_text(token, encoding="utf-8")


def ensure_session_token(data_dir: Path) -> str:
    token = _read_token_file(data_dir)
    if not token:
        token = secrets.token_hex(16)
        _write_token_file(data_dir, token)

    stored = store.get_session_token_hash()
    if stored:
        expected = _hash_token(token, stored["salt"])
        if not hmac.compare_digest(expected, stored["token_hash"]):
            salt = _ensure_salt()
            store.set_session_token_hash(_hash_token(token, salt), salt)
    else:
        salt = _ensure_salt()
        store.set_session_token_hash(_hash_token(token, salt), salt)
    return token


def require_auth(request: Request) -> None:
    auth_mode = get_auth_mode()
    if auth_mode == "local":
        if request.client is None:
            return
        client_host = request.client.host if request.client else ""
        try:
            if client_host and ipaddress.ip_address(client_host).is_loopback:
                return
        except ValueError:
            if client_host in ("localhost",):
                return

    token = None
    auth_header = request.headers.get("Authorization")
    bad_scheme = False
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "", 1).strip()
    elif auth_header:
        bad_scheme = True
    if not token:
        token = request.query_params.get("token")

    stored = store.get_session_token_hash()
    if not stored:
        _log_denied(request, "token_not_initialized")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token_not_initialized")

    if not token:
        _log_denied(request, "bad_scheme" if bad_scheme else "missing_authorization_header")
        detail = "bad_scheme" if bad_scheme else "missing_authorization"
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

    expected = _hash_token(token, stored["salt"])
    if not hmac.compare_digest(expected, stored["token_hash"]):
        _log_denied(request, "token_mismatch")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token")


def bootstrap_token(token: str, data_dir: Path) -> dict:
    file_token = _read_token_file(data_dir)
    if file_token and file_token != token:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Токен уже установлен")

    stored = store.get_session_token_hash()
    if stored:
        expected = _hash_token(token, stored["salt"])
        if hmac.compare_digest(expected, stored["token_hash"]):
            if not file_token:
                _write_token_file(data_dir, token)
            return {"status": "ок"}

        salt = _ensure_salt()
        store.set_session_token_hash(_hash_token(token, salt), salt)
        _write_token_file(data_dir, token)
        return {"status": "обновлено"}

    salt = _ensure_salt()
    token_hash = _hash_token(token, salt)
    store.set_session_token_hash(token_hash, salt)
    _write_token_file(data_dir, token)
    return {"status": "создано"}
