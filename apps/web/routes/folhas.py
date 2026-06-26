from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from io import BytesIO, StringIO
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from apps.web.dependencies.auth import auth_http_exception, get_current_user, require_dev_mode, require_permission
from apps.web.errors import bad_request, not_found
from infra.persistence.db import get_db
from infra.persistence.transactions import atomic
from infra.pipeline.uploads import (
    FOLHA_PDF_UPLOAD_POLICY,
    ODT_UPLOAD_POLICY,
    PDF_UPLOAD_POLICY,
    TXT_UPLOAD_POLICY,
    ZIP_UPLOAD_POLICY,
    UploadValidationError,
    save_upload_to_path,
)
from modules.folhas.domain.validacoes import validar_nome_arquivo_folha
from modules.documents.application.services import DocumentService
from modules.folhas.application.schemas import (
    FolhaActionInput,
    FolhaCreate,
    FolhaDocumentUpdateHistoryItem,
    FolhaDocumentUpdateInput,
    FolhaDocumentUpdateRead,
    FolhaDocumentUpdateSummary,
    FolhaRead,
    FolhaUpdate,
    FolhaWorkflowRead,
)
from modules.folhas.application.services import FolhasService, document_update_file_dir
from modules.folhas.application.parte1_semiok_service import generate_parte1_from_semiok_uploads
from modules.folhas.infrastructure.repository import FolhasRepository
from scripts.complete_folha_semi_ok_parte1 import (
    build_pairs,
    process_pair,
    write_classification,
    write_reports,
)
from scripts.build_folha_executable_template import build_template

router = APIRouter(prefix="/folhas", tags=["folhas"])
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_OUTPUT_ROOT = PROJECT_ROOT / "data" / "output"
FOLHA_EXECUTABLE_TEMPLATE_FILENAME = "000_MODELO_SISGES_EXECUTAVEL_V1.odt"


class SemiOkParte1Request(BaseModel):
    input_dir: str = Field(..., min_length=1)
    output_dir: str | None = None
    semestre: str = Field(default="2", pattern="^[12]$")


class FolhaExecutableTemplateStatus(BaseModel):
    available: bool
    filename: str
    sha256: str | None = None
    size_bytes: int | None = None
    message: str


class PrepareFolhaExecutableTemplateRequest(BaseModel):
    source_odt: str = Field(..., min_length=1)


def _actor_id(user: dict) -> str | None:
    value = user.get("id") or user.get("user_id")
    return str(value) if value else None


def _handle_workflow_error(exc: Exception):
    if isinstance(exc, PermissionError):
        raise auth_http_exception(403, "FOLHA_FORBIDDEN", str(exc)) from exc

    message = str(exc)
    if "nao encontrada" in message.lower():
        raise not_found("FOLHA_NOT_FOUND", "Folha nao encontrada.") from exc

    raise bad_request("FOLHA_WORKFLOW_INVALID", message) from exc


def _document_update_upload_policy(filename: str, tipo_documento: str = ""):
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        # Folhas de Alterações têm limite de 10 MB (Port. 063-DGP/2020 Art. 27).
        return FOLHA_PDF_UPLOAD_POLICY if tipo_documento == "folha_alteracao" else PDF_UPLOAD_POLICY
    if suffix == ".odt":
        return ODT_UPLOAD_POLICY
    if suffix == ".zip":
        return ZIP_UPLOAD_POLICY
    raise bad_request(
        "DOCUMENT_UPDATE_UPLOAD_EXTENSION_INVALID",
        "Anexo deve ser PDF, ODT ou ZIP.",
    )


def _validar_nome_folha_pdf(filename: str, tipo_documento: str) -> list[str]:
    """Retorna avisos de nomenclatura quando tipo_documento == folha_alteracao.

    As strings retornadas são ASCII-only (usadas em HTTP headers).
    """
    if tipo_documento != "folha_alteracao":
        return []
    if Path(filename).suffix.lower() != ".pdf":
        return []
    if not validar_nome_arquivo_folha(filename):
        return [
            f"Nome '{filename}' nao segue o padrao Port. 063-DGP/2020 Art. 27 V: "
            "{identidade}_{ano}_{semestre}_{CodOM}.pdf (ex: 9990000001_2024_1_9999.pdf)"
        ]
    return []


