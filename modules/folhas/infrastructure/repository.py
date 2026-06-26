from __future__ import annotations

from sqlalchemy.orm import Session

from infra.persistence.models import FolhaAlteracaoModel
from modules.folhas.application.schemas import FolhaCreate, FolhaUpdate


class FolhasRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(self, status: str | None = None, militar_id: int | None = None, limit: int = 100):
        stmt = self.db.query(FolhaAlteracaoModel)

        if status:
            stmt = stmt.filter(FolhaAlteracaoModel.status == status)

        if militar_id:
            stmt = stmt.filter(FolhaAlteracaoModel.militar_id == militar_id)

        return (
            stmt.order_by(FolhaAlteracaoModel.created_at.desc())
            .limit(limit)
            .all()
        )

    def list_by_statuses(
        self,
        statuses: list[str] | None = None,
        militar_id: int | None = None,
        limit: int = 100,
    ):
        stmt = self.db.query(FolhaAlteracaoModel)

        if statuses:
            stmt = stmt.filter(FolhaAlteracaoModel.status.in_(statuses))

        if militar_id:
            stmt = stmt.filter(FolhaAlteracaoModel.militar_id == militar_id)

        return (
            stmt.order_by(FolhaAlteracaoModel.updated_at.desc())
            .limit(limit)
            .all()
        )

    def get(self, folha_id: int):
        return (
            self.db.query(FolhaAlteracaoModel)
            .filter(FolhaAlteracaoModel.id == folha_id)
            .first()
        )

    def create(self, payload: FolhaCreate):
        model = FolhaAlteracaoModel(**payload.model_dump())
        self.db.add(model)
        self.db.flush()
        self.db.refresh(model)
        return model

    def update(self, folha_id: int, payload: FolhaUpdate):
        model = self.get(folha_id)
        if not model:
            return None

        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(model, key, value)

        self.db.flush()
        self.db.refresh(model)
        return model
