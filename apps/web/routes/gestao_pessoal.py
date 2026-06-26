from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse

from apps.web.dependencies.auth import auth_http_exception, require_permission
from apps.web.errors import bad_request, not_found
from infra.config import settings
from infra.persistence.db import get_db
from infra.persistence.transactions import atomic
from infra.pipeline.uploads import (
    IMAGE_UPLOAD_POLICY,
    PDF_UPLOAD_POLICY,
    ZIP_UPLOAD_POLICY,
    UploadValidationError,
    save_upload_to_path,
)
from infra.pipeline.workspace import PipelineWorkspaceManager
from modules.gestao_pessoal.application.pdf_importer import (
    parse_sicapex_pdf,
    upsert_militar_from_sicapex_pdf,
)
from modules.gestao_pessoal.application.schemas import (
    CompiladorContextoRead,
    GestaoPessoalFilterOptionsRead,
    GestaoPessoalUserScopeRead,
    MilitarCreate,
    MilitarEfetivoOmResponse,
    MilitarFromFullTextResponse,
    MilitarFromPdfResponse,
    MilitarFromTextResponse,
    MilitarParseFullTextResponse,
    MilitarParsePdfResponse,
    MilitarParseTextInput,
    MilitarParseTextResponse,
    MilitarPeriodoServicoCreate,
    MilitarPeriodoServicoRead,
    MilitarPeriodoServicoUpdate,
    MilitarRead,
    MilitarUpdate,
)
from modules.gestao_pessoal.application.hierarchy_config import (
    GestaoPessoalHierarchyConfig,
    default_hierarchy_config,
    load_hierarchy_config,
    save_hierarchy_config,
)
from modules.gestao_pessoal.application.text_parser import (
    parse_full_import_text,
    parse_militar_text,
)
from modules.gestao_pessoal.infrastructure.periodos_repository import MilitarPeriodosRepository
from modules.gestao_pessoal.infrastructure.repository import GestaoPessoalRepository
from modules.gestao_pessoal.importadores.sicapex.batch_importer import SicapexBatchImporter
from modules.gestao_pessoal.importadores.sicapex.report import report_to_dict
from modules.calculo_tempo_servico.application.sicapex_context import build_tempo_servico_context
from infra.persistence.models import SicapexEventoFuncionalModel

router = APIRouter(prefix="/gestao-pessoal", tags=["gestao_pessoal"])


def _require_dev_user(user: dict) -> None:
    if not user.get("is_dev"):
        raise auth_http_exception(403, "AUTH_DEV_REQUIRED", "Recurso restrito ao modo dev.")


@router.get("", response_model=list[MilitarRead])
def list_militares(
    query: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    include_inactive: bool = Query(default=False),
    only_inactive: bool = Query(default=False),
    posto_graduacao: str | None = Query(default=None),
    secao: str | None = Query(default=None),
    divisao: str | None = Query(default=None),
    view_scope: str = Query(default="usuario"),
    user=Depends(require_permission("mod.gestao_pessoal.view")),
    db=Depends(get_db),
):
    repository = GestaoPessoalRepository(db)
    user_context = repository.get_user_operational_context(user)
    return repository.list(
        query=query,
        limit=limit,
        include_inactive=include_inactive,
        only_inactive=only_inactive,
        posto_graduacao=posto_graduacao,
        secao=secao,
        divisao=divisao,
        view_scope=view_scope,
        user_context=user_context,
    )


@router.post("", response_model=MilitarRead)
def create_militar(
    payload: MilitarCreate,
    user=Depends(require_permission("mod.gestao_pessoal.create")),
    db=Depends(get_db),
):
    with atomic(db):
        return GestaoPessoalRepository(db).create(payload)


@router.get("/efetivo-om", response_model=MilitarEfetivoOmResponse)
def list_efetivo_om(
    om: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
    user=Depends(require_permission("mod.gestao_pessoal.view")),
    db=Depends(get_db),
):
    result = GestaoPessoalRepository(db).list_efetivo_om(om=om, limit=limit)
    return {
        **result,
        "total_ativos": len(result["ativos_na_om"]),
        "total_inativos": len(result["inativos_na_om"]),
    }