def _parte1_source_upload_policy(filename: str):
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return PDF_UPLOAD_POLICY
    if suffix == ".txt":
        return TXT_UPLOAD_POLICY
    raise bad_request(
        "FOLHA_PARTE1_SOURCE_EXTENSION_INVALID",
        "Fonte da Parte 1 deve ser TXT oficial ou PDF.",
    )


def _now_suffix() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def _build_download_filename(folha, tipo: str) -> str:
    """Monta o nome de arquivo conforme Port. 063-DGP/2020 Art. 27 V.

    Formato: {identidade}_{ano}_{semestre}_{CodOM}.{tipo}
    Fallback para nome genérico se os metadados necessários não estiverem presentes.
    """
    header = folha.header_json or {}
    identidade = header.get("identidade") or (folha.militar.identidade if folha.militar else None)
    codom = header.get("codom")
    ano = header.get("ano") or (folha.periodo_inicio.year if folha.periodo_inicio else None)
    semestre = header.get("semestre") or (
        1 if folha.periodo_inicio and folha.periodo_inicio.month <= 6 else 2
        if folha.periodo_inicio else None
    )
    if identidade and ano and semestre and codom and str(codom).isdigit():
        return f"{identidade}_{ano}_{semestre}_{codom}.{tipo}"
    return f"folha_alteracoes_{folha.id}.{tipo}"


