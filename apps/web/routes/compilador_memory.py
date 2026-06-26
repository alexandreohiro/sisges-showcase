from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
import zipfile

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from apps.web.dependencies.auth import require_permission
from apps.web.errors import bad_request
from infra.persistence.db import get_db
from infra.pipeline.uploads import PDF_UPLOAD_POLICY, UploadValidationError, save_upload_to_path
from infra.pipeline.workspace import PipelineWorkspaceManager
from modules.calculo_tempo_servico.application.sicapex_context import build_tempo_servico_context
from modules.compilador.application.compiler_memory_service import CompilerMemoryService
from modules.compilador.application.folha_alteracoes_compiler import (
    CompilerOptions,
    FolhaAlteracoesCompiler,
)
from modules.compilador.application.reference_folha_pdf_parser import (
    compiler_validations_from_parse,
    parse_reference_folha_pdf,
)
from modules.documents.application.services import DocumentService
from modules.gestao_pessoal.importadores.sicapex.parser import parse_sicapex_pdf
from modules.gestao_pessoal.importadores.sicapex.service import SicapexImportService
from shared.utils.hashing import sha256_file

router = APIRouter(prefix="/compilador", tags=["compilador-memory"])


@router.post("/memory/reference-pdf")
async def upload_reference_pdf(
    pdf: UploadFile = File(...),
    militar_id: int | None = None,
    tipo_documento: str = Query(default="folha_alteracoes"),
    user=Depends(require_permission("compilador.memory.upload")),
    db=Depends(get_db),
):
    temp_path = None
    try:
        suffix = Path(pdf.filename or "referencia.pdf").suffix or ".pdf"
        with NamedTemporaryFile(delete=False, suffix=suffix) as temp:
            temp_path = Path(temp.name)
        await save_upload_to_path(pdf, temp_path, PDF_UPLOAD_POLICY)

        parse_result = parse_reference_folha_pdf(temp_path)
        service = CompilerMemoryService(db)
        run = service.create_run(
            tipo_compilacao="MEMORY_REFERENCE_FOLHA_PDF",
            created_by_user_id=user.get("id"),
            militar_id=militar_id,
            nome_militar_snapshot=parse_result.nome_completo,
            identidade_snapshot=parse_result.identidade,
            posto_grad_snapshot=parse_result.posto_graduacao,
            periodo_inicio=parse_result.periodo_inicio,
            periodo_fim=parse_result.periodo_fim,
            ano=parse_result.ano,
            semestre=parse_result.semestre,
            fonte_tempo="TRANSCRITO_DE_FOLHA_PDF_MEMORIA",
            fonte_eventos="MEMORY_REFERENCE_FOLHA_PDF",
        )
        compiler_file = service.register_reference_file(
            source_path=temp_path,
            role="MEMORY_REFERENCE_FOLHA_PDF",
            original_filename=pdf.filename,
            mime_type=pdf.content_type,
            owner_user_id=user.get("id"),
            militar_id=militar_id,
            source_kind=tipo_documento,
            page_count=parse_result.page_count,
        )
        compiler_file.run_id = run.id
        snapshot = service.save_variable_snapshot(
            run_id=run.id,
            file_id=compiler_file.id,
            militar_id=militar_id,
            variables_json=parse_result.to_variables(),
            warnings_json=parse_result.warnings,
            pending_json=parse_result.pending,
            confidence_json={"parser": "reference_folha_pdf_v1"},
        )
        service.add_validations(
            compiler_validations_from_parse(parse_result, file_id=compiler_file.id)
            + [
                {
                    "run_id": run.id,
                    "level": "OK",
                    "code": "OK_FILE_STORED",
                    "message": "PDF salvo na memoria persistente do Compilador.",
                    "file_id": compiler_file.id,
                },
                {
                    "run_id": run.id,
                    "level": "OK",
                    "code": "OK_HASH_COMPUTED",
                    "message": "Hash SHA-256 calculado para o PDF de referencia.",
                    "file_id": compiler_file.id,
                },
                {
                    "run_id": run.id,
                    "level": "OK",
                    "code": "OK_DOCUMENT_REGISTERED",
                    "message": "Documento registrado no historico geral.",
                    "file_id": compiler_file.id,
                },
            ]
        )
        service.finalize_run(run, has_pending=bool(parse_result.pending))
        db.commit()
    except UploadValidationError as exc:
        raise bad_request(exc.code, exc.message) from exc
    except Exception as exc:
        db.rollback()
        raise bad_request("ERR_STORAGE_FAILED", f"Falha ao salvar PDF de referencia: {exc}") from exc
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()

    return {
        "file_id": compiler_file.id,
        "run_id": run.id,
        "document_id": compiler_file.document_id,
        "sha256": compiler_file.sha256,
        "storage_path": compiler_file.storage_path,
        "variables": snapshot.variables_json,
        "warnings": snapshot.warnings_json or [],
        "pending": snapshot.pending_json or [],
        "status": "STORED",
    }


