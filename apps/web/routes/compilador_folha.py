from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from apps.web.dependencies.auth import require_permission
from apps.web.errors import bad_request
from infra.persistence.db import get_db
from infra.pipeline.uploads import (
    ODT_UPLOAD_POLICY,
    PDF_UPLOAD_POLICY,
    UploadValidationError,
    save_upload_to_path,
)
from infra.pipeline.workspace import PipelineWorkspaceManager
from modules.compilador.application.default_odt_template import ensure_default_folha_template
from modules.compilador.application.folha_package_service import (
    ALTERACOES_ODT_ROLES,  # noqa: F401 — re-exported for test access via `route.`
    ALTERACOES_PDF_ROLES,  # noqa: F401 — re-exported for test access via `route.`
    ALTERACOES_ROLES,
    INPUT_BI_ODT,  # noqa: F401 — re-exported for test access via `route.`
    INPUT_BI_PDF,  # noqa: F401 — re-exported for test access via `route.`
    INPUT_MODELO_ODT,
    INPUT_SICAPEX_PDF,  # noqa: F401 — re-exported for test access via `route.`
    INTERNAL_DEFAULT_MODELO_ODT,
    MEMORY_REFERENCE_BI_ODT,  # noqa: F401 — re-exported for test access via `route.`
    MEMORY_REFERENCE_BI_PDF,  # noqa: F401 — re-exported for test access via `route.`
    MEMORY_REFERENCE_FOLHA_ODT,  # noqa: F401 — re-exported for test access via `route.`
    MEMORY_REFERENCE_FOLHA_PDF,  # noqa: F401 — re-exported for test access via `route.`
    MODELO_ROLES,
    OUTPUT_MODE_FULL,
    OUTPUT_MODE_PARTE1,  # noqa: F401 — re-exported for test access via `route.`
    SICAPEX_ROLES,
    STORED_EXECUTABLE_MODELO_ODT,
    VISUAL_REFERENCE_ONLY_MODELO_ODT,
    _alteracoes_role_for_upload,
    _context_requires_sicapex_pdf,
    _tempo_context_or_none,
    _validate_memory_file,
    compile_folha_pipeline,
)
from modules.compilador.application.odt_template_policy import (
    EXECUTABLE_TEMPLATE,
    INVALID_ODT,
    VISUAL_REFERENCE_ONLY,
    classify_odt_template,
)
from modules.documents.application.services import DocumentService

router = APIRouter(prefix="/compilador", tags=["compilador"])

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_OUTPUT_ROOT = PROJECT_ROOT / "data" / "output"
FOLHA_EXECUTABLE_TEMPLATE_FILENAME = "000_MODELO_SISGES_EXECUTAVEL_V1.odt"


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------

class CompileFromMemoryOptions(BaseModel):
    reparar_tabelas: bool = True
    preservar_tabelas_odt: bool = True
    gerar_pdf_preview: bool = True
    full_package: bool = True
    output_mode: str = OUTPUT_MODE_FULL
    assinatura_mode: str = "auto"
    assinatura_nome: str | None = None
    assinatura_funcao: str | None = None


class FonteAlteracoesPayload(BaseModel):
    type: str = "MEMORY_FILE"
    file_id: str | None = None
    run_id: str | None = None


class ModeloPayload(BaseModel):
    type: str = "INTERNAL_DEFAULT"
    file_id: str | None = None


class SicapexPayload(BaseModel):
    type: str = "GESTAO_PESSOAL_DB"
    file_id: str | None = None


class CompileFromMemoryPayload(BaseModel):
    militar_id: int | None = None
    ano: int = 2025
    semestre: str = "2"
    fonte_alteracoes: FonteAlteracoesPayload | None = None
    modelo: ModeloPayload | None = None
    sicapex: SicapexPayload | None = None
    alteracoes_file_id: str | None = None
    sicapex_file_id: str | None = None
    modelo_file_id: str | None = None
    options: CompileFromMemoryOptions = Field(default_factory=CompileFromMemoryOptions)


# ---------------------------------------------------------------------------
# Route-layer helpers
# ---------------------------------------------------------------------------