@router.get("/me/contexto-operacional", response_model=GestaoPessoalUserScopeRead)
def get_me_contexto_operacional(
    user=Depends(require_permission("mod.gestao_pessoal.view")),
    db=Depends(get_db),
):
    return GestaoPessoalRepository(db).get_user_operational_context(user)


@router.get("/filtros", response_model=GestaoPessoalFilterOptionsRead)
def list_gestao_pessoal_filters(
    user=Depends(require_permission("mod.gestao_pessoal.view")),
    db=Depends(get_db),
):
    return GestaoPessoalRepository(db).list_filter_options()


@router.get("/hierarquia-config", response_model=GestaoPessoalHierarchyConfig)
def get_gestao_pessoal_hierarchy_config(
    user=Depends(require_permission("mod.gestao_pessoal.view")),
):
    _require_dev_user(user)
    return load_hierarchy_config()


@router.patch("/hierarquia-config", response_model=GestaoPessoalHierarchyConfig)
def update_gestao_pessoal_hierarchy_config(
    payload: GestaoPessoalHierarchyConfig,
    user=Depends(require_permission("mod.gestao_pessoal.view")),
):
    _require_dev_user(user)
    return save_hierarchy_config(payload)


@router.post("/hierarquia-config/reset", response_model=GestaoPessoalHierarchyConfig)
def reset_gestao_pessoal_hierarchy_config(
    user=Depends(require_permission("mod.gestao_pessoal.view")),
):
    _require_dev_user(user)
    return save_hierarchy_config(default_hierarchy_config())


@router.post("/import/sicapex-zip")
async def import_sicapex_zip(
    zip_file: UploadFile = File(...),
    dry_run: bool = Query(default=True),
    user=Depends(require_permission("mod.gestao_pessoal.create")),
    db=Depends(get_db),
):
    try:
        with PipelineWorkspaceManager(base_dir="data/temp/gestao_pessoal") as workspace:
            zip_path = workspace.input_dir / "sicapex.zip"
            await save_upload_to_path(zip_file, zip_path, ZIP_UPLOAD_POLICY)
            importer = SicapexBatchImporter(db, dry_run=dry_run)
            report = importer.import_zip(zip_path)
    except UploadValidationError as exc:
        raise bad_request(exc.code, exc.message) from exc
    except Exception as exc:
        raise bad_request("SICAPEX_IMPORT_ZIP_FAILED", str(exc)) from exc

    return report_to_dict(report)


@router.get("/import/sicapex/{batch_id}/report")
def get_sicapex_import_report(
    batch_id: str,
    user=Depends(require_permission("mod.gestao_pessoal.view")),
    db=Depends(get_db),
):
    report = SicapexBatchImporter(db, dry_run=True).get_report(batch_id)
    if not report:
        raise not_found("SICAPEX_IMPORT_REPORT_NOT_FOUND", "Relatorio de importacao nao encontrado.")
    return report


@router.post("/parse-pdf", response_model=MilitarParsePdfResponse)
async def parse_militar_from_pdf(
    pdf: UploadFile = File(...),
    user=Depends(require_permission("mod.gestao_pessoal.create")),
):
    try:
        with PipelineWorkspaceManager(base_dir="data/temp/gestao_pessoal") as workspace:
            pdf_path = workspace.input_dir / "ficha_cadastro.pdf"
            await save_upload_to_path(pdf, pdf_path, PDF_UPLOAD_POLICY)
            result = parse_sicapex_pdf(pdf_path)
    except UploadValidationError as exc:
        raise bad_request(exc.code, exc.message) from exc
    except Exception as exc:
        raise bad_request("GESTAO_PESSOAL_PDF_PARSE_FAILED", str(exc)) from exc

    return {
        "parsed_data": result.parsed_data,
        "warnings": result.warnings,
        "unmapped_lines": result.unmapped_lines,
        "raw_excerpt": result.raw_excerpt,
    }


