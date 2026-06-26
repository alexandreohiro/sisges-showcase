from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from apps.web.dependencies.auth import require_permission
from apps.web.errors import bad_request
from infra.persistence.db import get_db
from modules.acoes_sugeridas.application.services import AcoesSugeridasService


router = APIRouter(prefix="/acoes-sugeridas", tags=["acoes_sugeridas"])


class ExecutarAcaoInput(BaseModel):
    acao: str | None = None
    item_id: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


@router.post("/executar")
def executar_acao_sugerida(
    payload: ExecutarAcaoInput,
    user=Depends(require_permission("acoes_sugeridas.execute")),
    db=Depends(get_db),
):
    try:
        return AcoesSugeridasService(db).executar(
            acao=payload.acao,
            item_id=payload.item_id,
            actor_user_id=user.get("id") or user.get("user_id"),
            payload=payload.payload,
        )
    except ValueError as exc:
        raise bad_request("ACAO_SUGERIDA_FAILED", str(exc)) from exc