@router.get("/memory/references")
def list_references(
    militar_id: int | None = None,
    nome: str | None = None,
    identidade: str | None = None,
    ano: int | None = None,
    semestre: str | None = None,
    tipo_documento: str | None = None,
    role: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    user=Depends(require_permission("compilador.memory.view")),
    db=Depends(get_db),
):
    service = CompilerMemoryService(db)
    files = service.list_references(
        militar_id=militar_id,
        nome=nome,
        identidade=identidade,
        ano=ano,
        semestre=semestre,
        tipo_documento=tipo_documento,
        role=role,
        limit=limit,
    )
    return {"items": [reference_to_dict(service, item) for item in files]}


@router.get("/runs")
def list_runs(
    militar_id: int | None = None,
    nome: str | None = None,
    identidade: str | None = None,
    ano: int | None = None,
    semestre: str | None = None,
    status: str | None = None,
    tipo_compilacao: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    user=Depends(require_permission("compilador.memory.view")),
    db=Depends(get_db),
):
    service = CompilerMemoryService(db)
    runs = service.list_runs(
        militar_id=militar_id,
        nome=nome,
        identidade=identidade,
        ano=ano,
        semestre=semestre,
        status=status,
        tipo_compilacao=tipo_compilacao,
        limit=limit,
    )
    return {"items": [run_to_dict(item) for item in runs]}