def _stored_folha_executable_template_path() -> Path:
    return DATA_OUTPUT_ROOT / "modelos" / FOLHA_EXECUTABLE_TEMPLATE_FILENAME


def _resolve_modelo_path(
    workspace,
    modelo_path: Path | None,
    *,
    usar_modelo_executavel_sisges: bool = False,
) -> tuple[Path, str, str]:
    if modelo_path:
        classification = classify_odt_template(modelo_path)
        if classification.classification == INVALID_ODT:
            raise bad_request("ERR_TEMPLATE_ODT_INVALID", "Modelo ODT enviado nao e um ODT valido.")
        if classification.classification == EXECUTABLE_TEMPLATE:
            return modelo_path, INPUT_MODELO_ODT, "UPLOADED_MODEL"
        if classification.classification == VISUAL_REFERENCE_ONLY:
            return modelo_path, VISUAL_REFERENCE_ONLY_MODELO_ODT, "VISUAL_REFERENCE_ONLY"

    if usar_modelo_executavel_sisges:
        stored_template = _stored_folha_executable_template_path()
        if not stored_template.exists():
            raise bad_request(
                "ERR_STORED_EXECUTABLE_TEMPLATE_NOT_FOUND",
                "Modelo executavel SISGES nao encontrado. Prepare o modelo em Folhas antes de compilar.",
            )
        classification = classify_odt_template(stored_template)
        if classification.classification != EXECUTABLE_TEMPLATE:
            raise bad_request(
                "ERR_STORED_EXECUTABLE_TEMPLATE_INVALID",
                "Modelo executavel SISGES salvo nao possui marcadores SISGES validos.",
            )
        return stored_template, STORED_EXECUTABLE_MODELO_ODT, "STORED_EXECUTABLE"

    default_template = ensure_default_folha_template(workspace.input_dir)
    return default_template, INTERNAL_DEFAULT_MODELO_ODT, "INTERNAL_DEFAULT"


def _is_current_request_template(template_source: str) -> bool:
    return template_source in {"UPLOADED_MODEL", "VISUAL_REFERENCE_ONLY"}


async def _save_validated_upload(upload: UploadFile, path: Path, policy) -> None:
    try:
        await save_upload_to_path(upload, path, policy)
    except UploadValidationError as exc:
        raise bad_request(exc.code, exc.message) from exc


# ---------------------------------------------------------------------------
# Shared compile handler
# ---------------------------------------------------------------------------