@router.post("/from-pdf", response_model=MilitarFromPdfResponse)
async def create_militar_from_pdf(
    pdf: UploadFile = File(...),
    user=Depends(require_permission("mod.gestao_pessoal.create")),
    db=Depends(get_db),
):
    try:
        with PipelineWorkspaceManager(base_dir="data/temp/gestao_pessoal") as workspace:
            pdf_path = workspace.input_dir / "ficha_cadastro.pdf"
            await save_upload_to_path(pdf, pdf_path, PDF_UPLOAD_POLICY)
            with atomic(db):
                result = upsert_militar_from_sicapex_pdf(db, pdf_path)
    except UploadValidationError as exc:
        raise bad_request(exc.code, exc.message) from exc
    except Exception as exc:
        raise bad_request("GESTAO_PESSOAL_PDF_IMPORT_FAILED", str(exc)) from exc

    return result


@router.post("/parse-text", response_model=MilitarParseTextResponse)
def parse_militar_from_text(
    payload: MilitarParseTextInput,
    user=Depends(require_permission("mod.gestao_pessoal.create")),
):
    return parse_militar_text(payload.raw_text)


@router.post("/from-text", response_model=MilitarFromTextResponse)
def create_militar_from_text(
    payload: MilitarParseTextInput,
    user=Depends(require_permission("mod.gestao_pessoal.create")),
    db=Depends(get_db),
):
    result = parse_militar_text(payload.raw_text)
    parsed_data = dict(result["parsed_data"])

    if not parsed_data.get("nome_completo"):
        raise bad_request(
            "GESTAO_PESSOAL_CREATE_FAILED",
            "Nao foi possivel criar o cadastro: nome completo nao encontrado no texto.",
        )

    try:
        with atomic(db):
            militar = GestaoPessoalRepository(db).create(MilitarCreate(**parsed_data))
    except Exception as exc:
        raise bad_request("GESTAO_PESSOAL_CREATE_FAILED", str(exc)) from exc

    return {
        "militar": militar,
        "warnings": result["warnings"],
        "unmapped_lines": result["unmapped_lines"],
    }


@router.post("/parse-full-text", response_model=MilitarParseFullTextResponse)
def parse_militar_full_text(
    payload: MilitarParseTextInput,
    user=Depends(require_permission("mod.gestao_pessoal.create")),
):
    return parse_full_import_text(payload.raw_text)


@router.post("/from-full-text", response_model=MilitarFromFullTextResponse)
def create_militar_full_text(
    payload: MilitarParseTextInput,
    user=Depends(require_permission("mod.gestao_pessoal.create")),
    db=Depends(get_db),
):
    result = parse_full_import_text(payload.raw_text)
    parsed_data = dict(result["parsed_data"])
    parsed_periodos = list(result["parsed_periodos"])

    if not parsed_data.get("nome_completo"):
        raise bad_request(
            "GESTAO_PESSOAL_CREATE_FAILED",
            "Nao foi possivel criar o cadastro: nome completo nao encontrado no texto.",
        )

    try:
        with atomic(db):
            militar = GestaoPessoalRepository(db).create(MilitarCreate(**parsed_data))
            repo = MilitarPeriodosRepository(db)

            criados = 0
            for item in parsed_periodos:
                repo.create(militar.id, MilitarPeriodoServicoCreate(**item))
                criados += 1
    except Exception as exc:
        raise bad_request("GESTAO_PESSOAL_CREATE_FAILED", str(exc)) from exc

    return {
        "militar": militar,
        "periodos_criados": criados,
        "warnings": result["warnings"],
        "unmapped_lines": result["unmapped_lines"],
    }


@router.patch("/periodos-servico/{periodo_id}", response_model=MilitarPeriodoServicoRead)
def update_periodo_servico(
    periodo_id: int,
    payload: MilitarPeriodoServicoUpdate,
    user=Depends(require_permission("mod.gestao_pessoal.edit")),
    db=Depends(get_db),
):
    with atomic(db):
        periodo = MilitarPeriodosRepository(db).update(periodo_id, payload)
    if not periodo:
        raise not_found("GESTAO_PESSOAL_PERIOD_NOT_FOUND", "Periodo nao encontrado.")
    return periodo


