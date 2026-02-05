from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from apps.api.auth import require_auth
from core import secrets
from memory import vault

router = APIRouter(prefix="/api/v1", tags=["secrets"], dependencies=[Depends(require_auth)])


class UnlockPayload(BaseModel):
    passphrase: str


class OpenAIPayload(BaseModel):
    api_key: str


@router.post("/secrets/unlock")
def unlock(payload: UnlockPayload):
    secrets.set_runtime_passphrase(payload.passphrase)
    return {"status": "ok"}


@router.post("/secrets/openai")
def set_openai(payload: OpenAIPayload, request: Request):
    passphrase = secrets.get_runtime_passphrase()
    if not passphrase:
        raise HTTPException(status_code=400, detail="Хранилище не разблокировано")

    vault_path = Path(request.app.state.data_dir) / "vault.bin"
    vault.set_secret(vault_path, passphrase, "OPENAI_API_KEY", payload.api_key)
    return {"status": "ok"}


@router.get("/secrets/status")
def status():
    return {"vault_unlocked": bool(secrets.get_runtime_passphrase())}
