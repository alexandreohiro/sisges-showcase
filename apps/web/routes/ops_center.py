from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from apps.web.dependencies.auth import require_permission
from apps.web.errors import bad_request
from infra.persistence.db import get_db
from modules.ops_center.application.services import OpsCenterService


router = APIRouter(prefix="/ops-center", tags=["ops_center"])


class ResolveInboxItemInput(BaseModel):
    note: str | None = None


@router.get("/inbox")
def get_inbox(
    status: str = Query(default="aberto"),
    modulo: str | None = Query(default=None),
    militar_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user=Depends(require_permission("ops_center.view")),
    db=Depends(get_db),
):
    service = OpsCenterService(db)
    return {
        "items": [
            service.to_dict(item)
            for item in service.inbox(
                status=status,
                modulo=modulo,
                militar_id=militar_id,
                limit=limit,
            )
        ]
    }


@router.get("/inbox/summary")
def get_inbox_summary(
    user=Depends(require_permission("ops_center.view")),
    db=Depends(get_db),
):
    return OpsCenterService(db).summary()


@router.post("/inbox/rebuild")
def rebuild_inbox(
    militar_id: int | None = Query(default=None),
    user=Depends(require_permission("ops_center.rebuild")),
    db=Depends(get_db),
):
    return OpsCenterService(db).rebuild(militar_id=militar_id)


@router.patch("/inbox/{item_id}/resolve")
def resolve_inbox_item(
    item_id: int,
    payload: ResolveInboxItemInput,
    user=Depends(require_permission("ops_center.resolve")),
    db=Depends(get_db),
):
    try:
        item = OpsCenterService(db).resolve(
            item_id=item_id,
            actor_user_id=user.get("id") or user.get("user_id"),
            note=payload.note,
        )
    except ValueError as exc:
        raise bad_request("OPS_INBOX_RESOLVE_FAILED", str(exc)) from exc
    return {"item": OpsCenterService.to_dict(item)}
