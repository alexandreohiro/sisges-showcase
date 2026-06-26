from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from apps.web.dependencies.auth import require_permission
from infra.persistence.db import get_db
from modules.consistencia.application.services import ConsistenciaService


router = APIRouter(prefix="/consistencia", tags=["consistencia"])


@router.post("/reprocessar")
def reprocessar_consistencia(
    militar_id: int | None = Query(default=None),
    user=Depends(require_permission("consistencia.reprocess")),
    db=Depends(get_db),
):
    issues = ConsistenciaService(db).reprocessar(militar_id=militar_id)
    return {"items": [item.to_dict() for item in issues], "total": len(issues)}


@router.get("/militar/{militar_id}")
def get_consistencia_militar(
    militar_id: int,
    user=Depends(require_permission("consistencia.view")),
    db=Depends(get_db),
):
    issues = ConsistenciaService(db).reprocessar(militar_id=militar_id)
    return {"items": [item.to_dict() for item in issues], "total": len(issues)}


@router.get("/summary")
def get_consistencia_summary(
    user=Depends(require_permission("consistencia.view")),
    db=Depends(get_db),
):
    return ConsistenciaService(db).summary()
