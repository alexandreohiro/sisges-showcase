from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from apps.web.dependencies.auth import require_permission
from apps.web.errors import bad_request, not_found
from infra.persistence.db import get_db
from infra.persistence.transactions import atomic
from modules.tarefas.application.schemas import (
    TarefaArtifactInput,
    TarefaBlockInput,
    TarefaCreate,
    TarefaEventoRead,
    TarefaFromWorkflowInput,
    TarefaRead,
    TarefaResumoRead,
    TarefaTransitionInput,
    TarefaUpdate,
)
from modules.tarefas.application.services import TarefasService

router = APIRouter(prefix="/tarefas", tags=["tarefas"])


def _actor_id(user) -> str | None:
    return user.get("id") or user.get("user_id")


@router.get("", response_model=list[TarefaRead])
def list_tarefas(
    status: str | None = Query(default=None),
    responsavel_user_id: str | None = Query(default=None),
    secao_responsavel: str | None = Query(default=None),
    divisao_responsavel: str | None = Query(default=None),
    origem_modulo: str | None = Query(default=None),
    prioridade: str | None = Query(default=None),
    tipo: str | None = Query(default=None),
    militar_id: int | None = Query(default=None),
    query: str | None = Query(default=None),
    bloqueada: bool | None = Query(default=None),
    include_closed: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    user=Depends(require_permission("mod.tarefas.view")),
    db=Depends(get_db),
):
    return TarefasService(db).list(
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


@router.get("/resumo", response_model=TarefaResumoRead)
def get_tarefas_resumo(
    user=Depends(require_permission("mod.tarefas.view")),
    db=Depends(get_db),
):
    return TarefasService(db).resumo(actor_user_id=_actor_id(user))


@router.get("/minhas", response_model=list[TarefaRead])
def list_minhas_tarefas(
    status: str | None = Query(default=None),
    include_closed: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    user=Depends(require_permission("mod.tarefas.view")),
    db=Depends(get_db),
):
    return TarefasService(db).list(
        status=status,
        responsavel_user_id=_actor_id(user),
        include_closed=include_closed,
        limit=limit,
    )


@router.get("/secao", response_model=list[TarefaRead])
def list_tarefas_secao(
    secao_responsavel: str | None = Query(default=None),
    divisao_responsavel: str | None = Query(default=None),
    status: str | None = Query(default=None),
    include_closed: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    user=Depends(require_permission("mod.tarefas.view")),
    db=Depends(get_db),
):
    secao = secao_responsavel or user.get("secao")
    divisao = divisao_responsavel or user.get("divisao")
    return TarefasService(db).list(
        status=status,
        secao_responsavel=secao,
        divisao_responsavel=divisao,
        include_closed=include_closed,
        limit=limit,
    )


@router.get("/{tarefa_id}", response_model=TarefaRead)
def get_tarefa(
    tarefa_id: int,
    user=Depends(require_permission("mod.tarefas.view")),
    db=Depends(get_db),
):
    try:
        return TarefasService(db).get_or_raise(tarefa_id)
    except ValueError as exc:
        raise not_found("TAREFA_NOT_FOUND", str(exc)) from exc


@router.post("", response_model=TarefaRead)
def create_tarefa(
    payload: TarefaCreate,
    user=Depends(require_permission("mod.tarefas.create")),
    db=Depends(get_db),
):
    try:
        with atomic(db):
            return TarefasService(db).create(payload, actor_user_id=_actor_id(user))
    except ValueError as exc:
        raise bad_request("TAREFA_CREATE_INVALID", str(exc)) from exc


@router.patch("/{tarefa_id}", response_model=TarefaRead)
def update_tarefa(
    tarefa_id: int,
    payload: TarefaUpdate,
    user=Depends(require_permission("mod.tarefas.edit")),
    db=Depends(get_db),
):
    try:
        with atomic(db):
            return TarefasService(db).update(tarefa_id, payload, actor_user_id=_actor_id(user))
    except ValueError as exc:
        message = str(exc)
        if "nao encontrada" in message:
            raise not_found("TAREFA_NOT_FOUND", message) from exc
        raise bad_request("TAREFA_UPDATE_INVALID", message) from exc


@router.post("/from-workflow-item/{item_id}", response_model=TarefaRead)
def create_from_workflow_item(
    item_id: int,
    payload: TarefaFromWorkflowInput,
    user=Depends(require_permission("mod.tarefas.create")),
    db=Depends(get_db),
):
    try:
        with atomic(db):
            return TarefasService(db).from_workflow_item(
                item_id,
                payload,
                actor_user_id=_actor_id(user),
            )
    except ValueError as exc:
        raise bad_request("TAREFA_FROM_WORKFLOW_FAILED", str(exc)) from exc


@router.post("/{tarefa_id}/iniciar", response_model=TarefaRead)
def iniciar_tarefa(
    tarefa_id: int,
    payload: TarefaTransitionInput,
    user=Depends(require_permission("mod.tarefas.edit")),
    db=Depends(get_db),
):
    try:
        with atomic(db):
            return TarefasService(db).iniciar(tarefa_id, payload, actor_user_id=_actor_id(user))
    except ValueError as exc:
        raise bad_request("TAREFA_START_FAILED", str(exc)) from exc


@router.post("/{tarefa_id}/bloquear", response_model=TarefaRead)
def bloquear_tarefa(
    tarefa_id: int,
    payload: TarefaBlockInput,
    user=Depends(require_permission("mod.tarefas.edit")),
    db=Depends(get_db),
):
    try:
        with atomic(db):
            return TarefasService(db).bloquear(tarefa_id, payload, actor_user_id=_actor_id(user))
    except ValueError as exc:
        raise bad_request("TAREFA_BLOCK_FAILED", str(exc)) from exc


@router.post("/{tarefa_id}/concluir", response_model=TarefaRead)
def concluir_tarefa(
    tarefa_id: int,
    payload: TarefaTransitionInput,
    user=Depends(require_permission("mod.tarefas.close")),
    db=Depends(get_db),
):
    try:
        with atomic(db):
            return TarefasService(db).concluir(tarefa_id, payload, actor_user_id=_actor_id(user))
    except ValueError as exc:
        raise bad_request("TAREFA_COMPLETE_FAILED", str(exc)) from exc


@router.post("/{tarefa_id}/reabrir", response_model=TarefaRead)
def reabrir_tarefa(
    tarefa_id: int,
    payload: TarefaTransitionInput,
    user=Depends(require_permission("mod.tarefas.edit")),
    db=Depends(get_db),
):
    try:
        with atomic(db):
            return TarefasService(db).reabrir(tarefa_id, payload, actor_user_id=_actor_id(user))
    except ValueError as exc:
        raise bad_request("TAREFA_REOPEN_FAILED", str(exc)) from exc


@router.post("/{tarefa_id}/anexar-artefato", response_model=TarefaRead)
def anexar_artefato_tarefa(
    tarefa_id: int,
    payload: TarefaArtifactInput,
    user=Depends(require_permission("mod.tarefas.edit")),
    db=Depends(get_db),
):
    try:
        with atomic(db):
            return TarefasService(db).anexar_artefato(tarefa_id, payload, actor_user_id=_actor_id(user))
    except ValueError as exc:
        raise bad_request("TAREFA_ARTIFACT_FAILED", str(exc)) from exc


@router.get("/{tarefa_id}/historico", response_model=list[TarefaEventoRead])
def get_tarefa_historico(
    tarefa_id: int,
    user=Depends(require_permission("mod.tarefas.view")),
    db=Depends(get_db),
):
    try:
        return TarefasService(db).historico(tarefa_id)
    except ValueError as exc:
        raise not_found("TAREFA_NOT_FOUND", str(exc)) from exc
