from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from apps.web.dependencies.auth import require_permission
from apps.web.errors import not_found
from infra.persistence.db import get_db
from infra.persistence.transactions import atomic
from modules.quadro.application.schemas import QuadroBoardCreate, QuadroBoardRead, QuadroBoardUpdate
from modules.quadro.infrastructure.repository import QuadroRepository

router = APIRouter(prefix="/quadro", tags=["quadro"])


@router.get("/boards", response_model=list[QuadroBoardRead])
def list_boards(
    query: str | None = Query(default=None),
    include_shared: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
    user=Depends(require_permission("mod.quadro.view")),
    db=Depends(get_db),
):
    return QuadroRepository(db).list(
        user_id=user["id"],
        include_shared=include_shared,
        query=query,
        limit=limit,
    )


@router.post("/boards", response_model=QuadroBoardRead)
def create_board(
    payload: QuadroBoardCreate,
    user=Depends(require_permission("mod.quadro.edit")),
    db=Depends(get_db),
):
    with atomic(db):
        return QuadroRepository(db).create(payload, user_id=user["id"])


@router.get("/boards/{board_id}", response_model=QuadroBoardRead)
def get_board(
    board_id: int,
    user=Depends(require_permission("mod.quadro.view")),
    db=Depends(get_db),
):
    board = QuadroRepository(db).get_visible(board_id, user_id=user["id"])
    if not board:
        raise not_found("QUADRO_NOT_FOUND", "Quadro nao encontrado.")
    return board


@router.patch("/boards/{board_id}", response_model=QuadroBoardRead)
def update_board(
    board_id: int,
    payload: QuadroBoardUpdate,
    user=Depends(require_permission("mod.quadro.edit")),
    db=Depends(get_db),
):
    with atomic(db):
        board = QuadroRepository(db).update(board_id, payload, user_id=user["id"])
    if not board:
        raise not_found("QUADRO_NOT_FOUND", "Quadro nao encontrado ou sem permissao de edicao.")
    return board


@router.delete("/boards/{board_id}")
def delete_board(
    board_id: int,
    user=Depends(require_permission("mod.quadro.edit")),
    db=Depends(get_db),
):
    with atomic(db):
        deleted = QuadroRepository(db).delete(board_id, user_id=user["id"])
    if not deleted:
        raise not_found("QUADRO_NOT_FOUND", "Quadro nao encontrado ou sem permissao de exclusao.")
    return {"ok": True, "deleted_id": board_id}
