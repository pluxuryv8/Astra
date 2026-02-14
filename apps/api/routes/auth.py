from __future__ import annotations

from fastapi import APIRouter, Request

from apps.api.auth import bootstrap_token, get_auth_mode
from apps.api.config import load_settings
from apps.api.models import BootstrapRequest
from memory import store

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/status")
def auth_status():
    auth_mode = get_auth_mode()
    token_required = auth_mode == "strict"
    return {
        "initialized": bool(store.get_session_token_hash()),
        "auth_mode": auth_mode,
        "token_required": token_required,
    }


@router.post("/bootstrap")
def auth_bootstrap(payload: BootstrapRequest, request: Request):
    data_dir = getattr(request.app.state, "data_dir", None)
    if data_dir is None:
        data_dir = load_settings().data_dir
    return bootstrap_token(payload.token, data_dir)
