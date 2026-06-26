from __future__ import annotations

from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from infra.persistence.models import QuadroBoardModel
from modules.quadro.application.schemas import QuadroBoardCreate, QuadroBoardUpdate, QuadroContent


def _content_dict(value: QuadroContent | dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return QuadroContent().model_dump()
    if isinstance(value, QuadroContent):
        return value.model_dump()
    return value


class QuadroRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(self, *, user_id: str, include_shared: bool = True, query: str | None = None, limit: int = 100):
        stmt = self.db.query(QuadroBoardModel)
        if include_shared:
            stmt = stmt.filter(
                or_(
                    QuadroBoardModel.owner_user_id == user_id,
                    QuadroBoardModel.visibility == "shared",
                ),
            )
        else:
            stmt = stmt.filter(QuadroBoardModel.owner_user_id == user_id)

        if query:
            q = f"%{query.strip()}%"
            stmt = stmt.filter(
                or_(
                    QuadroBoardModel.titulo.ilike(q),
                    QuadroBoardModel.descricao.ilike(q),
                ),
            )

        return stmt.order_by(QuadroBoardModel.updated_at.desc(), QuadroBoardModel.id.desc()).limit(limit).all()

    def get_visible(self, board_id: int, *, user_id: str):
        return (
            self.db.query(QuadroBoardModel)
            .filter(
                QuadroBoardModel.id == board_id,
                or_(
                    QuadroBoardModel.owner_user_id == user_id,
                    QuadroBoardModel.visibility == "shared",
                ),
            )
            .first()
        )

    def get_owned(self, board_id: int, *, user_id: str):
        return (
            self.db.query(QuadroBoardModel)
            .filter(
                QuadroBoardModel.id == board_id,
                QuadroBoardModel.owner_user_id == user_id,
            )
            .first()
        )

    def create(self, payload: QuadroBoardCreate, *, user_id: str):
        board = QuadroBoardModel(
            titulo=payload.titulo.strip(),
            descricao=payload.descricao.strip() if payload.descricao else None,
            visibility=payload.visibility,
            owner_user_id=user_id,
            content_json=_content_dict(payload.content_json),
            thumbnail_png=payload.thumbnail_png,
        )
        self.db.add(board)
        self.db.flush()
        self.db.refresh(board)
        return board

    def update(self, board_id: int, payload: QuadroBoardUpdate, *, user_id: str):
        board = self.get_owned(board_id, user_id=user_id)
        if not board:
            return None

        data = payload.model_dump(exclude_unset=True)
        if "titulo" in data and payload.titulo is not None:
            board.titulo = payload.titulo.strip()
        if "descricao" in data:
            board.descricao = payload.descricao.strip() if payload.descricao else None
        if "visibility" in data and payload.visibility is not None:
            board.visibility = payload.visibility
        if "content_json" in data:
            board.content_json = _content_dict(payload.content_json)
        if "thumbnail_png" in data:
            board.thumbnail_png = payload.thumbnail_png

        self.db.add(board)
        self.db.flush()
        self.db.refresh(board)
        return board

    def delete(self, board_id: int, *, user_id: str) -> bool:
        board = self.get_owned(board_id, user_id=user_id)
        if not board:
            return False
        self.db.delete(board)
        self.db.flush()
        return True