async def compile_folha_odt_package(
    *,
    bi_odt: UploadFile | None = None,
    fonte_alteracoes_pdf: UploadFile | None = None,
    fonte_alteracoes_odt: UploadFile | None = None,
    sicapex_pdf: UploadFile | None = None,
    modelo_odt: UploadFile | None,
    militar_id: int | None = None,
    usar_sicapex_banco: bool = True,
    ano: int,
    semestre: str,
    reparar_tabelas: bool,
    preservar_tabelas_odt: bool,
    gerar_pdf_preview: bool,
    full_package: bool,
    output_mode: str,
    assinatura_mode: str,
    assinatura_nome: str | None = None,
    assinatura_funcao: str | None = None,
    usar_modelo_executavel_sisges: bool = False,
    memory_reference_file_id: str | None = None,
    fonte_eventos: str | None = None,
    document_service: DocumentService,
    owner_user_id: str | None,
    db,
) -> FileResponse:
    with PipelineWorkspaceManager() as workspace:
        alteracoes_upload = fonte_alteracoes_pdf or fonte_alteracoes_odt or bi_odt
        if alteracoes_upload is None or not alteracoes_upload.filename:
            raise bad_request("ERR_BI_SOURCE_MISSING", "Informe uma fonte de alteracoes PDF, ODT ou memoria.")
        alteracoes_suffix = Path(alteracoes_upload.filename).suffix.lower()
        if fonte_alteracoes_pdf is not None or alteracoes_suffix == ".pdf":
            bi_path = workspace.input_dir / "bi_alteracoes.pdf"
            await _save_validated_upload(alteracoes_upload, bi_path, PDF_UPLOAD_POLICY)
        else:
            bi_path = workspace.input_dir / "bi_alteracoes.odt"
            await _save_validated_upload(alteracoes_upload, bi_path, ODT_UPLOAD_POLICY)
        bi_role = _alteracoes_role_for_upload(bi_path)

        sicapex_path = None
        if sicapex_pdf is not None and sicapex_pdf.filename:
            sicapex_path = workspace.input_dir / "ficha_sicapex.pdf"
            await _save_validated_upload(sicapex_pdf, sicapex_path, PDF_UPLOAD_POLICY)
        elif usar_sicapex_banco:
            context = _tempo_context_or_none(militar_id, db)
            if _context_requires_sicapex_pdf(context):
                raise bad_request(
                    "ERR_SICAPEX_REQUIRED_FOR_UNREGISTERED_OR_INCOMPLETE_MILITAR",
                    "Ficha SiCaPEx PDF e obrigatoria quando o militar nao possui contexto completo no banco.",
                )

        modelo_path = None
        if modelo_odt is not None and modelo_odt.filename:
            modelo_path = workspace.input_dir / "modelo.odt"
            await _save_validated_upload(modelo_odt, modelo_path, ODT_UPLOAD_POLICY)
        modelo_path, modelo_role, template_source = _resolve_modelo_path(
            workspace,
            modelo_path,
            usar_modelo_executavel_sisges=usar_modelo_executavel_sisges,
        )
        modelo_user_provided = _is_current_request_template(template_source)

        pkg = compile_folha_pipeline(
            bi_path=bi_path,
            bi_role=bi_role,
            sicapex_path=sicapex_path,
            modelo_path=modelo_path,
            modelo_role=modelo_role,
            template_source=template_source,
            modelo_user_provided=modelo_user_provided,
            militar_id=militar_id,
            bi_original_filename=alteracoes_upload.filename,
            sicapex_original_filename=sicapex_pdf.filename if sicapex_pdf else None,
            modelo_original_filename=modelo_odt.filename if modelo_odt else None,
            bi_mime_type=alteracoes_upload.content_type,
            sicapex_mime_type=sicapex_pdf.content_type if sicapex_pdf else None,
            modelo_mime_type=modelo_odt.content_type if modelo_odt else None,
            ano=ano,
            semestre=semestre,
            reparar_tabelas=reparar_tabelas,
            preservar_tabelas_odt=preservar_tabelas_odt,
            gerar_pdf_preview=gerar_pdf_preview,
            full_package=full_package,
            output_mode=output_mode,
            assinatura_mode=assinatura_mode,
            assinatura_nome=assinatura_nome,
            assinatura_funcao=assinatura_funcao,
            memory_reference_file_id=memory_reference_file_id,
            fonte_eventos=fonte_eventos,
            output_dir=workspace.output_dir,
            trace_id=workspace.trace_id,
            document_service=document_service,
            owner_user_id=owner_user_id,
            db=db,
        )
        return FileResponse(
            pkg.final_path,
            filename=pkg.filename,
            media_type=pkg.media_type,
            headers={
                "X-Sisges-Document-Id": pkg.document_id,
                "X-Sisges-Compiler-Run-Id": pkg.run_id,
                "X-Sisges-Package-Mode": pkg.package_mode,
            },
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/folha/compile-odt")
async def compile_folha_odt(
    bi_odt: UploadFile | None = File(default=None),
    fonte_alteracoes_pdf: UploadFile | None = File(default=None),
    fonte_alteracoes_odt: UploadFile | None = File(default=None),
    sicapex_pdf: UploadFile | None = File(default=None),
    modelo_odt: UploadFile | None = File(default=None),
    militar_id: int | None = Form(default=None),
    usar_sicapex_banco: bool = Form(True),
    ano: int = Form(2025),
    semestre: str = Form("2"),
    reparar_tabelas: bool = Form(True),
    preservar_tabelas_odt: bool = Form(True),
    gerar_pdf_preview: bool = Form(True),
    full_package: bool = Form(True),
    output_mode: str = Form(OUTPUT_MODE_FULL),
    assinatura_mode: str = Form("auto"),
    assinatura_nome: str | None = Form(default=None),
    assinatura_funcao: str | None = Form(default=None),
    usar_modelo_executavel_sisges: bool = Form(False),
    memory_reference_file_id: str | None = Form(default=None),
    fonte_eventos: str | None = Form(default=None),
    user=Depends(require_permission("compilador.generate_odt")),
    db=Depends(get_db),
):
    return await compile_folha_odt_package(
        bi_odt=bi_odt,
        fonte_alteracoes_pdf=fonte_alteracoes_pdf,
        fonte_alteracoes_odt=fonte_alteracoes_odt,
        sicapex_pdf=sicapex_pdf,
        modelo_odt=modelo_odt,
        militar_id=militar_id,
        usar_sicapex_banco=usar_sicapex_banco,
        ano=ano,
        semestre=semestre,
        reparar_tabelas=reparar_tabelas,
        preservar_tabelas_odt=preservar_tabelas_odt,
        gerar_pdf_preview=gerar_pdf_preview,
        full_package=full_package,
        output_mode=output_mode,
        assinatura_mode=assinatura_mode,
        assinatura_nome=assinatura_nome,
        assinatura_funcao=assinatura_funcao,
        usar_modelo_executavel_sisges=usar_modelo_executavel_sisges,
        memory_reference_file_id=memory_reference_file_id,
        fonte_eventos=fonte_eventos,
        document_service=DocumentService(db),
        owner_user_id=user.get("id"),
        db=db,
    )


@router.post("/folha/compile-from-memory")
def compile_folha_from_memory(
    payload: CompileFromMemoryPayload,
    user=Depends(require_permission("compilador.generate_odt")),
    db=Depends(get_db),
):
    from modules.compilador.application.compiler_memory_service import CompilerMemoryService

    memory_service = CompilerMemoryService(db)
    fonte = payload.fonte_alteracoes or FonteAlteracoesPayload(
        file_id=payload.alteracoes_file_id
    )
    if not fonte.file_id and not fonte.run_id:
        raise bad_request("ERR_BI_SOURCE_MISSING", "Informe a fonte de alteracoes da memoria.")

    alteracoes_file = None
    alteracoes_source = None
    if fonte.file_id:
        alteracoes_file, alteracoes_source = _validate_memory_file(
            memory_service,
            fonte.file_id,
            field_name="fonte_alteracoes.file_id",
            allowed_roles=ALTERACOES_ROLES,
            allowed_suffixes={".pdf", ".odt"},
        )
    elif fonte.run_id:
        candidates = [
            item
            for item in memory_service.list_files(fonte.run_id)
            if item.role in ALTERACOES_ROLES
        ]
        if not candidates:
            raise bad_request(
                "ERR_BI_SOURCE_MISSING",
                "Execucao informada nao possui fonte de alteracoes reutilizavel.",
            )
        alteracoes_file = candidates[0]
        alteracoes_source = Path(alteracoes_file.storage_path)

    assert alteracoes_file is not None
    assert alteracoes_source is not None

    sicapex_payload = payload.sicapex or SicapexPayload(
        type="MEMORY_FILE" if payload.sicapex_file_id else "GESTAO_PESSOAL_DB",
        file_id=payload.sicapex_file_id,
    )
    sicapex_file = None
    sicapex_source = None
    if sicapex_payload.file_id:
        sicapex_file, sicapex_source = _validate_memory_file(
            memory_service,
            sicapex_payload.file_id,
            field_name="sicapex.file_id",
            allowed_roles=SICAPEX_ROLES,
            allowed_suffixes={".pdf"},
        )
    else:
        context = _tempo_context_or_none(payload.militar_id, db)
        if _context_requires_sicapex_pdf(context):
            raise bad_request(
                "ERR_SICAPEX_REQUIRED_FOR_UNREGISTERED_OR_INCOMPLETE_MILITAR",
                "Ficha SiCaPEx PDF e obrigatoria quando o militar nao possui contexto completo no banco.",
            )

    modelo_payload = payload.modelo or ModeloPayload(
        type="MEMORY_FILE" if payload.modelo_file_id else "INTERNAL_DEFAULT",
        file_id=payload.modelo_file_id,
    )
    modelo_file = None
    modelo_source = None
    if modelo_payload.file_id:
        modelo_file, modelo_source = _validate_memory_file(
            memory_service,
            modelo_payload.file_id,
            field_name="modelo.file_id",
            allowed_roles=MODELO_ROLES,
            allowed_suffixes={".odt"},
        )
    usar_modelo_executavel_sisges = (modelo_payload.type or "").upper() in {
        "STORED_EXECUTABLE",
        "SISGES_EXECUTABLE",
        STORED_EXECUTABLE_MODELO_ODT,
    }

    alteracoes_suffix = Path(alteracoes_source).suffix.lower()
    bi_filename = "bi_alteracoes.pdf" if alteracoes_suffix == ".pdf" else "bi_alteracoes.odt"
    alteracoes_file, alteracoes_source = _validate_memory_file(
        memory_service,
        alteracoes_file.id,
        field_name="fonte_alteracoes.file_id",
        allowed_roles=ALTERACOES_ROLES,
        allowed_suffixes={".pdf", ".odt"},
    )

    with PipelineWorkspaceManager() as workspace:
        bi_path = workspace.input_dir / bi_filename
        sicapex_path = workspace.input_dir / "ficha_sicapex.pdf" if sicapex_source else None
        modelo_path = workspace.input_dir / "modelo.odt" if modelo_source else None
        shutil.copyfile(alteracoes_source, bi_path)
        if sicapex_source and sicapex_path:
            shutil.copyfile(sicapex_source, sicapex_path)
        if modelo_source and modelo_path:
            shutil.copyfile(modelo_source, modelo_path)
        modelo_path, modelo_role, template_source = _resolve_modelo_path(
            workspace,
            modelo_path,
            usar_modelo_executavel_sisges=usar_modelo_executavel_sisges,
        )
        modelo_user_provided = _is_current_request_template(template_source)

        pkg = compile_folha_pipeline(
            bi_path=bi_path,
            bi_role=alteracoes_file.role,
            sicapex_path=sicapex_path,
            modelo_path=modelo_path,
            modelo_role=modelo_role,
            template_source=template_source,
            modelo_user_provided=modelo_user_provided,
            militar_id=payload.militar_id,
            bi_original_filename=alteracoes_file.original_filename or alteracoes_file.filename,
            sicapex_original_filename=(
                sicapex_file.original_filename or sicapex_file.filename if sicapex_file else None
            ),
            modelo_original_filename=(
                modelo_file.original_filename or modelo_file.filename if modelo_file else None
            ),
            bi_mime_type=alteracoes_file.mime_type,
            sicapex_mime_type=sicapex_file.mime_type if sicapex_file else None,
            modelo_mime_type=modelo_file.mime_type if modelo_file else None,
            ano=payload.ano,
            semestre=payload.semestre,
            reparar_tabelas=payload.options.reparar_tabelas,
            preservar_tabelas_odt=payload.options.preservar_tabelas_odt,
            gerar_pdf_preview=payload.options.gerar_pdf_preview,
            full_package=payload.options.full_package,
            output_mode=payload.options.output_mode,
            assinatura_mode=payload.options.assinatura_mode,
            assinatura_nome=payload.options.assinatura_nome,
            assinatura_funcao=payload.options.assinatura_funcao,
            memory_reference_file_id=alteracoes_file.id,
            fonte_eventos=alteracoes_file.role,
            source_memory_file_ids={
                "alteracoes_file_id": alteracoes_file.id,
                "sicapex_file_id": sicapex_file.id if sicapex_file else None,
                "modelo_file_id": modelo_file.id if modelo_file else None,
            },
            output_dir=workspace.output_dir,
            trace_id=workspace.trace_id,
            document_service=DocumentService(db),
            owner_user_id=user.get("id"),
            db=db,
        )
        return FileResponse(
            pkg.final_path,
            filename=pkg.filename,
            media_type=pkg.media_type,
            headers={
                "X-Sisges-Document-Id": pkg.document_id,
                "X-Sisges-Compiler-Run-Id": pkg.run_id,
                "X-Sisges-Package-Mode": pkg.package_mode,
            },
        )