@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    user=Depends(require_permission("compilador.memory.view")),
    db=Depends(get_db),
):
    service = CompilerMemoryService(db)
    run = service.get_run_detail(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Execucao do Compilador nao encontrada.")
    return {
        "run": run_to_dict(run),
        "files": [file_to_dict(item) for item in service.list_files(run_id)],
        "variables": [snapshot_to_dict(item) for item in service.snapshots_for_run(run_id)],
        "validations": [validation_to_dict(item) for item in service.validations_for_run(run_id)],
    }


@router.get("/runs/{run_id}/files")
def get_run_files(
    run_id: str,
    user=Depends(require_permission("compilador.memory.view")),
    db=Depends(get_db),
):
    service = CompilerMemoryService(db)
    return {"items": [file_to_dict(item) for item in service.list_files(run_id)]}


@router.get("/runs/{run_id}/variables")
def get_run_variables(
    run_id: str,
    user=Depends(require_permission("compilador.memory.view")),
    db=Depends(get_db),
):
    service = CompilerMemoryService(db)
    return {"items": [snapshot_to_dict(item) for item in service.snapshots_for_run(run_id)]}


@router.get("/runs/{run_id}/validations")
def get_run_validations(
    run_id: str,
    user=Depends(require_permission("compilador.memory.view")),
    db=Depends(get_db),
):
    service = CompilerMemoryService(db)
    return {"items": [validation_to_dict(item) for item in service.validations_for_run(run_id)]}


@router.post("/runs/{run_id}/reprocess")
def reprocess_run(
    run_id: str,
    user=Depends(require_permission("compilador.reprocess")),
    db=Depends(get_db),
):
    service = CompilerMemoryService(db)
    run = service.get_run_detail(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Execucao do Compilador nao encontrada.")
    try:
        if run.tipo_compilacao == "MEMORY_REFERENCE_FOLHA_PDF":
            payload = _reprocess_reference_pdf(service, run)
        elif run.tipo_compilacao == "FOLHA_ALTERACOES_ODT":
            payload = _reprocess_folha_odt(service, run, owner_user_id=user.get("id"), db=db)
        else:
            raise bad_request(
                "REPROCESSAMENTO_NAO_SUPORTADO",
                f"Tipo de execucao nao suportado para reprocessamento: {run.tipo_compilacao}.",
            )
        db.commit()
    except Exception as exc:
        db.rollback()
        run = service.get_run_detail(run_id)
        if run:
            service.fail_run(run, error_message=str(exc))
            db.commit()
        raise bad_request("REPROCESSAMENTO_FALHOU", f"Falha ao reprocessar run: {exc}") from exc

    return payload


def _reprocess_reference_pdf(service: CompilerMemoryService, run) -> dict:
    reference_file = next(
        (
            item
            for item in service.list_files(run.id)
            if item.role == "MEMORY_REFERENCE_FOLHA_PDF"
        ),
        None,
    )
    if not reference_file:
        raise bad_request(
            "REPROCESSAMENTO_SEM_REFERENCIA_PDF",
            "Este run ainda nao possui PDF de Folha salvo na memoria para reprocessar.",
        )

    pdf_path = service.download_file(reference_file.id)
    parse_result = parse_reference_folha_pdf(pdf_path)
    run.status = "EXTRAINDO_VARIAVEIS"
    run.nome_militar_snapshot = parse_result.nome_completo or run.nome_militar_snapshot
    run.identidade_snapshot = parse_result.identidade or run.identidade_snapshot
    run.posto_grad_snapshot = parse_result.posto_graduacao or run.posto_grad_snapshot
    run.periodo_inicio = parse_result.periodo_inicio or run.periodo_inicio
    run.periodo_fim = parse_result.periodo_fim or run.periodo_fim
    run.ano = parse_result.ano or run.ano
    run.semestre = parse_result.semestre or run.semestre

    snapshot = service.save_variable_snapshot(
        run_id=run.id,
        file_id=reference_file.id,
        militar_id=reference_file.militar_id,
        variables_json=parse_result.to_variables(),
        warnings_json=parse_result.warnings,
        pending_json=parse_result.pending,
        confidence_json={
            "parser": "reference_folha_pdf_v1",
            "reprocess": True,
        },
    )
    service.add_validations(
        compiler_validations_from_parse(parse_result, file_id=reference_file.id)
        + [
            {
                "run_id": run.id,
                "file_id": reference_file.id,
                "level": "OK",
                "code": "OK_VARIABLES_EXTRACTED",
                "message": "Referencia PDF reprocessada e novo snapshot salvo.",
            },
            {
                "run_id": run.id,
                "file_id": reference_file.id,
                "level": "WARNING",
                "code": "WARN_TEMPO_TRANSCRITO_NAO_RECALCULADO",
                "message": (
                    "Tempos extraidos de PDF de memoria permanecem como historico "
                    "transcrito, nao como calculo homologado."
                ),
            },
        ]
    )
    service.finalize_run(run, has_pending=bool(parse_result.pending))
    return {
        "run": run_to_dict(run),
        "file": file_to_dict(reference_file),
        "snapshot": snapshot_to_dict(snapshot),
        "status": "REPROCESSED",
    }


def _reprocess_folha_odt(
    service: CompilerMemoryService,
    run,
    *,
    owner_user_id: str | None,
    db,
) -> dict:
    files_by_role = {item.role: item for item in service.list_files(run.id)}
    bi_file = files_by_role.get("INPUT_BI_ODT")
    sicapex_file = files_by_role.get("INPUT_SICAPEX_PDF")
    modelo_file = files_by_role.get("INPUT_MODELO_ODT")
    if not bi_file or not sicapex_file:
        raise bad_request(
            "REPROCESSAMENTO_INPUTS_INCOMPLETOS",
            "Run de Folha nao possui INPUT_BI_ODT e INPUT_SICAPEX_PDF salvos.",
        )
    if run.ano is None or not run.semestre:
        raise bad_request(
            "REPROCESSAMENTO_PERIODO_AUSENTE",
            "Run de Folha nao possui ano/semestre suficientes para reprocessamento.",
        )

    bi_path = service.download_file(bi_file.id)
    sicapex_path = service.download_file(sicapex_file.id)
    modelo_path = service.download_file(modelo_file.id) if modelo_file else None

    run.status = "GERANDO_ODT"
    sicapex_record = parse_sicapex_pdf(sicapex_path)
    existing_militar = SicapexImportService(db)._find_existing(sicapex_record)
    sicapex_context = (
        build_tempo_servico_context(existing_militar.id, db) if existing_militar else None
    )
    with PipelineWorkspaceManager() as workspace:
        output_odt = workspace.output_dir / "folha_alteracoes_compilada.odt"
        result = FolhaAlteracoesCompiler().compile(
            bi_odt_path=bi_path,
            sicapex_pdf_path=sicapex_path,
            template_odt_path=modelo_path,
            output_path=output_odt,
            options=CompilerOptions(
                ano=run.ano,
                semestre=run.semestre,
                reparar_tabelas=True,
                preservar_tabelas_odt=True,
            ),
            sicapex_context=sicapex_context,
        )
        run.militar_id = existing_militar.id if existing_militar else run.militar_id
        run.nome_militar_snapshot = result.profile.nome_completo
        run.identidade_snapshot = result.profile.identidade
        run.posto_grad_snapshot = result.profile.graduacao_abrev or result.profile.graduacao_extenso
        run.fonte_tempo = result.times.origem

        snapshot = service.save_variable_snapshot(
            run_id=run.id,
            militar_id=run.militar_id,
            variables_json={
                "nome_completo": result.profile.nome_completo,
                "nome_guerra": result.profile.nome_guerra,
                "graduacao": result.profile.graduacao_abrev,
                "graduacao_extenso": result.profile.graduacao_extenso,
                "qas_qms": result.profile.qm,
                "identidade": result.profile.identidade,
                "ano": run.ano,
                "semestre": run.semestre,
                "tempo_origem": result.times.origem,
                "tc": result.times.tc,
                "tnc": result.times.tnc,
                "ttes": result.times.ttes,
                "eventos": result.events_count,
                "tabelas": result.tables_count,
                "reprocess": True,
            },
            warnings_json=[],
            pending_json=result.validation,
            confidence_json={"source": "folha_alteracoes_compiler", "reprocess": True},
        )

        package_path = workspace.output_dir / f"{result.slug}_reprocessado_compilador_sisges.zip"
        with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            zout.write(result.output_path, result.output_path.name)
            zout.write(result.validation_path, result.validation_path.name)
            zout.write(result.justification_path, result.justification_path.name)

        service.register_output_file(
            run=run,
            source_path=result.output_path,
            role="OUTPUT_FOLHA_ODT",
            owner_user_id=owner_user_id,
            militar_id=run.militar_id,
            source_kind="folha_alteracoes_reprocess",
        )
        service.register_output_file(
            run=run,
            source_path=result.validation_path,
            role="OUTPUT_VALIDACAO_TXT",
            owner_user_id=owner_user_id,
            militar_id=run.militar_id,
            source_kind="validacao_reprocess",
        )
        service.register_output_file(
            run=run,
            source_path=result.justification_path,
            role="OUTPUT_JUSTIFICATIVA_TXT",
            owner_user_id=owner_user_id,
            militar_id=run.militar_id,
            source_kind="justificativa_reprocess",
        )

        final_path = Path("data/outputs") / package_path.name
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(package_path.read_bytes())
        output_sha256 = sha256_file(final_path)
        document = DocumentService(db).register_document(
            kind="FOLHA_ALTERACOES_ZIP",
            filename=final_path.name,
            status="generated",
            source_module="compilador.folha.reprocess",
            output_path=str(final_path).replace("\\", "/"),
            owner_user_id=owner_user_id,
            trace_id=run.trace_id,
            template_sha256=sha256_file(modelo_path) if modelo_path else None,
            template_version="uploaded" if modelo_path else "internal-v1",
            input_sha256=sha256_file(sicapex_path),
            output_sha256=output_sha256,
            metadata={
                "run_id": run.id,
                "reprocess": True,
                "ano": run.ano,
                "semestre": run.semestre,
                "militar": result.profile.nome_completo,
                "identidade": result.profile.identidade,
                "eventos": result.events_count,
                "tabelas": result.tables_count,
                "tempo_origem": result.times.origem,
                "ttes": result.times.ttes,
                "tc": result.times.tc,
                "tnc": result.times.tnc,
                "bi_odt_sha256": sha256_file(bi_path),
                "sicapex_pdf_sha256": sha256_file(sicapex_path),
                "output_sha256": output_sha256,
            },
        )
        zip_file = service.register_existing_document_file(
            run=run,
            source_path=final_path,
            role="OUTPUT_ZIP",
            document_id=document.id,
            militar_id=run.militar_id,
            original_filename=final_path.name,
            mime_type="application/zip",
            source_kind="folha_alteracoes_zip_reprocess",
        )
        service.add_validations(
            [
                {
                    "run_id": run.id,
                    "level": "OK",
                    "code": "OK_REPROCESSAMENTO_CONCLUIDO",
                    "message": "Run de Folha reprocessado a partir dos inputs persistidos.",
                },
                {
                    "run_id": run.id,
                    "level": "OK",
                    "code": "OK_DOCUMENT_REGISTERED",
                    "message": "ZIP reprocessado registrado no historico geral de documentos.",
                },
            ]
        )
        service.finalize_run(run, has_pending=any("PENDENTE" in item for item in result.validation))

    return {
        "run": run_to_dict(run),
        "file": file_to_dict(zip_file),
        "snapshot": snapshot_to_dict(snapshot),
        "status": "REPROCESSED",
    }


@router.get("/memory/references/{file_id}")
def get_reference(
    file_id: str,
    user=Depends(require_permission("compilador.memory.view")),
    db=Depends(get_db),
):
    service = CompilerMemoryService(db)
    file = service.get_file(file_id)
    if not file or not file.role.startswith("MEMORY_REFERENCE_"):
        raise HTTPException(status_code=404, detail="Referencia nao encontrada.")
    return reference_to_dict(service, file, include_validations=True)


@router.get("/memory/references/{file_id}/variables")
def get_reference_variables(
    file_id: str,
    user=Depends(require_permission("compilador.memory.view")),
    db=Depends(get_db),
):
    service = CompilerMemoryService(db)
    snapshot = service.latest_snapshot_for_file(file_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Variaveis nao encontradas.")
    return {
        "file_id": file_id,
        "schema_version": snapshot.schema_version,
        "variables": snapshot.variables_json,
        "warnings": snapshot.warnings_json or [],
        "pending": snapshot.pending_json or [],
        "confidence": snapshot.confidence_json or {},
    }


@router.get("/files/{file_id}/download")
def download_compiler_file(
    file_id: str,
    user=Depends(require_permission("compilador.memory.download")),
    db=Depends(get_db),
):
    service = CompilerMemoryService(db)
    file = service.get_file(file_id)
    if not file:
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado.")
    path = service.download_file(file_id)
    return FileResponse(path, filename=file.original_filename or file.filename, media_type=file.mime_type or "application/octet-stream")


def reference_to_dict(
    service: CompilerMemoryService,
    file,
    *,
    include_validations: bool = False,
) -> dict:
    snapshot = service.latest_snapshot_for_file(file.id)
    variables = snapshot.variables_json if snapshot else {}
    item = {
        "id": file.id,
        "file_id": file.id,
        "document_id": file.document_id,
        "role": file.role,
        "filename": file.filename,
        "original_filename": file.original_filename,
        "mime_type": file.mime_type,
        "sha256": file.sha256,
        "size_bytes": file.size_bytes,
        "page_count": file.page_count,
        "source_kind": file.source_kind,
        "created_at": file.created_at.isoformat() if file.created_at else None,
        "variables": variables,
        "warnings": snapshot.warnings_json if snapshot else [],
        "pending": snapshot.pending_json if snapshot else [],
    }
    if include_validations:
        item["validations"] = [
            {
                "id": validation.id,
                "level": validation.level,
                "code": validation.code,
                "message": validation.message,
                "field": validation.field,
                "payload": validation.payload_json,
                "created_at": validation.created_at.isoformat() if validation.created_at else None,
            }
            for validation in service.validations_for_file(file.id)
        ]
    return item


def run_to_dict(run) -> dict:
    return {
        "id": run.id,
        "trace_id": run.trace_id,
        "tipo_compilacao": run.tipo_compilacao,
        "status": run.status,
        "militar_id": run.militar_id,
        "nome_militar_snapshot": run.nome_militar_snapshot,
        "identidade_snapshot": mask_identity(run.identidade_snapshot),
        "posto_grad_snapshot": run.posto_grad_snapshot,
        "periodo_inicio": run.periodo_inicio.isoformat() if run.periodo_inicio else None,
        "periodo_fim": run.periodo_fim.isoformat() if run.periodo_fim else None,
        "ano": run.ano,
        "semestre": run.semestre,
        "fonte_tempo": run.fonte_tempo,
        "fonte_eventos": run.fonte_eventos,
        "error_message": run.error_message,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
    }


def file_to_dict(file) -> dict:
    return {
        "id": file.id,
        "run_id": file.run_id,
        "document_id": file.document_id,
        "militar_id": file.militar_id,
        "role": file.role,
        "filename": file.filename,
        "original_filename": file.original_filename,
        "mime_type": file.mime_type,
        "extension": file.extension,
        "sha256": file.sha256,
        "size_bytes": file.size_bytes,
        "page_count": file.page_count,
        "source_kind": file.source_kind,
        "created_at": file.created_at.isoformat() if file.created_at else None,
    }


def snapshot_to_dict(snapshot) -> dict:
    return {
        "id": snapshot.id,
        "run_id": snapshot.run_id,
        "file_id": snapshot.file_id,
        "militar_id": snapshot.militar_id,
        "schema_version": snapshot.schema_version,
        "variables": snapshot.variables_json,
        "warnings": snapshot.warnings_json or [],
        "pending": snapshot.pending_json or [],
        "confidence": snapshot.confidence_json or {},
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
    }


def validation_to_dict(validation) -> dict:
    return {
        "id": validation.id,
        "run_id": validation.run_id,
        "file_id": validation.file_id,
        "level": validation.level,
        "code": validation.code,
        "message": validation.message,
        "field": validation.field,
        "payload": validation.payload_json,
        "created_at": validation.created_at.isoformat() if validation.created_at else None,
    }


def mask_identity(value: str | None) -> str | None:
    if not value:
        return value
    digits = "".join(char for char in value if char.isdigit())
    if len(digits) < 4:
        return "***"
    return f"***{digits[-4:]}"
