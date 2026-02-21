from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.api.auth import require_auth
from core import secrets

router = APIRouter(prefix="/api/v1", tags=["secrets"], dependencies=[Depends(require_auth)])


class UnlockPayload(BaseModel):
    passphrase: str


@router.post("/secrets/unlock")
def unlock(payload: UnlockPayload):
    secrets.set_runtime_passphrase(payload.passphrase)
    return {"status": "ok"}


@router.get("/secrets/status")
def status():
    return {"vault_unlocked": bool(secrets.get_runtime_passphrase())}
