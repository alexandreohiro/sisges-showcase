from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.web.dependencies.auth import require_permission
from apps.web.errors import not_found
from infra.persistence.db import get_db
from modules.militar_360.application.services import Militar360Service


router = APIRouter(prefix="/militar-360", tags=["militar_360"])


@router.get("/{militar_id}")
def get_militar_360(
    militar_id: int,
    user=Depends(require_permission("militar_360.view")),
    db=Depends(get_db),
):
    try:
        return Militar360Service(db).get_profile(militar_id)
    except ValueError as exc:
        raise not_found("MILITAR_360_NOT_FOUND", str(exc)) from exc


@router.get("/{militar_id}/timeline")
def get_militar_360_timeline(
    militar_id: int,
    user=Depends(require_permission("militar_360.view")),
    db=Depends(get_db),
):
    try:
        return {"items": Militar360Service(db).timeline(militar_id)}
    except ValueError as exc:
        raise not_found("MILITAR_360_NOT_FOUND", str(exc)) from exc
