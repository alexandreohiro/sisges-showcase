from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class TarefaCreate(BaseModel):
    titulo: str
    descricao: Optional[str] = None
    tipo: str
    prioridade: str = "media"
    status: str = "nova"
    origem_modulo: str
    fingerprint: Optional[str] = None
    secao_responsavel: Optional[str] = None
    divisao_responsavel: Optional[str] = None
    referencia_tipo: Optional[str] = None
    referencia_id: Optional[str] = None
    militar_id: Optional[int] = None
    missao_id: Optional[int] = None
    workflow_item_id: Optional[int] = None
    document_id: Optional[str] = None
    responsavel_user_id: Optional[str] = None
    revisor_user_id: Optional[str] = None
    criado_por_user_id: Optional[str] = None
    prazo: Optional[datetime] = None
    artefato_tipo: Optional[str] = None
    artefato_path: Optional[str] = None
    artefato_sha256: Optional[str] = None
    checklist_json: Optional[dict[str, Any]] = None
    created_from_rule: bool = False
    blocked_by_task_id: Optional[int] = None
    observacoes: Optional[str] = None


class TarefaUpdate(BaseModel):
    titulo: Optional[str] = None
    descricao: Optional[str] = None
    tipo: Optional[str] = None
    prioridade: Optional[str] = None
    status: Optional[str] = None
    origem_modulo: Optional[str] = None
    fingerprint: Optional[str] = None
    secao_responsavel: Optional[str] = None
    divisao_responsavel: Optional[str] = None
    referencia_tipo: Optional[str] = None
    referencia_id: Optional[str] = None
    militar_id: Optional[int] = None
    missao_id: Optional[int] = None
    workflow_item_id: Optional[int] = None
    document_id: Optional[str] = None
    responsavel_user_id: Optional[str] = None
    revisor_user_id: Optional[str] = None
    prazo: Optional[datetime] = None
    data_inicio: Optional[datetime] = None
    data_conclusao: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    bloqueada: Optional[bool] = None
    motivo_bloqueio: Optional[str] = None
    resultado_resumido: Optional[str] = None
    artefato_tipo: Optional[str] = None
    artefato_path: Optional[str] = None
    artefato_sha256: Optional[str] = None
    checklist_json: Optional[dict[str, Any]] = None
    created_from_rule: Optional[bool] = None
    blocked_by_task_id: Optional[int] = None
    observacoes: Optional[str] = None


class TarefaRead(BaseModel):
    id: int
    codigo: Optional[str] = None
    titulo: str
    descricao: Optional[str] = None
    tipo: str
    prioridade: str
    status: str
    origem_modulo: str
    fingerprint: Optional[str] = None
    secao_responsavel: Optional[str] = None
    divisao_responsavel: Optional[str] = None
    referencia_tipo: Optional[str] = None
    referencia_id: Optional[str] = None
    militar_id: Optional[int] = None
    missao_id: Optional[int] = None
    workflow_item_id: Optional[int] = None
    document_id: Optional[str] = None
    responsavel_user_id: Optional[str] = None
    revisor_user_id: Optional[str] = None
    criado_por_user_id: Optional[str] = None
    completed_by_user_id: Optional[str] = None
    closed_by_user_id: Optional[str] = None
    blocked_by_task_id: Optional[int] = None
    prazo: Optional[datetime] = None
    data_inicio: Optional[datetime] = None
    data_conclusao: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    bloqueada: bool
    motivo_bloqueio: Optional[str] = None
    resultado_resumido: Optional[str] = None
    artefato_tipo: Optional[str] = None
    artefato_path: Optional[str] = None
    artefato_sha256: Optional[str] = None
    checklist_json: Optional[dict[str, Any]] = None
    created_from_rule: bool
    observacoes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TarefaTransitionInput(BaseModel):
    note: Optional[str] = None
    resultado_resumido: Optional[str] = None


class TarefaBlockInput(BaseModel):
    motivo_bloqueio: str
    note: Optional[str] = None
    blocked_by_task_id: Optional[int] = None


class TarefaArtifactInput(BaseModel):
    artefato_tipo: Optional[str] = None
    artefato_path: Optional[str] = None
    artefato_sha256: Optional[str] = None
    document_id: Optional[str] = None
    resultado_resumido: Optional[str] = None
    note: Optional[str] = None


class TarefaFromWorkflowInput(BaseModel):
    responsavel_user_id: Optional[str] = None
    secao_responsavel: Optional[str] = None
    divisao_responsavel: Optional[str] = None


class TarefaEventoRead(BaseModel):
    id: int
    tarefa_id: int
    actor_user_id: Optional[str] = None
    event_type: str
    before_json: Optional[dict[str, Any]] = None
    after_json: Optional[dict[str, Any]] = None
    note: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TarefaResumoRead(BaseModel):
    total: int
    abertas: int
    minhas_abertas: int
    vencidas: int
    vencem_hoje: int
    bloqueadas: int
    aguardando_revisao: int
    criticas: int