@router.get("/compilador-contexto", response_model=CompiladorContextoRead)
def find_compilador_contexto(
    identidade: str | None = Query(default=None),
    nome: str | None = Query(default=None),
    prec_cp: str | None = Query(default=None),
    user=Depends(require_permission("mod.gestao_pessoal.view")),
    db=Depends(get_db),
):
    if not any([identidade, nome, prec_cp]):
        raise bad_request(
            "GESTAO_PESSOAL_CONTEXT_QUERY_REQUIRED",
            "Informe identidade, nome ou Prec-CP para buscar contexto do Compilador.",
        )

    militar = GestaoPessoalRepository(db).find_for_compilador(
        identidade=identidade,
        nome=nome,
        prec_cp=prec_cp,
    )
    if not militar:
        raise not_found("GESTAO_PESSOAL_NOT_FOUND", "Militar nao encontrado.")

    return CompiladorContextoRead(
        militar_id=militar.id,
        tipo_documento_sugerido="folha_alteracao",
        militar=militar,
    )


@router.get("/{militar_id}", response_model=MilitarRead)
def get_militar(
    militar_id: int,
    user=Depends(require_permission("mod.gestao_pessoal.view")),
    db=Depends(get_db),
):
    militar = GestaoPessoalRepository(db).get(militar_id)
    if not militar:
        raise not_found("GESTAO_PESSOAL_NOT_FOUND", "Militar nao encontrado.")
    return militar


@router.patch("/{militar_id}", response_model=MilitarRead)
def update_militar(
    militar_id: int,
    payload: MilitarUpdate,
    user=Depends(require_permission("mod.gestao_pessoal.edit")),
    db=Depends(get_db),
):
    with atomic(db):
        militar = GestaoPessoalRepository(db).update(militar_id, payload)
    if not militar:
        raise not_found("GESTAO_PESSOAL_NOT_FOUND", "Militar nao encontrado.")
    return militar


@router.delete("/{militar_id}", response_model=MilitarRead)
def deactivate_militar(
    militar_id: int,
    user=Depends(require_permission("mod.gestao_pessoal.delete")),
    db=Depends(get_db),
):
    with atomic(db):
        militar = GestaoPessoalRepository(db).deactivate(militar_id)
    if not militar:
        raise not_found("GESTAO_PESSOAL_NOT_FOUND", "Militar nao encontrado.")
    return militar


@router.delete("/{militar_id}/permanent")
def delete_militar_permanent(
    militar_id: int,
    confirm_permanent: bool = Query(default=False),
    user=Depends(require_permission("mod.gestao_pessoal.delete")),
    db=Depends(get_db),
):
    if not confirm_permanent:
        raise bad_request(
            "GESTAO_PESSOAL_PERMANENT_DELETE_CONFIRMATION_REQUIRED",
            "Confirme a exclusao fisica com confirm_permanent=true.",
        )
    with atomic(db):
        snapshot = GestaoPessoalRepository(db).delete_permanent(militar_id)
    if not snapshot:
        raise not_found("GESTAO_PESSOAL_NOT_FOUND", "Militar nao encontrado.")
    return {"ok": True, "deleted": snapshot}


@router.patch("/{militar_id}/reactivate", response_model=MilitarRead)
def reactivate_militar(
    militar_id: int,
    user=Depends(require_permission("mod.gestao_pessoal.edit")),
    db=Depends(get_db),
):
    with atomic(db):
        militar = GestaoPessoalRepository(db).reactivate(militar_id)
    if not militar:
        raise not_found("GESTAO_PESSOAL_NOT_FOUND", "Militar nao encontrado.")
    return militar


@router.post("/{militar_id}/foto", response_model=MilitarRead)
async def upload_militar_foto(
    militar_id: int,
    foto: UploadFile = File(...),
    user=Depends(require_permission("mod.gestao_pessoal.edit")),
    db=Depends(get_db),
):
    militar = GestaoPessoalRepository(db).get(militar_id)
    if not militar:
        raise not_found("GESTAO_PESSOAL_NOT_FOUND", "Militar nao encontrado.")

    suffix = Path(foto.filename or "").suffix.lower()
    output_path = settings.base_dir / "data" / "uploads" / "gestao_pessoal" / "fotos" / f"{militar_id}{suffix}"
    try:
        await save_upload_to_path(foto, output_path, IMAGE_UPLOAD_POLICY)
    except UploadValidationError as exc:
        raise bad_request(exc.code, exc.message) from exc

    relative_path = output_path.relative_to(settings.base_dir).as_posix()
    with atomic(db):
        militar = GestaoPessoalRepository(db).update(
            militar_id,
            MilitarUpdate(foto_path=relative_path),
        )
    if not militar:
        raise not_found("GESTAO_PESSOAL_NOT_FOUND", "Militar nao encontrado.")
    return militar


