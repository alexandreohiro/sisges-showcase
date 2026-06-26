from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from infra.persistence.models import TarefaEventoModel, TarefaModel
from modules.tarefas.domain.priorities import PRIORITY_ORDER
from modules.tarefas.domain.statuses import CLOSED_STATUSES
from modules.tarefas.application.schemas import TarefaCreate, TarefaUpdate


class TarefasRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(
        self,
        status: str | None = None,
        responsavel_user_id: str | None = None,
        secao_responsavel: str | None = None,
        divisao_responsavel: str | None = None,
        origem_modulo: str | None = None,
        prioridade: str | None = None,
        tipo: str | None = None,
        militar_id: int | None = None,
        query: str | None = None,
        bloqueada: bool | None = None,
        include_closed: bool = False,
        limit: int = 100,
    ):
        stmt = self.db.query(TarefaModel)

        if status:
            stmt = stmt.filter(TarefaModel.status == status)
        elif not include_closed:
            stmt = stmt.filter(~TarefaModel.status.in_(CLOSED_STATUSES))

        if responsavel_user_id:
            stmt = stmt.filter(TarefaModel.responsavel_user_id == responsavel_user_id)

        if secao_responsavel:
            stmt = stmt.filter(TarefaModel.secao_responsavel == secao_responsavel)

        if divisao_responsavel:
            stmt = stmt.filter(TarefaModel.divisao_responsavel == divisao_responsavel)

        if origem_modulo:
            stmt = stmt.filter(TarefaModel.origem_modulo == origem_modulo)

        if prioridade:
            stmt = stmt.filter(TarefaModel.prioridade == prioridade)

        if tipo:
            stmt = stmt.filter(TarefaModel.tipo == tipo)

        if militar_id is not None:
            stmt = stmt.filter(TarefaModel.militar_id == militar_id)

        if bloqueada is not None:
            stmt = stmt.filter(TarefaModel.bloqueada.is_(bloqueada))

        if query:
            pattern = f"%{query.strip()}%"
            stmt = stmt.filter(
                TarefaModel.titulo.ilike(pattern)
                | TarefaModel.descricao.ilike(pattern)
                | TarefaModel.codigo.ilike(pattern)
            )

        tasks = stmt.order_by(
            TarefaModel.prazo.is_(None),
            TarefaModel.prazo.asc(),
            TarefaModel.created_at.desc(),
        ).limit(limit).all()

        return sorted(
            tasks,
            key=lambda item: (
                PRIORITY_ORDER.get(item.prioridade, 99),
                item.prazo is None,
                item.prazo or datetime.max.replace(tzinfo=None),
                -item.id,
            ),
        )

    def get(self, tarefa_id: int):
        return (
            self.db.query(TarefaModel)
            .filter(TarefaModel.id == tarefa_id)
            .first()
        )

    def find_by_fingerprint(self, fingerprint: str):
        return (
            self.db.query(TarefaModel)
            .filter(TarefaModel.fingerprint == fingerprint)
            .first()
        )

    def create(self, payload: TarefaCreate):
        model = TarefaModel(**payload.model_dump())
        self.db.add(model)
        self.db.flush()
        self.db.refresh(model)
        return model

    def update(self, tarefa_id: int, payload: TarefaUpdate):
        model = self.get(tarefa_id)
        if not model:
            return None

        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(model, key, value)

        self.db.flush()
        self.db.refresh(model)
        return model

    def create_event(
        self,
        *,
        tarefa_id: int,
        actor_user_id: str | None,
        event_type: str,
        before_json: dict | None = None,
        after_json: dict | None = None,
        note: str | None = None,
    ) -> TarefaEventoModel:
        event = TarefaEventoModel(
            tarefa_id=tarefa_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            before_json=before_json,
            after_json=after_json,
            note=note,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
        self.db.add(event)
        self.db.flush()
        self.db.refresh(event)
        return event

    def list_events(self, tarefa_id: int) -> list[TarefaEventoModel]:
        return (
            self.db.query(TarefaEventoModel)
            .filter(TarefaEventoModel.tarefa_id == tarefa_id)
            .order_by(TarefaEventoModel.created_at.asc(), TarefaEventoModel.id.asc())
            .all()
        )
