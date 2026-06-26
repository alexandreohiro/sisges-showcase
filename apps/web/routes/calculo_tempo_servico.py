from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from apps.web.dependencies.auth import require_permission
from apps.web.errors import bad_request
from infra.persistence.db import get_db
from modules.calculo_tempo_servico.application.sicapex_context import build_tempo_servico_context
from modules.calculo_tempo_servico.application.services import CalculoTempoServicoConsolidador

router = APIRouter(
    prefix="/calculo-tempo-servico",
    tags=["calculo_tempo_servico"],
)


class PreviewComplementadoInput(BaseModel):
    militar_id: int
    referencia_data: date
    respostas: dict[str, Any] = Field(default_factory=dict)


class AprovarInput(BaseModel):
    militar_id: int
    referencia_data: date
    respostas: dict[str, Any] = Field(default_factory=dict)
    observacoes: str | None = None


@router.get("/preview")
def preview_calculo_tempo_servico(
    militar_id: int = Query(...),
    referencia_data: date = Query(...),
    user=Depends(require_permission("mod.calculo.view")),
    db=Depends(get_db),
):
    try:
        return CalculoTempoServicoConsolidador(db).preview(
            militar_id=militar_id,
            referencia_data=referencia_data,
        )
    except ValueError as exc:
        raise bad_request("CALCULO_TEMPO_PREVIEW_FAILED", str(exc))


@router.post("/preview-complementado")
def preview_calculo_tempo_servico_complementado(
    payload: PreviewComplementadoInput,
    user=Depends(require_permission("mod.calculo.view")),
    db=Depends(get_db),
):
    try:
        return CalculoTempoServicoConsolidador(db).preview_complementado(
            militar_id=payload.militar_id,
            referencia_data=payload.referencia_data,
            respostas=payload.respostas,
        )
    except ValueError as exc:
        raise bad_request("CALCULO_TEMPO_PREVIEW_FAILED", str(exc))


@router.post("/preview-from-sicapex/{militar_id}")
def preview_calculo_from_sicapex(
    militar_id: int,
    referencia_data: date | None = Query(default=None),
    user=Depends(require_permission("mod.calculo.view")),
    db=Depends(get_db),
):
    try:
        contexto = build_tempo_servico_context(militar_id, db)
        preview = CalculoTempoServicoConsolidador(db).preview(
            militar_id=militar_id,
            referencia_data=referencia_data or date.today(),
        )
        return {
            "contexto_sicapex": contexto,
            "preview": preview,
            "status": "CALCULO_PENDENTE_VALIDACAO",
        }
    except ValueError as exc:
        raise bad_request("CALCULO_TEMPO_SICAPEX_PREVIEW_FAILED", str(exc))


@router.post("/diff-respostas")
def diff_respostas_calculo_tempo_servico(
    payload: PreviewComplementadoInput,
    user=Depends(require_permission("mod.calculo.view")),
    db=Depends(get_db),
):
    try:
        return CalculoTempoServicoConsolidador(db).diff_respostas(
            militar_id=payload.militar_id,
            referencia_data=payload.referencia_data,
            respostas=payload.respostas,
        )
    except ValueError as exc:
        raise bad_request("CALCULO_TEMPO_DIFF_FAILED", str(exc))


@router.post("/aprovar-ajustes-e-salvar")
def aprovar_ajustes_e_salvar_calculo_tempo_servico(
    payload: AprovarInput,
    user=Depends(require_permission("mod.calculo.view")),
    db=Depends(get_db),
):
    try:
        return CalculoTempoServicoConsolidador(db).approve_and_save(
            militar_id=payload.militar_id,
            referencia_data=payload.referencia_data,
            respostas=payload.respostas,
            observacoes=payload.observacoes,
            calculado_por_user_id=user.get("id") or user.get("user_id"),
        )
    except ValueError as exc:
        raise bad_request("CALCULO_TEMPO_APPROVE_FAILED", str(exc))


@router.get("/historico")
def historico_calculo_tempo_servico(
    militar_id: int = Query(...),
    limit: int = Query(default=20, ge=1, le=100),
    user=Depends(require_permission("mod.calculo.view")),
    db=Depends(get_db),
):
    try:
        return CalculoTempoServicoConsolidador(db).list_history(
            militar_id=militar_id,
            limit=limit,
        )
    except ValueError as exc:
        raise bad_request("CALCULO_TEMPO_HISTORY_FAILED", str(exc))
