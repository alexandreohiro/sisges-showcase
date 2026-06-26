from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from apps.web.dependencies.auth import require_permission
from apps.web.errors import bad_request
from infra.persistence.db import get_db
from infra.pipeline.uploads import (
    ODT_UPLOAD_POLICY,
    PDF_UPLOAD_POLICY,
    UploadPolicy,
    UploadValidationError,
    save_upload_to_path,
)
from infra.pipeline.workspace import PipelineWorkspaceManager
from modules.compilador.application.compiler_memory_service import CompilerMemoryService
from modules.compilador.application.declaracao_template_catalog import (
    resolve_declaracao_template_path,
)
from modules.compilador.application.documento_compiler import (
    DOCUMENTO_CTSM,
    OUTPUT_MODE_FULL,
    OUTPUT_MODE_ODT,
    DocumentoCompiler,
)
from modules.documents.application.services import DocumentService
from shared.utils.hashing import sha256_file


router = APIRouter(prefix="/compilador/documentos", tags=["compilador"])


@router.post("/compile")
async def compile_documento(
    tipo_documento: str = Form(...),
    militar_id: int = Form(...),
    calculo_id: int | None = Form(default=None),
    output_mode: str = Form(OUTPUT_MODE_FULL),
    template_mode: str | None = Form(default=None),
    instituicao_ensino: str | None = Form(default=None),
    data_servico: str | None = Form(default=None),
    data_extenso: str | None = Form(default=None),
    ato_servico: str | None = Form(default=None),
    situacao_ausencia: str | None = Form(default=None),
    referencia_aluno: str | None = Form(default=None),
    assinatura_nome: str | None = Form(default=None),
    assinatura_funcao: str | None = Form(default=None),
    template_key: str | None = Form(default=None),
    template_odt: UploadFile | None = File(default=None),
    reference_pdf: UploadFile | None = File(default=None),
    user=Depends(require_permission("compilador.generate_odt")),
    db=Depends(get_db),
):
    owner_user_id = user.get("id") or user.get("user_id")
    with PipelineWorkspaceManager() as workspace:
        template_path = await _save_upload(workspace.input_dir, template_odt, ODT_UPLOAD_POLICY)
        template_source_filename = template_odt.filename if template_odt else None
        template_source_kind = None
        if template_path is None and template_key:
            template_path = resolve_declaracao_template_path(template_key)
            if template_path is None:
                raise bad_request(
                    "ERR_DECLARACAO_TEMPLATE_NOT_FOUND",
                    "Modelo de declaração não encontrado no catálogo configurado.",
                )
            template_source_filename = template_path.name
            template_source_kind = "DECLARACAO_TEMPLATE_CATALOG"
        reference_path = await _save_upload(workspace.input_dir, reference_pdf, PDF_UPLOAD_POLICY)
        try:
            result = DocumentoCompiler(db).compile(
                document_type=tipo_documento,
                militar_id=militar_id,
                calculo_id=calculo_id,
                output_dir=workspace.output_dir,
                template_path=template_path,
                output_mode=output_mode,
                owner_user_id=owner_user_id,
                template_mode=template_mode,
                declaracao_context={
                    "instituicao_ensino": instituicao_ensino,
                    "data_servico": data_servico,
                    "data_extenso": data_extenso,
                    "ato_servico": ato_servico,
                    "situacao_ausencia": situacao_ausencia,
                    "referencia_aluno": referencia_aluno,
                    "assinatura_nome": assinatura_nome,
                    "assinatura_funcao": assinatura_funcao,
                },
            )
        except ValueError as exc:
            raise bad_request(str(exc), str(exc)) from exc

        final_source = result.package_path if result.package_path else result.output_odt_path
        final_path = Path("data/outputs") / final_source.name
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(final_source.read_bytes())

        document = DocumentService(db).register_document(
            kind=result.document_type,
            filename=final_path.name,
            status="generated",
            source_module="compilador.documentos",
            output_path=str(final_path).replace("\\", "/"),
            owner_user_id=owner_user_id,
            template_sha256=result.template_sha256,
            output_sha256=sha256_file(final_path),
            metadata={
                "tipo_documento": result.document_type,
                "militar_id": militar_id,
                "package_mode": OUTPUT_MODE_ODT if result.package_path is None else OUTPUT_MODE_FULL,
                "template_source": result.template_source,
                "template_key": template_key,
                "errors": result.errors,
                "warnings": result.warnings,
            },
        )

        memory = CompilerMemoryService(db)
        run = memory.create_run(
            tipo_compilacao=f"DOCUMENTO_{result.document_type}",
            created_by_user_id=owner_user_id,
            militar_id=militar_id,
            nome_militar_snapshot=result.variables.get("militar", {}).get("nome_completo"),
            identidade_snapshot=result.variables.get("militar", {}).get("identidade"),
            posto_grad_snapshot=result.variables.get("militar", {}).get("posto_graduacao"),
            fonte_tempo="CALCULO_TEMPO_APROVADO" if result.document_type == DOCUMENTO_CTSM else None,
            fonte_eventos="GESTAO_PESSOAL_DB",
        )
        if template_path:
            memory.register_input_file(
                run=run,
                source_path=template_path,
                role="INPUT_DOCUMENT_TEMPLATE_ODT",
                original_filename=template_source_filename,
                mime_type=template_odt.content_type if template_odt else None,
                owner_user_id=owner_user_id,
                militar_id=militar_id,
                source_kind=template_source_kind or result.template_source,
            )
        if reference_path:
            memory.register_input_file(
                run=run,
                source_path=reference_path,
                role="VISUAL_REFERENCE_PDF",
                original_filename=reference_pdf.filename if reference_pdf else None,
                mime_type=reference_pdf.content_type if reference_pdf else None,
                owner_user_id=owner_user_id,
                militar_id=militar_id,
                source_kind="visual_reference",
            )
        for path, role in (
            (result.output_odt_path, "OUTPUT_DOCUMENT_ODT"),
            (result.validation_path, "OUTPUT_VALIDACAO_TXT"),
            (result.justification_path, "OUTPUT_JUSTIFICATIVA_TXT"),
            (result.variables_path, "VARIABLES_JSON"),
            (result.compiler_run_path, "COMPILER_RUN_JSON"),
            (result.manifest_path, "MANIFEST_JSON"),
        ):
            memory.register_output_file(
                run=run,
                source_path=path,
                role=role,
                owner_user_id=owner_user_id,
                militar_id=militar_id,
                source_kind=result.document_type,
            )
        memory.register_existing_document_file(
            run=run,
            source_path=final_path,
            role="OUTPUT_DOCUMENT_PACKAGE" if result.package_path else "OUTPUT_DOCUMENT_ODT",
            document_id=document.id,
            militar_id=militar_id,
            original_filename=final_path.name,
            mime_type="application/zip" if result.package_path else "application/vnd.oasis.opendocument.text",
            source_kind=result.document_type,
        )
        memory.save_variable_snapshot(
            variables_json=result.variables,
            run_id=run.id,
            militar_id=militar_id,
            schema_version="documento-compilador-v1",
            warnings_json=result.warnings,
            pending_json=result.errors,
        )
        memory.add_validations(
            [
                {
                    "run_id": run.id,
                    "level": "ERROR" if code.startswith("ERR_") else ("WARNING" if code.startswith("WARN_") else "OK"),
                    "code": code,
                    "message": code,
                }
                for code in [*result.validations, *result.warnings, *result.errors]
            ],
        )
        memory.finalize_run(run, has_pending=bool(result.warnings or result.errors))
        db.commit()

        return FileResponse(
            final_path,
            filename=final_path.name,
            media_type="application/zip" if result.package_path else "application/vnd.oasis.opendocument.text",
            headers={
                "X-Sisges-Document-Id": document.id,
                "X-Sisges-Compiler-Run-Id": run.id,
                "X-Sisges-Package-Mode": OUTPUT_MODE_FULL if result.package_path else OUTPUT_MODE_ODT,
            },
        )


async def _save_upload(
    input_dir: Path,
    upload: UploadFile | None,
    policy: UploadPolicy,
) -> Path | None:
    if upload is None or not upload.filename:
        return None
    target = input_dir / Path(upload.filename).name
    try:
        await save_upload_to_path(upload, target, policy)
    except UploadValidationError as exc:
        raise bad_request(exc.code, exc.message) from exc
    return target
