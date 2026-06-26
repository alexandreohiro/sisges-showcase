from __future__ import annotations

import json

from fastapi import APIRouter, Body, Depends, File, Form, Request, UploadFile
from fastapi.templating import Jinja2Templates

from apps.web.config import TEMPLATES_DIR
from apps.web.dependencies.auth import require_permission
from apps.web.dependencies.container import container
from apps.web.errors import bad_request
from apps.web.routes.compilador_folha import compile_folha_odt_package
from infra.persistence.db import get_db
from infra.pipeline.uploads import (
    ODT_UPLOAD_POLICY,
    PDF_UPLOAD_POLICY,
    UploadValidationError,
    save_upload_to_path,
)
from infra.pipeline.workspace import PipelineWorkspaceManager
from modules.compilador.domain.entities import (
    CompilationRecord,
    HeaderData,
    Part1Entry,
    Part2Times,
    PendingField,
)
from modules.documents.application.services import DocumentService

router = APIRouter(prefix="/compilador", tags=["compilador"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _record_to_dict(record: CompilationRecord) -> dict:
    return {
        "header": {
            "nome_completo": record.header.nome_completo,
            "nome_guerra": record.header.nome_guerra,
            "graduacao": record.header.graduacao,
            "identidade": record.header.identidade,
            "qm": record.header.qm,
            "periodo": record.header.periodo,
            "data_de_praca": record.header.data_de_praca,
        },
        "part1": [
            {
                "mes": item.mes,
                "titulo": item.titulo,
                "referencia": item.referencia,
                "corpo": item.corpo,
            }
            for item in record.part1
        ],
        "part2": {
            "tc": record.part2.tc,
            "tc_arreg": record.part2.tc_arreg,
            "tc_nao_arreg": record.part2.tc_nao_arreg,
            "tc_transito": record.part2.tc_transito,
            "tc_instalacao": record.part2.tc_instalacao,
            "tnc": record.part2.tnc,
            "tscmm": record.part2.tscmm,
            "tssd": record.part2.tssd,
            "tsnr": record.part2.tsnr,
            "ttes": record.part2.ttes,
            "origem": record.part2.origem,
        },
        "pending_fields": [
            {
                "field_name": pending.field_name,
                "reason": pending.reason,
                "suggested_value": pending.suggested_value,
                "source": pending.source,
            }
            for pending in record.pending_fields
        ],
        "can_finalize": len(record.pending_fields) == 0,
        "diagnostics": record.diagnostics,
        "metadata": record.metadata,
        "raw_excerpt": (record.raw_text or "")[:1200],
    }


def _record_from_payload(data: dict) -> CompilationRecord:
    record = CompilationRecord()

    header = data.get("header", {})
    record.header = HeaderData(
        nome_completo=header.get("nome_completo", ""),
        nome_guerra=header.get("nome_guerra", ""),
        graduacao=header.get("graduacao", ""),
        identidade=header.get("identidade", ""),
        qm=header.get("qm", ""),
        periodo=header.get("periodo", ""),
        data_de_praca=header.get("data_de_praca", ""),
    )

    record.part1 = [
        Part1Entry(
            mes=item.get("mes", ""),
            titulo=item.get("titulo", ""),
            referencia=item.get("referencia", ""),
            corpo=item.get("corpo", ""),
        )
        for item in data.get("part1", [])
    ]

    part2 = data.get("part2", {})
    record.part2 = Part2Times(
        tc=part2.get("tc", ""),
        tc_arreg=part2.get("tc_arreg", ""),
        tc_nao_arreg=part2.get("tc_nao_arreg", ""),
        tc_transito=part2.get("tc_transito", ""),
        tc_instalacao=part2.get("tc_instalacao", ""),
        tnc=part2.get("tnc", ""),
        tscmm=part2.get("tscmm", ""),
        tssd=part2.get("tssd", ""),
        tsnr=part2.get("tsnr", ""),
        ttes=part2.get("ttes", ""),
        origem=part2.get("origem", ""),
    )

    record.pending_fields = [
        PendingField(
            field_name=item.get("field_name", ""),
            reason=item.get("reason", ""),
            suggested_value=item.get("suggested_value", ""),
            source=item.get("source", "pending"),
        )
        for item in data.get("pending_fields", [])
    ]

    record.diagnostics = data.get("diagnostics", [])
    record.metadata = data.get("metadata", {})
    return record


@router.get("")
def compilador_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="compilador.html",
        context={
            "request": request,
            "title": "SisGeS - Compilador",
        },
    )


@router.post("/test-compile")
def test_compile(
    payload: dict = Body(...),
    user=Depends(require_permission("compilador.run")),
):
    text = payload.get("text", "")
    record = container.compile_record_use_case.execute(text)
    return _record_to_dict(record)


@router.post("/compile-pdf")
async def compile_pdf(
    pdf: UploadFile = File(...),
    user=Depends(require_permission("compilador.run")),
):
    try:
        with PipelineWorkspaceManager() as workspace:
            pdf_path = workspace.input_dir / "entrada.pdf"
            await save_upload_to_path(pdf, pdf_path, PDF_UPLOAD_POLICY)
            result = container.compiler_document_pipeline.compile_pdf(
                pdf_path=pdf_path,
                workspace=workspace,
            )
    except UploadValidationError as exc:
        raise bad_request(exc.code, exc.message) from exc

    payload = _record_to_dict(result.record)
    payload["trace_id"] = result.trace_id
    payload["input_pdf_sha256"] = result.input_pdf.sha256
    payload["pipeline_steps"] = [step.__dict__ for step in result.steps]
    return payload


@router.post("/compile-folha-odt")
async def compile_folha_odt(
    bi_odt: UploadFile = File(...),
    sicapex_pdf: UploadFile = File(...),
    modelo_odt: UploadFile | None = File(default=None),
    ano: int = Form(2025),
    semestre: str = Form("2"),
    reparar_tabelas: bool = Form(True),
    preservar_tabelas_odt: bool = Form(True),
    user=Depends(require_permission("compilador.generate_odt")),
    db=Depends(get_db),
):
    """Compilador real de Folhas de Alterações.

    Entrada canônica:
    - ODT do BI/alterações;
    - PDF da Ficha Cadastro SiCaPEx;
    - modelo ODT opcional, preservado para compatibilidade da UI.

    Saída: pacote ZIP com ODT final, validação TXT e justificativa TXT.
    """
    return await compile_folha_odt_package(
        bi_odt=bi_odt,
        sicapex_pdf=sicapex_pdf,
        modelo_odt=modelo_odt,
        ano=ano,
        semestre=semestre,
        reparar_tabelas=reparar_tabelas,
        preservar_tabelas_odt=preservar_tabelas_odt,
        document_service=DocumentService(db),
        owner_user_id=user.get("id"),
        db=db,
    )


@router.post("/resolve-pending")
def resolve_pending(
    payload: dict = Body(...),
    user=Depends(require_permission("compilador.resolve_pending")),
):
    record_payload = payload.get("record", {})
    resolutions = payload.get("resolutions", {})

    record = _record_from_payload(record_payload)
    record = container.apply_pending_resolution_use_case.execute(record, resolutions)

    for field_name, payload_field in resolutions.items():
        save_to_gp = (payload_field or {}).get("save_to_gp", False)
        value = (payload_field or {}).get("value", "")

        if not save_to_gp or not value:
            continue

        identidade = record.header.identidade
        if not identidade:
            continue

        kwargs = {
            "identidade": identidade,
            "nome_completo": record.header.nome_completo,
            "graduacao": record.header.graduacao,
        }

        if field_name == "nome_guerra":
            kwargs["nome_guerra"] = value.strip()
        elif field_name == "qm":
            kwargs["qm"] = value.strip()
        elif field_name == "data_de_praca":
            kwargs["data_de_praca"] = value.strip()

        container.gestao_pessoal.upsert_por_identidade(**kwargs)

    rendered = _record_to_dict(record)
    return {
        "header": rendered["header"],
        "part1": rendered["part1"],
        "part2": rendered["part2"],
        "pending_fields": rendered["pending_fields"],
        "can_finalize": len(record.pending_fields) == 0,
        "diagnostics": record.diagnostics,
        "metadata": record.metadata,
    }


@router.post("/render-odt")
async def render_odt(
    pdf: UploadFile = File(...),
    template: UploadFile = File(...),
    user=Depends(require_permission("compilador.generate_odt")),
    db=Depends(get_db),
):
    try:
        with PipelineWorkspaceManager() as workspace:
            pdf_path = workspace.input_dir / "entrada.pdf"
            template_path = workspace.input_dir / "template.odt"
            await save_upload_to_path(pdf, pdf_path, PDF_UPLOAD_POLICY)
            await save_upload_to_path(template, template_path, ODT_UPLOAD_POLICY)
            result = container.compiler_document_pipeline.render_odt_from_pdf(
                pdf_path=pdf_path,
                template_path=template_path,
                template_filename=template.filename or "template.odt",
                workspace=workspace,
                document_service=DocumentService(db),
                owner_user_id=user.get("id"),
            )
    except UploadValidationError as exc:
        raise bad_request(exc.code, exc.message) from exc
    except ValueError as exc:
        return _render_failure(str(exc), can_finalize=False)
    except Exception as exc:
        return _render_failure(f"Falha no render ODT: {exc}", can_finalize=True)

    return _render_success(result)


@router.post("/render-odt-from-record")
async def render_odt_from_record(
    template: UploadFile = File(...),
    record_json: str = Form(...),
    user=Depends(require_permission("compilador.generate_odt")),
    db=Depends(get_db),
):
    try:
        data = json.loads(record_json)
    except json.JSONDecodeError as exc:
        raise bad_request("RECORD_JSON_INVALIDO", "record_json nao e JSON valido.") from exc

    record = _record_from_payload(data)

    if record.pending_fields:
        return {
            "success": False,
            "can_finalize": False,
            "message": "Existem pendencias canonicas. Resolva antes de gerar o ODT.",
            "pending_fields": [
                {
                    "field_name": pending.field_name,
                    "reason": pending.reason,
                    "suggested_value": pending.suggested_value,
                    "source": pending.source,
                }
                for pending in record.pending_fields
            ],
        }

    try:
        with PipelineWorkspaceManager() as workspace:
            template_path = workspace.input_dir / "template.odt"
            await save_upload_to_path(template, template_path, ODT_UPLOAD_POLICY)
            result = container.compiler_document_pipeline.render_odt_from_record(
                record=record,
                template_path=template_path,
                template_filename=template.filename or "template.odt",
                workspace=workspace,
                document_service=DocumentService(db),
                owner_user_id=user.get("id"),
            )
    except UploadValidationError as exc:
        raise bad_request(exc.code, exc.message) from exc
    except ValueError as exc:
        return _render_failure(f"Falha no render ODT: {exc}", can_finalize=True)
    except Exception as exc:
        return _render_failure(f"Falha no render ODT: {exc}", can_finalize=True)

    return _render_success(result)


def _render_success(result) -> dict:
    return {
        "success": True,
        "can_finalize": True,
        "message": "ODT gerado com sucesso.",
        "trace_id": result.trace_id,
        "output_file": str(result.output.path).replace("\\", "/"),
        "document_id": result.document_id,
        "download_url": result.download_url,
        "template_version": result.template.version,
        "template_sha256": result.template.sha256,
        "input_pdf_sha256": result.input_pdf.sha256 if result.input_pdf else None,
        "output_sha256": result.output.sha256,
        "pipeline_steps": [step.__dict__ for step in result.steps],
        "render_info": result.render_info,
    }


def _render_failure(message: str, *, can_finalize: bool) -> dict:
    return {
        "success": False,
        "can_finalize": can_finalize,
        "message": message,
    }
