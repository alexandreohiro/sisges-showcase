from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from apps.web.dependencies.auth import require_permission
from apps.web.errors import bad_request, not_found
from infra.persistence.db import get_db
from modules.ctsm.application.schemas import CTSMEmitirInput, CTSMFromCalculoInput
from modules.ctsm.application.services import CTSMService


router = APIRouter(prefix="/ctsm", tags=["ctsm"])


@router.get("")
def list_ctsm(
    militar_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    user=Depends(require_permission("mod.ctsm.view")),
    db=Depends(get_db),
):
    service = CTSMService(db)
    return {
        "items": [
            service.to_dict(item)
            for item in service.list_items(militar_id=militar_id, limit=limit)
        ]
    }


@router.get("/{ctsm_id}")
def get_ctsm(
    ctsm_id: int,
    user=Depends(require_permission("mod.ctsm.view")),
    db=Depends(get_db),
):
    service = CTSMService(db)
    item = service.get(ctsm_id)
    if not item:
        raise not_found("CTSM_NOT_FOUND", "CTSM nao encontrada.")
    return {"item": service.to_dict(item)}


@router.post("/from-calculo")
def create_ctsm_from_calculo(
    payload: CTSMFromCalculoInput,
    user=Depends(require_permission("mod.ctsm.create")),
    db=Depends(get_db),
):
    try:
        item = CTSMService(db).create_from_calculo(
            calculo_id=payload.calculo_id,
            actor_user_id=user.get("id") or user.get("user_id"),
            observacoes=payload.observacoes,
            emitir_documento=payload.emitir_documento,
        )
    except ValueError as exc:
        raise bad_request("CTSM_CREATE_FAILED", str(exc)) from exc

    return {"item": CTSMService.to_dict(item)}


@router.post("/{ctsm_id}/emitir")
def emitir_ctsm(
    ctsm_id: int,
    payload: CTSMEmitirInput,
    user=Depends(require_permission("mod.ctsm.emit")),
    db=Depends(get_db),
):
    try:
        item = CTSMService(db).emitir_documento(
            ctsm_id=ctsm_id,
            actor_user_id=user.get("id") or user.get("user_id"),
            observacoes=payload.observacoes,
        )
    except ValueError as exc:
        raise bad_request("CTSM_EMIT_FAILED", str(exc)) from exc

    return {"item": CTSMService.to_dict(item)}
