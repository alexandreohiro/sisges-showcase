from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Any

from sqlalchemy.orm import Session

from infra.persistence.models import MilitarModel, TarefaModel, WorkflowItemModel
from modules.ops_center.application.services import OpsCenterService
from modules.tarefas.application.schemas import (
    TarefaArtifactInput,
    TarefaBlockInput,
    TarefaCreate,
    TarefaFromWorkflowInput,
    TarefaTransitionInput,
    TarefaUpdate,
)
from modules.tarefas.domain.priorities import SEVERITY_TO_PRIORITY, VALID_PRIORITIES
from modules.tarefas.domain.statuses import (
    OPEN_STATUSES,
    STATUS_BLOQUEADA,
    STATUS_CONCLUIDA,
    STATUS_EM_ANDAMENTO,
    STATUS_NOVA,
    STATUS_TRIAGEM,
    VALID_STATUSES,
)
from modules.tarefas.infrastructure.repository import TarefasRepository


DOCUMENTAL_ORIGINS = {"compilador", "ctsm", "folhas", "folha", "documents", "documentos"}
DOCUMENTAL_TYPE_TOKENS = {"gerar", "emitir", "compilar", "documento", "folha", "ctsm"}

SNAPSHOT_FIELDS = (
    "id",
    "codigo",
    "titulo",
    "descricao",
    "tipo",
    "prioridade",
    "status",
    "origem_modulo",
    "secao_responsavel",
    "divisao_responsavel",
    "referencia_tipo",
    "referencia_id",
    "militar_id",
    "missao_id",
    "workflow_item_id",
    "document_id",
    "responsavel_user_id",
    "revisor_user_id",
    "criado_por_user_id",
    "completed_by_user_id",
    "closed_by_user_id",
    "prazo",
    "data_inicio",
    "data_conclusao",
    "closed_at",
    "bloqueada",
    "motivo_bloqueio",
    "resultado_resumido",
    "artefato_tipo",
    "artefato_path",
    "artefato_sha256",
    "created_from_rule",
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _snapshot(task: TarefaModel) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for field in SNAPSHOT_FIELDS:
        value = getattr(task, field, None)
        if isinstance(value, datetime):
            data[field] = value.isoformat()
        else:
            data[field] = value
    return data


def _has_evidence(task: TarefaModel) -> bool:
    return any(
        [
            bool(task.resultado_resumido and task.resultado_resumido.strip()),
            bool(task.document_id),
            bool(task.artefato_path),
            bool(task.artefato_sha256),
        ]
    )


def _requires_evidence(task: TarefaModel) -> bool:
    origem = (task.origem_modulo or "").lower()
    tipo = (task.tipo or "").lower()
    return origem in DOCUMENTAL_ORIGINS or any(token in tipo for token in DOCUMENTAL_TYPE_TOKENS)


def _validate_status(status: str) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"Status de tarefa invalido: {status}.")


def _validate_priority(priority: str) -> None:
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"Prioridade de tarefa invalida: {priority}.")