def _resolve_generation_input_dir(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    if not path.exists() or not path.is_dir():
        raise bad_request("FOLHA_GENERATION_INPUT_INVALID", "Pasta de entrada invalida.")
    return path


def _resolve_generation_output_dir(value: str | None) -> Path:
    if value:
        path = Path(value)
        if path.is_absolute():
            resolved = path.resolve()
        elif value.replace("\\", "/").startswith("data/output/"):
            resolved = (PROJECT_ROOT / path).resolve()
        else:
            resolved = (DATA_OUTPUT_ROOT / path).resolve()
    else:
        resolved = (DATA_OUTPUT_ROOT / "folhas_geracao" / "semi_ok_parte1" / _now_suffix()).resolve()

    output_root = DATA_OUTPUT_ROOT.resolve()
    if resolved != output_root and output_root not in resolved.parents:
        raise bad_request(
            "FOLHA_GENERATION_OUTPUT_INVALID",
            "Pasta de saida deve ficar dentro de data/output.",
        )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _folha_executable_template_path() -> Path:
    return DATA_OUTPUT_ROOT / "modelos" / FOLHA_EXECUTABLE_TEMPLATE_FILENAME


def _resolve_template_source_odt(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    if not path.exists() or not path.is_file() or path.suffix.lower() != ".odt":
        raise bad_request("FOLHA_TEMPLATE_SOURCE_INVALID", "Modelo de origem deve ser um arquivo ODT existente.")
    return path


def _build_folha_executable_template_response(source_odt: Path) -> dict:
    output_dir = DATA_OUTPUT_ROOT / "modelos"
    output_odt = output_dir / FOLHA_EXECUTABLE_TEMPLATE_FILENAME
    contract_json = output_dir / "000_MODELO_SISGES_EXECUTAVEL_V1.contract.json"
    report_txt = output_dir / "RELATORIO_MODELO_SISGES_EXECUTAVEL_V1.txt"

    try:
        result = build_template(source_odt, output_odt, contract_json, report_txt)
    except Exception as exc:
        raise bad_request("FOLHA_EXECUTABLE_TEMPLATE_BUILD_FAILED", str(exc)) from exc

    if result.status != "OK":
        raise bad_request(
            "FOLHA_EXECUTABLE_TEMPLATE_BUILD_FAILED",
            "Modelo executavel gerado com erro. Consulte o relatorio em data/output/modelos.",
        )

    return {
        "status": result.status,
        "source_odt": result.source_odt,
        "output_odt": result.output_odt,
        "contract_json": result.contract_json,
        "report_txt": result.report_txt,
        "flags_content_xml": result.flags_content_xml,
        "flags_styles_xml": result.flags_styles_xml,
        "structural_checks": result.structural_checks,
        "warnings": result.warnings,
        "sha256": hashlib.sha256(output_odt.read_bytes()).hexdigest(),
    }


def _get_document_update_or_404(db, document_id: str):
    document = DocumentService(db).get_document(document_id)
    if not document or document.source_module != "folhas.document_update":
        raise not_found("DOCUMENT_UPDATE_NOT_FOUND", "Update documental nao encontrado.")
    return document


def _document_update_files_or_404(document):
    metadata = document.metadata_json or {}
    manifest_path_raw = metadata.get("manifest_path")
    if not manifest_path_raw:
        raise not_found("DOCUMENT_UPDATE_MANIFEST_NOT_FOUND", "Manifesto do update documental nao registrado.")

    manifest_path = Path(str(manifest_path_raw))
    if not manifest_path.exists() or not manifest_path.is_file():
        raise not_found("DOCUMENT_UPDATE_MANIFEST_NOT_FOUND", "Arquivo de manifesto nao encontrado.")

    uploaded_file = metadata.get("uploaded_file") or {}
    uploaded_path_raw = uploaded_file.get("storage_path")
    uploaded_path = Path(str(uploaded_path_raw)) if uploaded_path_raw else None
    if uploaded_path and (not uploaded_path.exists() or not uploaded_path.is_file()):
        raise not_found("DOCUMENT_UPDATE_FILE_NOT_FOUND", "Arquivo do update documental nao encontrado.")

    return manifest_path, uploaded_path


def _document_update_attachment_or_404(document) -> Path:
    metadata = document.metadata_json or {}
    uploaded_file = metadata.get("uploaded_file") or {}
    uploaded_path_raw = uploaded_file.get("storage_path")
    if not uploaded_path_raw:
        raise not_found("DOCUMENT_UPDATE_FILE_NOT_FOUND", "Update documental nao possui anexo.")

    uploaded_path = Path(str(uploaded_path_raw))
    if not uploaded_path.exists() or not uploaded_path.is_file():
        raise not_found("DOCUMENT_UPDATE_FILE_NOT_FOUND", "Arquivo do update documental nao encontrado.")
    return uploaded_path


def _write_document_update_audit_entries(archive: ZipFile, document, *, prefix: str = "") -> None:
    manifest_path, uploaded_path = _document_update_files_or_404(document)
    base = f"{prefix}{document.id}/" if prefix else ""
    archive.write(manifest_path, f"{base}manifesto_update_{document.id}.json")
    if uploaded_path:
        archive.write(uploaded_path, f"{base}anexo/{Path(document.filename or uploaded_path.name).name}")


def _document_update_index_rows(items: list[FolhaDocumentUpdateHistoryItem]) -> list[dict]:
    rows: list[dict] = []
    for item in items:
        rows.append(
            {
                "document_id": item.document_id,
                "status": item.status,
                "tipo_documento": item.tipo_documento,
                "ano": item.ano,
                "semestre": item.semestre,
                "codom": item.codom,
                "cpf_masked": item.cpf_masked,
                "militar_id": item.militar_id,
                "militar_nome": item.militar_nome,
                "uploaded_filename": item.uploaded_filename,
                "sha256": item.uploaded_sha256 or item.output_sha256,
                "trace_id": item.trace_id,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
        )
    return rows


def _document_update_index_csv(rows: list[dict]) -> str:
    output = StringIO()
    fieldnames = [
        "document_id",
        "status",
        "tipo_documento",
        "ano",
        "semestre",
        "codom",
        "cpf_masked",
        "militar_id",
        "militar_nome",
        "uploaded_filename",
        "sha256",
        "trace_id",
        "created_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


@router.get("", response_model=list[FolhaRead])
def list_folhas(
    status: str | None = Query(default=None),
    militar_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user=Depends(require_permission("mod.folhas.view")),
    db=Depends(get_db),
):
    return FolhasRepository(db).list(
        status=status,
        militar_id=militar_id,
        limit=limit,
    )


@router.post("")
def create_folha(
    payload: FolhaCreate,
    user=Depends(require_permission("mod.folhas.create")),
    db=Depends(get_db),
):
    folha, tarefa = FolhasService(db).create_folha_with_task(
        payload=payload,
        actor_user_id=user["id"],
    )
    return {
        "folha": FolhaRead.model_validate(folha).model_dump(),
        "tarefa": {
            "id": tarefa.id,
            "titulo": tarefa.titulo,
            "status": tarefa.status,
            "responsavel_user_id": tarefa.responsavel_user_id,
        },
    }


@router.get("/workflows", response_model=list[FolhaWorkflowRead])
def list_folha_workflows(
    status: str | None = Query(default=None),
    scope: str = Query(default="todas", pattern="^(todas|minhas|assinatura)$"),
    limit: int = Query(default=100, ge=1, le=500),
    user=Depends(require_permission("mod.folhas.view")),
    db=Depends(get_db),
):
    return FolhasService(db).list_workflows(
        status=status,
        scope=scope,
        user=user,
        limit=limit,
    )


@router.get("/minhas", response_model=list[FolhaWorkflowRead])
def list_minhas_folhas(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    return FolhasService(db).list_workflows(
        status=status,
        scope="minhas",
        user=user,
        limit=limit,
    )


@router.get("/assinatura", response_model=list[FolhaWorkflowRead])
def list_folhas_para_assinatura(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user=Depends(require_permission("mod.folhas.finalize")),
    db=Depends(get_db),
):
    return FolhasService(db).list_workflows(
        status=status,
        scope="assinatura",
        user=user,
        limit=limit,
    )


@router.get("/documentos/updates", response_model=list[FolhaDocumentUpdateHistoryItem])
def list_folha_document_updates(
    limit: int = Query(default=50, ge=1, le=100),
    tipo_documento: str | None = Query(default=None),
    ano: int | None = Query(default=None, ge=1900, le=2100),
    semestre: int | None = Query(default=None, ge=1, le=2),
    codom: str | None = Query(default=None),
    cpf: str | None = Query(default=None),
    has_upload: bool | None = Query(default=None),
    user=Depends(require_permission("mod.folhas.review")),
    db=Depends(get_db),
):
    return FolhasService(db).list_document_updates(
        limit=limit,
        tipo_documento=tipo_documento,
        ano=ano,
        semestre=semestre,
        codom=codom,
        cpf=cpf,
        has_upload=has_upload,
    )


@router.get("/documentos/updates/summary", response_model=FolhaDocumentUpdateSummary)
def summarize_folha_document_updates(
    limit: int = Query(default=5000, ge=1, le=5000),
    tipo_documento: str | None = Query(default=None),
    ano: int | None = Query(default=None, ge=1900, le=2100),
    semestre: int | None = Query(default=None, ge=1, le=2),
    codom: str | None = Query(default=None),
    cpf: str | None = Query(default=None),
    has_upload: bool | None = Query(default=None),
    user=Depends(require_permission("mod.folhas.review")),
    db=Depends(get_db),
):
    return FolhasService(db).summarize_document_updates(
        limit=limit,
        tipo_documento=tipo_documento,
        ano=ano,
        semestre=semestre,
        codom=codom,
        cpf=cpf,
        has_upload=has_upload,
    )


@router.get("/documentos/updates/export.csv")
def export_folha_document_updates_csv(
    limit: int = Query(default=1000, ge=1, le=5000),
    tipo_documento: str | None = Query(default=None),
    ano: int | None = Query(default=None, ge=1900, le=2100),
    semestre: int | None = Query(default=None, ge=1, le=2),
    codom: str | None = Query(default=None),
    cpf: str | None = Query(default=None),
    has_upload: bool | None = Query(default=None),
    user=Depends(require_permission("mod.folhas.review")),
    db=Depends(get_db),
):
    items = FolhasService(db).list_document_updates(
        limit=limit,
        tipo_documento=tipo_documento,
        ano=ano,
        semestre=semestre,
        codom=codom,
        cpf=cpf,
        has_upload=has_upload,
    )

    return Response(
        content=_document_update_index_csv(_document_update_index_rows(items)),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="folhas_document_updates.csv"'},
    )


@router.get("/documentos/updates/audit.zip")
def export_folha_document_updates_audit_zip(
    limit: int = Query(default=100, ge=1, le=500),
    tipo_documento: str | None = Query(default=None),
    ano: int | None = Query(default=None, ge=1900, le=2100),
    semestre: int | None = Query(default=None, ge=1, le=2),
    codom: str | None = Query(default=None),
    cpf: str | None = Query(default=None),
    has_upload: bool | None = Query(default=None),
    user=Depends(require_permission("mod.folhas.review")),
    db=Depends(get_db),
):
    service = FolhasService(db)
    items = service.list_document_updates(
        limit=limit,
        tipo_documento=tipo_documento,
        ano=ano,
        semestre=semestre,
        codom=codom,
        cpf=cpf,
        has_upload=has_upload,
    )
    summary_limit = 5000
    summary = service.summarize_document_updates(
        limit=summary_limit,
        tipo_documento=tipo_documento,
        ano=ano,
        semestre=semestre,
        codom=codom,
        cpf=cpf,
        has_upload=has_upload,
    )
    buffer = BytesIO()
    index_rows = _document_update_index_rows(items)
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "README_AUDITORIA_LOTE.txt",
            "\n".join(
                [
                    "Pacote de auditoria em lote dos updates documentais SISGES.",
                    f"total_registros: {len(items)}",
                    f"export_limit: {limit}",
                    f"known_filtered_count: {summary.total}",
                    f"partial_package: {summary.total > len(items)}",
                    f"tipo_documento: {tipo_documento or 'todos'}",
                    f"ano: {ano or 'todos'}",
                    f"semestre: {semestre or 'todos'}",
                    f"codom: {codom or 'todos'}",
                    f"cpf_filter_applied: {bool(cpf)}",
                    f"has_upload: {has_upload if has_upload is not None else 'todos'}",
                    "contexto: contexto_auditoria.json",
                    "CPF bruto nao e escrito neste README nem nos manifestos operacionais.",
                ]
            )
            + "\n",
        )
        archive.writestr(
            "contexto_auditoria.json",
            json.dumps(
                {
                    "schema_version": "folhas-document-update-audit-context-v1",
                    "package_kind": "FOLHAS_DOCUMENT_UPDATES_AUDIT_BATCH",
                    "export": {
                        "export_limit": limit,
                        "exported_count": len(items),
                        "is_partial": summary.total > len(items),
                        "known_filtered_count": summary.total,
                        "summary_limit": summary_limit,
                    },
                    "summary": summary.model_dump(mode="json"),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
        )
        archive.writestr(
            "indice_auditoria.json",
            json.dumps(index_rows, ensure_ascii=False, indent=2, sort_keys=True),
        )
        archive.writestr("indice_auditoria.csv", _document_update_index_csv(index_rows))
        for item in items:
            document = _get_document_update_or_404(db, item.document_id)
            _write_document_update_audit_entries(archive, document, prefix="updates/")

    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="folhas_document_updates_auditoria.zip"'},
    )


@router.post("/documentos/update", response_model=FolhaDocumentUpdateRead)
def register_folha_document_update(
    payload: FolhaDocumentUpdateInput,
    user=Depends(require_permission("mod.folhas.review")),
    db=Depends(get_db),
):
    return FolhasService(db).register_document_update(
        payload=payload,
        actor_user_id=_actor_id(user),
    )


@router.get("/documentos/updates/{document_id}/download")
def download_folha_document_update(
    document_id: str,
    user=Depends(require_permission("mod.folhas.review")),
    db=Depends(get_db),
):
    document = _get_document_update_or_404(db, document_id)
    file_path = _document_update_attachment_or_404(document)

    return FileResponse(
        path=str(file_path),
        filename=document.filename or file_path.name,
        media_type="application/octet-stream",
    )


@router.get("/documentos/updates/{document_id}/manifest")
def download_folha_document_update_manifest(
    document_id: str,
    user=Depends(require_permission("mod.folhas.review")),
    db=Depends(get_db),
):
    document = _get_document_update_or_404(db, document_id)
    manifest_path, _uploaded_path = _document_update_files_or_404(document)

    return FileResponse(
        path=str(manifest_path),
        filename=f"manifesto_update_{document.id}.json",
        media_type="application/json",
    )


@router.get("/documentos/updates/{document_id}/audit.zip")
def download_folha_document_update_audit_package(
    document_id: str,
    user=Depends(require_permission("mod.folhas.review")),
    db=Depends(get_db),
):
    document = _get_document_update_or_404(db, document_id)
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        _write_document_update_audit_entries(archive, document)
        archive.writestr(
            "README_AUDITORIA.txt",
            "\n".join(
                [
                    "Pacote de auditoria do update documental SISGES.",
                    f"document_id: {document.id}",
                    f"trace_id: {document.trace_id or ''}",
                    "Conteudo: manifesto operacional e anexo original, quando existente.",
                ]
            )
            + "\n",
        )

    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="auditoria_update_{document.id}.zip"',
        },
    )


@router.post("/documentos/update-upload", response_model=FolhaDocumentUpdateRead)
async def register_folha_document_update_upload(
    tipo_documento: str = Form(default="folha_alteracao"),
    ano: int = Form(...),
    semestre: int = Form(...),
    cpf: str = Form(...),
    codom: str = Form(...),
    observacao: str | None = Form(default=None),
    arquivo: UploadFile | None = File(default=None),
    user=Depends(require_permission("mod.folhas.review")),
    db=Depends(get_db),
):
    payload = FolhaDocumentUpdateInput(
        tipo_documento=tipo_documento,
        ano=ano,
        semestre=semestre,
        cpf=cpf,
        codom=codom,
        observacao=observacao,
    )
    trace_id = uuid4().hex
    uploaded_file_path: str | None = None
    uploaded_filename: str | None = None
    uploaded_mime_type: str | None = None
    uploaded_size_bytes: int | None = None
    uploaded_sha256: str | None = None

    filename_warnings: list[str] = []
    if arquivo and arquivo.filename:
        original_name = Path(arquivo.filename).name
        policy = _document_update_upload_policy(original_name, payload.tipo_documento)
        target_path = document_update_file_dir() / f"{trace_id}_{original_name}"
        try:
            uploaded_size_bytes = await save_upload_to_path(arquivo, target_path, policy)
        except UploadValidationError as exc:
            raise bad_request(exc.code, exc.message) from exc

        uploaded_file_path = str(target_path)
        uploaded_filename = original_name
        uploaded_mime_type = arquivo.content_type
        uploaded_sha256 = hashlib.sha256(target_path.read_bytes()).hexdigest()
        filename_warnings = _validar_nome_folha_pdf(original_name, payload.tipo_documento)

    result = FolhasService(db).register_document_update(
        payload=payload,
        actor_user_id=_actor_id(user),
        uploaded_file_path=uploaded_file_path,
        uploaded_filename=uploaded_filename,
        uploaded_mime_type=uploaded_mime_type,
        uploaded_size_bytes=uploaded_size_bytes,
        uploaded_sha256=uploaded_sha256,
        trace_id=trace_id,
    )
    if filename_warnings:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            content=result.model_dump(mode="json"),
            headers={
                "X-Sisges-Filename-Warnings": "; ".join(filename_warnings),
                "X-Sisges-Filename-Warnings-Count": str(len(filename_warnings)),
            },
        )
    return result


@router.post("/geracao/semi-ok-parte1/upload")
async def process_folha_semi_ok_parte1_upload(
    odt_semi_pronto: UploadFile = File(...),
    fonte_parte1: UploadFile = File(...),
    semestre: str = Form(default="2", pattern="^[12]$"),
    user=Depends(get_current_user),
):
    trace_id = uuid4().hex
    input_dir = DATA_OUTPUT_ROOT / "folhas_geracao" / "parte1_uploads" / trace_id / "inputs"
    semi_filename = Path(odt_semi_pronto.filename or "folha_semi_pronta.odt").name
    fonte_filename = Path(fonte_parte1.filename or "fonte_parte1.txt").name
    semi_path = input_dir / f"semi_{semi_filename}"
    fonte_path = input_dir / f"parte1_{fonte_filename}"

    try:
        await save_upload_to_path(odt_semi_pronto, semi_path, ODT_UPLOAD_POLICY)
        await save_upload_to_path(fonte_parte1, fonte_path, _parte1_source_upload_policy(fonte_filename))
    except UploadValidationError as exc:
        raise bad_request(exc.code, exc.message) from exc

    try:
        package = generate_parte1_from_semiok_uploads(
            semi_odt=semi_path,
            fonte_parte1=fonte_path,
            output_root=DATA_OUTPUT_ROOT,
            semestre=semestre,
            actor_user_id=_actor_id(user),
            run_id=trace_id,
        )
    except Exception as exc:
        raise bad_request("FOLHA_PARTE1_GENERATION_FAILED", str(exc)) from exc

    return FileResponse(
        path=str(package.package_path),
        filename=package.package_filename,
        media_type="application/zip",
        headers={
            "X-Sisges-Folhas-Generation-Status": package.status,
            "X-Sisges-Folhas-Warnings-Count": str(len(package.warnings)),
        },
    )


@router.post("/geracao/semi-ok-parte1/process")
def process_folhas_semi_ok_parte1(
    payload: SemiOkParte1Request,
    user=Depends(require_dev_mode),
):
    input_dir = _resolve_generation_input_dir(payload.input_dir)
    output_dir = _resolve_generation_output_dir(payload.output_dir)

    pairs, classified = build_pairs(input_dir)
    write_classification(output_dir, classified, pairs)
    results = [process_pair(pair, output_dir, payload.semestre) for pair in pairs]
    write_reports(output_dir, input_dir, results)

    return {
        "status": "CONCLUIDO" if not any(item.status == "ERROR" for item in results) else "COM_ERROS",
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "semestre": payload.semestre,
        "total_pares": len(results),
        "ok": sum(item.status == "OK" for item in results),
        "ok_with_warnings": sum(item.status == "OK_WITH_WARNINGS" for item in results),
        "errors": sum(item.status == "ERROR" for item in results),
        "reports": {
            "matriz": str(output_dir / "matriz_pares_semi_ok.csv"),
            "resumo_csv": str(output_dir / "resumo_lote_semi_ok_parte1.csv"),
            "resumo_json": str(output_dir / "resumo_lote_semi_ok_parte1.json"),
            "relatorio_txt": str(output_dir / "RELATORIO_LOTE_SEMI_OK_PARTE1.txt"),
        },
        "items": [
            {
                "key": item.key,
                "status": item.status,
                "warnings": item.warnings,
                "errors": item.errors,
                "output_odt": item.output_odt,
                "inserted_lines": item.inserted_lines,
            }
            for item in results
        ],
    }


@router.post("/geracao/modelo-executavel/preparar")
def prepare_folha_executable_template(
    payload: PrepareFolhaExecutableTemplateRequest,
    user=Depends(require_dev_mode),
):
    source_odt = _resolve_template_source_odt(payload.source_odt)
    return _build_folha_executable_template_response(source_odt)


@router.post("/geracao/modelo-executavel/preparar-upload")
async def prepare_folha_executable_template_upload(
    modelo_odt: UploadFile = File(...),
    user=Depends(require_dev_mode),
):
    original_name = Path(modelo_odt.filename or "modelo_base.odt").name
    if Path(original_name).suffix.lower() != ".odt":
        raise bad_request("FOLHA_TEMPLATE_SOURCE_INVALID", "Modelo de origem deve ser um arquivo ODT.")

    source_dir = DATA_OUTPUT_ROOT / "modelos" / "fontes"
    target_path = source_dir / f"{uuid4().hex}_{original_name}"
    try:
        await save_upload_to_path(modelo_odt, target_path, ODT_UPLOAD_POLICY)
    except UploadValidationError as exc:
        raise bad_request(exc.code, exc.message) from exc

    return _build_folha_executable_template_response(target_path)


@router.get("/geracao/modelo-executavel/status", response_model=FolhaExecutableTemplateStatus)
def get_folha_executable_template_status(
    user=Depends(require_permission("compilador.generate_odt")),
):
    template_path = _folha_executable_template_path()
    if not template_path.exists() or not template_path.is_file():
        return FolhaExecutableTemplateStatus(
            available=False,
            filename=FOLHA_EXECUTABLE_TEMPLATE_FILENAME,
            message="Modelo executavel SISGES ainda nao foi gerado no backend.",
        )

    return FolhaExecutableTemplateStatus(
        available=True,
        filename=FOLHA_EXECUTABLE_TEMPLATE_FILENAME,
        sha256=hashlib.sha256(template_path.read_bytes()).hexdigest(),
        size_bytes=template_path.stat().st_size,
        message="Modelo executavel SISGES disponivel para download.",
    )


@router.get("/geracao/modelo-executavel/download")
def download_folha_executable_template(
    user=Depends(require_permission("compilador.generate_odt")),
):
    template_path = _folha_executable_template_path()
    if not template_path.exists() or not template_path.is_file():
        raise not_found(
            "FOLHA_EXECUTABLE_TEMPLATE_NOT_FOUND",
            "Modelo executavel SISGES nao encontrado. Gere o modelo com scripts.build_folha_executable_template.",
        )

    return FileResponse(
        path=str(template_path),
        filename=FOLHA_EXECUTABLE_TEMPLATE_FILENAME,
        media_type="application/vnd.oasis.opendocument.text",
    )


@router.get("/{folha_id}", response_model=FolhaWorkflowRead)
def get_folha_workflow(
    folha_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    folha = FolhasRepository(db).get(folha_id)
    if not folha:
        raise not_found("FOLHA_NOT_FOUND", "Folha nao encontrada.")
    service = FolhasService(db)
    try:
        service.ensure_user_can_access_folha(folha, user)
    except Exception as exc:
        _handle_workflow_error(exc)
    return service.to_workflow_read(folha, user=user)


@router.get("/{folha_id}/download")
def download_folha_documento(
    folha_id: int,
    tipo: str = Query(default="pdf", pattern="^(pdf|odt)$"),
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    folha = FolhasRepository(db).get(folha_id)
    if not folha:
        raise not_found("FOLHA_NOT_FOUND", "Folha nao encontrada.")

    service = FolhasService(db)
    try:
        service.ensure_user_can_access_folha(folha, user)
    except Exception as exc:
        _handle_workflow_error(exc)

    raw_path = folha.pdf_path if tipo == "pdf" else folha.odt_path
    if not raw_path:
        raise not_found("FOLHA_FILE_NOT_FOUND", f"Arquivo {tipo.upper()} nao registrado para esta folha.")

    file_path = Path(raw_path)
    if not file_path.exists() or not file_path.is_file():
        raise not_found("FOLHA_FILE_NOT_FOUND", f"Arquivo {tipo.upper()} nao encontrado no storage.")

    filename = _build_download_filename(folha, tipo)
    media_type = "application/pdf" if tipo == "pdf" else "application/vnd.oasis.opendocument.text"
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type=media_type,
    )


@router.post("/{folha_id}/liberar-ciencia", response_model=FolhaWorkflowRead)
def liberar_folha_para_ciencia(
    folha_id: int,
    payload: FolhaActionInput | None = None,
    user=Depends(require_permission("mod.folhas.review")),
    db=Depends(get_db),
):
    try:
        folha = FolhasService(db).liberar_ciencia(
            folha_id,
            payload or FolhaActionInput(),
            _actor_id(user),
        )
    except Exception as exc:
        _handle_workflow_error(exc)
    return FolhasService(db).to_workflow_read(folha, user=user)


@router.post("/{folha_id}/aprovar", response_model=FolhaWorkflowRead)
def aprovar_folha_pelo_militar(
    folha_id: int,
    payload: FolhaActionInput | None = None,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    try:
        folha = FolhasService(db).aprovar_militar(
            folha_id,
            payload or FolhaActionInput(),
            user,
        )
    except Exception as exc:
        _handle_workflow_error(exc)
    return FolhasService(db).to_workflow_read(folha, user=user)


@router.post("/{folha_id}/devolver", response_model=FolhaWorkflowRead)
def devolver_folha_pelo_militar(
    folha_id: int,
    payload: FolhaActionInput,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    try:
        folha = FolhasService(db).devolver_militar(folha_id, payload, user)
    except Exception as exc:
        _handle_workflow_error(exc)
    return FolhasService(db).to_workflow_read(folha, user=user)


@router.post("/{folha_id}/enviar-assinatura", response_model=FolhaWorkflowRead)
def enviar_folha_para_assinatura(
    folha_id: int,
    payload: FolhaActionInput | None = None,
    user=Depends(require_permission("mod.folhas.review")),
    db=Depends(get_db),
):
    try:
        folha = FolhasService(db).enviar_assinatura(
            folha_id,
            payload or FolhaActionInput(),
            _actor_id(user),
        )
    except Exception as exc:
        _handle_workflow_error(exc)
    return FolhasService(db).to_workflow_read(folha, user=user)


@router.post("/{folha_id}/assinar", response_model=FolhaWorkflowRead)
def assinar_folha(
    folha_id: int,
    payload: FolhaActionInput | None = None,
    user=Depends(require_permission("mod.folhas.finalize")),
    db=Depends(get_db),
):
    try:
        folha = FolhasService(db).assinar(folha_id, payload or FolhaActionInput(), user)
    except Exception as exc:
        _handle_workflow_error(exc)
    return FolhasService(db).to_workflow_read(folha, user=user)


@router.patch("/{folha_id}", response_model=FolhaRead)
def update_folha(
    folha_id: int,
    payload: FolhaUpdate,
    user=Depends(require_permission("mod.folhas.edit")),
    db=Depends(get_db),
):
    try:
        with atomic(db):
            folha = FolhasService(db).update_folha(folha_id, payload)
    except ValueError as exc:
        raise bad_request("FOLHA_PART2_INVALID", str(exc)) from exc
    if not folha:
        raise not_found("FOLHA_NOT_FOUND", "Folha nao encontrada.")
    return folha