@router.get("/{militar_id}/foto")
def get_militar_foto(
    militar_id: int,
    user=Depends(require_permission("mod.gestao_pessoal.view")),
    db=Depends(get_db),
):
    militar = GestaoPessoalRepository(db).get(militar_id)
    if not militar:
        raise not_found("GESTAO_PESSOAL_NOT_FOUND", "Militar nao encontrado.")
    if not militar.foto_path:
        raise not_found("GESTAO_PESSOAL_FOTO_NOT_FOUND", "Foto nao encontrada.")

    photo_path = (settings.base_dir / militar.foto_path).resolve()
    uploads_root = (settings.base_dir / "data" / "uploads").resolve()
    if uploads_root not in photo_path.parents or not photo_path.exists():
        raise not_found("GESTAO_PESSOAL_FOTO_NOT_FOUND", "Foto nao encontrada.")
    return FileResponse(photo_path)


@router.get("/{militar_id}/compilador-contexto", response_model=CompiladorContextoRead)
def get_compilador_contexto(
    militar_id: int,
    user=Depends(require_permission("mod.gestao_pessoal.view")),
    db=Depends(get_db),
):
    militar = GestaoPessoalRepository(db).get(militar_id)
    if not militar:
        raise not_found("GESTAO_PESSOAL_NOT_FOUND", "Militar nao encontrado.")

    return CompiladorContextoRead(
        militar_id=militar.id,
        tipo_documento_sugerido="folha_alteracao",
        militar=militar,
    )


@router.get("/{militar_id}/periodos-servico", response_model=list[MilitarPeriodoServicoRead])
def list_periodos_servico(
    militar_id: int,
    user=Depends(require_permission("mod.gestao_pessoal.view")),
    db=Depends(get_db),
):
    militar = GestaoPessoalRepository(db).get(militar_id)
    if not militar:
        raise not_found("GESTAO_PESSOAL_NOT_FOUND", "Militar nao encontrado.")
    return MilitarPeriodosRepository(db).list_by_militar(militar_id)


@router.get("/{militar_id}/tempo-servico-contexto")
def get_tempo_servico_contexto(
    militar_id: int,
    user=Depends(require_permission("mod.gestao_pessoal.view")),
    db=Depends(get_db),
):
    try:
        return build_tempo_servico_context(militar_id, db)
    except ValueError as exc:
        raise not_found("GESTAO_PESSOAL_NOT_FOUND", str(exc)) from exc


@router.get("/{militar_id}/sicapex-eventos")
def list_sicapex_eventos(
    militar_id: int,
    user=Depends(require_permission("mod.gestao_pessoal.view")),
    db=Depends(get_db),
):
    militar = GestaoPessoalRepository(db).get(militar_id)
    if not militar:
        raise not_found("GESTAO_PESSOAL_NOT_FOUND", "Militar nao encontrado.")
    eventos = (
        db.query(SicapexEventoFuncionalModel)
        .filter(SicapexEventoFuncionalModel.militar_id == militar_id)
        .order_by(SicapexEventoFuncionalModel.created_at.desc(), SicapexEventoFuncionalModel.id.desc())
        .all()
    )
    return [
        {
            "id": item.id,
            "tipo_evento": item.tipo_evento,
            "subtipo_evento": item.subtipo_evento,
            "data_inicio": item.data_inicio,
            "data_fim": item.data_fim,
            "documento": item.documento,
            "source_file_id": item.source_file_id,
            "payload_json": item.payload_json,
        }
        for item in eventos
    ]


@router.post("/{militar_id}/periodos-servico", response_model=MilitarPeriodoServicoRead)
def create_periodo_servico(
    militar_id: int,
    payload: MilitarPeriodoServicoCreate,
    user=Depends(require_permission("mod.gestao_pessoal.edit")),
    db=Depends(get_db),
):
    militar = GestaoPessoalRepository(db).get(militar_id)
    if not militar:
        raise not_found("GESTAO_PESSOAL_NOT_FOUND", "Militar nao encontrado.")
    with atomic(db):
        return MilitarPeriodosRepository(db).create(militar_id, payload)