class TarefasService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = TarefasRepository(db)

    def list(
        self,
        *,
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
    ) -> list[TarefaModel]:
        return self.repo.list(
            status=status,
            responsavel_user_id=responsavel_user_id,
            secao_responsavel=secao_responsavel,
            divisao_responsavel=divisao_responsavel,
            origem_modulo=origem_modulo,
            prioridade=prioridade,
            tipo=tipo,
            militar_id=militar_id,
            query=query,
            bloqueada=bloqueada,
            include_closed=include_closed,
            limit=limit,
        )

    def get_or_raise(self, tarefa_id: int) -> TarefaModel:
        task = self.repo.get(tarefa_id)
        if not task:
            raise ValueError("Tarefa nao encontrada.")
        return task

    def _validate_militar_id(self, militar_id: int | None) -> None:
        if militar_id is None:
            return
        exists = self.db.query(MilitarModel.id).filter(MilitarModel.id == militar_id).first()
        if not exists:
            raise ValueError("Militar vinculado nao encontrado no banco.")

    def create(self, payload: TarefaCreate, *, actor_user_id: str | None) -> TarefaModel:
        _validate_status(payload.status)
        _validate_priority(payload.prioridade)
        self._validate_militar_id(payload.militar_id)
        data = payload.model_copy()
        if not data.criado_por_user_id:
            data.criado_por_user_id = actor_user_id
        task = self.repo.create(data)
        if not task.codigo:
            task.codigo = f"TRF-{task.id:06d}"
            self.db.flush()
            self.db.refresh(task)
        self.repo.create_event(
            tarefa_id=task.id,
            actor_user_id=actor_user_id,
            event_type="TAREFA_CREATED",
            after_json=_snapshot(task),
        )
        return task

    def update(
        self,
        tarefa_id: int,
        payload: TarefaUpdate,
        *,
        actor_user_id: str | None,
    ) -> TarefaModel:
        task = self.get_or_raise(tarefa_id)
        before = _snapshot(task)
        if payload.status is not None:
            _validate_status(payload.status)
        if payload.prioridade is not None:
            _validate_priority(payload.prioridade)
        if "militar_id" in payload.model_fields_set:
            self._validate_militar_id(payload.militar_id)
        task = self.repo.update(tarefa_id, payload)
        if not task:
            raise ValueError("Tarefa nao encontrada.")
        self.repo.create_event(
            tarefa_id=task.id,
            actor_user_id=actor_user_id,
            event_type="TAREFA_UPDATED",
            before_json=before,
            after_json=_snapshot(task),
        )
        return task

    def iniciar(
        self,
        tarefa_id: int,
        payload: TarefaTransitionInput,
        *,
        actor_user_id: str | None,
    ) -> TarefaModel:
        task = self.get_or_raise(tarefa_id)
        before = _snapshot(task)
        task.status = STATUS_EM_ANDAMENTO
        task.bloqueada = False
        task.motivo_bloqueio = None
        task.data_inicio = task.data_inicio or _now()
        self.db.flush()
        self.db.refresh(task)
        self.repo.create_event(
            tarefa_id=task.id,
            actor_user_id=actor_user_id,
            event_type="TAREFA_STARTED",
            before_json=before,
            after_json=_snapshot(task),
            note=payload.note,
        )
        return task

    def bloquear(
        self,
        tarefa_id: int,
        payload: TarefaBlockInput,
        *,
        actor_user_id: str | None,
    ) -> TarefaModel:
        if not payload.motivo_bloqueio.strip():
            raise ValueError("Motivo de bloqueio e obrigatorio.")
        task = self.get_or_raise(tarefa_id)
        before = _snapshot(task)
        task.status = STATUS_BLOQUEADA
        task.bloqueada = True
        task.motivo_bloqueio = payload.motivo_bloqueio.strip()
        task.blocked_by_task_id = payload.blocked_by_task_id
        self.db.flush()
        self.db.refresh(task)
        self.repo.create_event(
            tarefa_id=task.id,
            actor_user_id=actor_user_id,
            event_type="TAREFA_BLOCKED",
            before_json=before,
            after_json=_snapshot(task),
            note=payload.note,
        )
        return task

    def concluir(
        self,
        tarefa_id: int,
        payload: TarefaTransitionInput,
        *,
        actor_user_id: str | None,
    ) -> TarefaModel:
        task = self.get_or_raise(tarefa_id)
        before = _snapshot(task)
        if payload.resultado_resumido:
            task.resultado_resumido = payload.resultado_resumido.strip()
        if _requires_evidence(task) and not _has_evidence(task):
            raise ValueError("Tarefa documental ou sistemica exige resultado ou artefato antes da conclusao.")
        task.status = STATUS_CONCLUIDA
        task.bloqueada = False
        task.motivo_bloqueio = None
        task.completed_by_user_id = actor_user_id
        task.closed_by_user_id = actor_user_id
        task.data_conclusao = task.data_conclusao or _now()
        task.closed_at = task.closed_at or _now()
        self.db.flush()
        self.db.refresh(task)
        if task.workflow_item_id:
            OpsCenterService(self.db).resolve(
                item_id=task.workflow_item_id,
                actor_user_id=actor_user_id,
                note=payload.note or task.resultado_resumido,
            )
        self.repo.create_event(
            tarefa_id=task.id,
            actor_user_id=actor_user_id,
            event_type="TAREFA_COMPLETED",
            before_json=before,
            after_json=_snapshot(task),
            note=payload.note,
        )
        return task

    def reabrir(
        self,
        tarefa_id: int,
        payload: TarefaTransitionInput,
        *,
        actor_user_id: str | None,
    ) -> TarefaModel:
        task = self.get_or_raise(tarefa_id)
        before = _snapshot(task)
        task.status = STATUS_EM_ANDAMENTO if task.data_inicio else STATUS_TRIAGEM
        task.data_conclusao = None
        task.closed_at = None
        task.completed_by_user_id = None
        task.closed_by_user_id = None
        self.db.flush()
        self.db.refresh(task)
        self.repo.create_event(
            tarefa_id=task.id,
            actor_user_id=actor_user_id,
            event_type="TAREFA_REOPENED",
            before_json=before,
            after_json=_snapshot(task),
            note=payload.note,
        )
        return task

    def anexar_artefato(
        self,
        tarefa_id: int,
        payload: TarefaArtifactInput,
        *,
        actor_user_id: str | None,
    ) -> TarefaModel:
        task = self.get_or_raise(tarefa_id)
        before = _snapshot(task)
        for key, value in payload.model_dump(exclude={"note"}, exclude_unset=True).items():
            setattr(task, key, value)
        self.db.flush()
        self.db.refresh(task)
        self.repo.create_event(
            tarefa_id=task.id,
            actor_user_id=actor_user_id,
            event_type="TAREFA_ARTIFACT_ATTACHED",
            before_json=before,
            after_json=_snapshot(task),
            note=payload.note,
        )
        return task

    def from_workflow_item(
        self,
        item_id: int,
        payload: TarefaFromWorkflowInput,
        *,
        actor_user_id: str | None,
    ) -> TarefaModel:
        item = self.db.query(WorkflowItemModel).filter(WorkflowItemModel.id == item_id).first()
        if not item:
            raise ValueError("Item operacional nao encontrado.")
        fingerprint = f"workflow_item:{item.fingerprint}"
        existing = self.repo.find_by_fingerprint(fingerprint)
        if existing:
            return existing
        return self.create(
            TarefaCreate(
                titulo=item.titulo,
                descricao=item.descricao,
                tipo=item.tipo,
                prioridade=SEVERITY_TO_PRIORITY.get(item.severidade, "media"),
                status=STATUS_NOVA,
                origem_modulo=item.modulo,
                fingerprint=fingerprint,
                secao_responsavel=payload.secao_responsavel,
                divisao_responsavel=payload.divisao_responsavel,
                referencia_tipo=item.referencia_tipo,
                referencia_id=item.referencia_id,
                militar_id=item.militar_id,
                workflow_item_id=item.id,
                responsavel_user_id=payload.responsavel_user_id,
                criado_por_user_id=actor_user_id,
                created_from_rule=True,
                observacoes=item.acao_recomendada,
            ),
            actor_user_id=actor_user_id,
        )

    def historico(self, tarefa_id: int):
        self.get_or_raise(tarefa_id)
        return self.repo.list_events(tarefa_id)

    def resumo(self, *, actor_user_id: str | None) -> dict[str, int]:
        tasks = self.repo.list(include_closed=True, limit=5000)
        now = _now()
        today_start = datetime.combine(now.date(), time.min)
        today_end = datetime.combine(now.date(), time.max)
        open_tasks = [task for task in tasks if task.status in OPEN_STATUSES]
        return {
            "total": len(tasks),
            "abertas": len(open_tasks),
            "minhas_abertas": len(
                [task for task in open_tasks if actor_user_id and task.responsavel_user_id == actor_user_id]
            ),
            "vencidas": len([task for task in open_tasks if task.prazo and task.prazo < now]),
            "vencem_hoje": len(
                [task for task in open_tasks if task.prazo and today_start <= task.prazo <= today_end]
            ),
            "bloqueadas": len([task for task in open_tasks if task.bloqueada or task.status == STATUS_BLOQUEADA]),
            "aguardando_revisao": len([task for task in open_tasks if task.status == "aguardando_revisao"]),
            "criticas": len([task for task in open_tasks if task.prioridade == "critica"]),
        }
