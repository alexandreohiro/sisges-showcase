"""Servico de empacotamento e pipeline de compilacao de Folhas de Alteracoes.

Contem helpers de payload, construcao de ZIP, validacoes de role e a funcao
principal de pipeline que orquestra o compilador, registra arquivos na memoria
do compilador e produz o pacote de saida (ODT parte-1 ou ZIP completo).
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException

from apps.web.errors import bad_request
from infra.pipeline.uploads import UploadValidationError
from modules.calculo_tempo_servico.application.sicapex_context import build_tempo_servico_context
from modules.compilador.application.compiler_memory_service import CompilerMemoryService
from modules.compilador.application.folha_alteracoes_compiler import (
    CompilerOptions,
    FolhaAlteracoesCompiler,
    period_bounds,
)
from modules.documents.application.services import DocumentService
from modules.gestao_pessoal.importadores.sicapex.parser import parse_sicapex_pdf
from modules.gestao_pessoal.importadores.sicapex.service import SicapexImportService
from shared.utils.hashing import sha256_file

# ---------------------------------------------------------------------------
# Role constants
# ---------------------------------------------------------------------------

INPUT_BI_PDF = "INPUT_BI_PDF"
INPUT_BI_ODT = "INPUT_BI_ODT"
INPUT_SICAPEX_PDF = "INPUT_SICAPEX_PDF"
INPUT_MODELO_ODT = "INPUT_MODELO_ODT"
STORED_EXECUTABLE_MODELO_ODT = "STORED_EXECUTABLE_MODELO_ODT"
MEMORY_REFERENCE_FOLHA_PDF = "MEMORY_REFERENCE_FOLHA_PDF"
MEMORY_REFERENCE_FOLHA_ODT = "MEMORY_REFERENCE_FOLHA_ODT"
MEMORY_REFERENCE_BI_PDF = "MEMORY_REFERENCE_BI_PDF"
MEMORY_REFERENCE_BI_ODT = "MEMORY_REFERENCE_BI_ODT"
INTERNAL_DEFAULT_MODELO_ODT = "INTERNAL_DEFAULT_MODELO_ODT"
VISUAL_REFERENCE_ONLY_MODELO_ODT = "VISUAL_REFERENCE_ONLY"

ALTERACOES_PDF_ROLES = {INPUT_BI_PDF, MEMORY_REFERENCE_BI_PDF, MEMORY_REFERENCE_FOLHA_PDF}
ALTERACOES_ODT_ROLES = {INPUT_BI_ODT, MEMORY_REFERENCE_BI_ODT, MEMORY_REFERENCE_FOLHA_ODT}
ALTERACOES_ROLES = ALTERACOES_PDF_ROLES | ALTERACOES_ODT_ROLES
MODELO_ROLES = {
    INPUT_MODELO_ODT,
    STORED_EXECUTABLE_MODELO_ODT,
    INTERNAL_DEFAULT_MODELO_ODT,
    MEMORY_REFERENCE_FOLHA_ODT,
    VISUAL_REFERENCE_ONLY_MODELO_ODT,
}
SICAPEX_ROLES = {INPUT_SICAPEX_PDF}

FULL_PACKAGE_FILES = {
    "folha_alteracoes.odt",
    "parte_1_alteracoes.odt",
    "validacao.txt",
    "justificativa.txt",
    "variables.json",
    "compiler_run.json",
    "manifest.json",
}

OUTPUT_MODE_FULL = "full"
OUTPUT_MODE_PARTE1 = "parte1"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class PackageResult:
    final_path: Path
    filename: str
    document_id: str
    run_id: str
    package_mode: str
    media_type: str


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _contains_pending(validation: list[str]) -> bool:
    return any(
        "PENDENTE" in item or item.startswith(("WARN_", "ERR_"))
        for item in validation
    )


def _validation_code(line: str) -> str:
    return line.split(":", 1)[0].strip().split(" ", 1)[0].strip()


def _json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _alteracoes_role_for_upload(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return INPUT_BI_PDF
    if suffix == ".odt":
        return INPUT_BI_ODT
    raise bad_request("ERR_INPUT_ROLE_INVALID", "Fonte de alteracoes deve ser PDF ou ODT.")


def _normalize_output_mode(value: str | None) -> str:
    normalized = (value or OUTPUT_MODE_FULL).strip().lower()
    if normalized in {"parte1", "parte_1", "primeira_parte", "part1"}:
        return OUTPUT_MODE_PARTE1
    return OUTPUT_MODE_FULL


def _context_requires_sicapex_pdf(context: dict | None) -> bool:
    if not context:
        return True
    return bool(context.get("requires_sicapex_pdf", context.get("status") != "SICAPEX_COMPLETO"))


def _tempo_context_or_none(militar_id: int | None, db) -> dict | None:
    if militar_id is None:
        return None
    try:
        return build_tempo_servico_context(militar_id, db)
    except ValueError:
        return {
            "militar_id": militar_id,
            "status": "SEM_SICAPEX",
            "has_sicapex": False,
            "has_data_praca": False,
            "has_tempo_context": False,
            "source": "GESTAO_PESSOAL_DB",
            "requires_sicapex_pdf": True,
            "warnings": ["MILITAR_NAO_ENCONTRADO"],
        }


def _validation_for_alteracoes_role(role: str) -> dict:
    if role in ALTERACOES_PDF_ROLES:
        return {
            "level": "OK",
            "code": "OK_INPUT_BI_PDF_REGISTERED",
            "message": "Fonte de alteracoes PDF registrada com role correta.",
        }
    if role in ALTERACOES_ODT_ROLES:
        return {
            "level": "OK",
            "code": "OK_INPUT_BI_ODT_REGISTERED",
            "message": "Fonte de alteracoes ODT registrada com role correta.",
        }
    return {
        "level": "ERROR",
        "code": "ERR_INPUT_ROLE_INVALID",
        "message": f"Role de fonte de alteracoes invalida: {role}.",
    }


def _validation_for_modelo_role(role: str) -> dict:
    if role == INPUT_MODELO_ODT:
        return {
            "level": "OK",
            "code": "OK_UPLOADED_TEMPLATE_USED",
            "message": "Modelo ODT executavel enviado pelo operador usado na renderizacao.",
        }
    if role == STORED_EXECUTABLE_MODELO_ODT:
        return {
            "level": "OK",
            "code": "OK_STORED_EXECUTABLE_TEMPLATE_USED",
            "message": "Modelo ODT executavel salvo no SISGES usado na renderizacao.",
        }
    if role == INTERNAL_DEFAULT_MODELO_ODT:
        return {
            "level": "OK",
            "code": "OK_DEFAULT_TEMPLATE_USED",
            "message": "Modelo ODT padrao interno usado na renderizacao.",
        }
    if role == VISUAL_REFERENCE_ONLY_MODELO_ODT:
        return {
            "level": "WARNING",
            "code": "WARN_TEMPLATE_VISUAL_REFERENCE_ONLY",
            "message": "ODT enviado sem marcadores SISGES tratado como referencia visual; renderizacao usou modelo interno.",
        }
    return {
        "level": "ERROR",
        "code": "ERR_TEMPLATE_NOT_EXECUTABLE",
        "message": f"Role de modelo ODT invalida: {role}.",
    }


def _run_to_payload(run) -> dict:
    return {
        "run_id": run.id,
        "trace_id": run.trace_id,
        "status": run.status,
        "tipo_compilacao": run.tipo_compilacao,
        "militar_id": run.militar_id,
        "nome_militar_snapshot": run.nome_militar_snapshot,
        "identidade_snapshot": run.identidade_snapshot,
        "posto_grad_snapshot": run.posto_grad_snapshot,
        "ano": run.ano,
        "semestre": run.semestre,
        "periodo_inicio": run.periodo_inicio.isoformat() if run.periodo_inicio else None,
        "periodo_fim": run.periodo_fim.isoformat() if run.periodo_fim else None,
        "fonte_tempo": run.fonte_tempo,
        "fonte_eventos": run.fonte_eventos,
        "error_message": run.error_message,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
    }


def _file_to_manifest_item(role: str, path: Path) -> dict:
    return {
        "role": role,
        "filename": path.name,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _build_variables_payload(
    *,
    result,
    run,
    ano: int,
    semestre: str,
    period_start,
    period_end,
    modelo_path: Path | None,
    modelo_role: str = INPUT_MODELO_ODT,
    template_source: str = "UPLOADED_MODEL",
    modelo_user_provided: bool = True,
    sicapex_context: dict | None = None,
    memory_reference_file=None,
    memory_reference_snapshot=None,
    source_memory_file_ids: dict | None = None,
) -> dict:
    template_sha = sha256_file(modelo_path) if modelo_path else None
    template_used = "OK_TEMPLATE_USED" in result.validation
    template_warnings = [
        item
        for item in result.validation
        if item
        in {
            "WARN_TEMPLATE_VISUAL_REFERENCE_ONLY",
            "ERR_TEMPLATE_NOT_EXECUTABLE",
            "ERR_TEMPLATE_HEADER_MARKERS_UNSUPPORTED",
            "ERR_TEMPLATE_PLACEHOLDER_LEFTOVER",
            "ERR_TEMPLATE_ODT_INVALID",
        }
        or item.startswith("ERR_TEMPLATE_PLACEHOLDER_LEFTOVER:")
    ]
    tempo_pendencias = [
        item for item in result.validation if "PENDENTE" in item or item.startswith("WARN_TEMPO")
    ]
    memory_reference_payload = (
        {
            "file_id": memory_reference_file.id,
            "filename": memory_reference_file.original_filename or memory_reference_file.filename,
            "sha256": memory_reference_file.sha256,
            "schema_version": (
                memory_reference_snapshot.schema_version if memory_reference_snapshot else None
            ),
        }
        if memory_reference_file
        else None
    )
    return {
        "schema_version": "compilador-folha-full-package.v1",
        "nome_completo": result.profile.nome_completo,
        "nome_guerra": result.profile.nome_guerra,
        "graduacao": result.profile.graduacao_abrev,
        "graduacao_extenso": result.profile.graduacao_extenso,
        "qas_qms": result.profile.qm,
        "identidade": result.profile.identidade,
        "ano": ano,
        "semestre": semestre,
        "periodo_inicio": period_start.isoformat(),
        "periodo_fim": period_end.isoformat(),
        "tempo_origem": result.times.origem,
        "tc": result.times.tc,
        "tnc": result.times.tnc,
        "ttes": result.times.ttes,
        "eventos": result.events_count,
        "tabelas": result.tables_count,
        "memory_reference": memory_reference_payload,
        "militar": {
            "id": run.militar_id,
            "nome_completo": result.profile.nome_completo,
            "nome_guerra": result.profile.nome_guerra,
            "posto_graduacao": result.profile.graduacao_abrev or result.profile.graduacao_extenso,
            "graduacao_extenso": result.profile.graduacao_extenso,
            "qas_qms": result.profile.qm,
            "identidade": result.profile.identidade,
        },
        "periodo": {
            "ano": ano,
            "semestre": semestre,
            "periodo_inicio": period_start.isoformat(),
            "periodo_fim": period_end.isoformat(),
        },
        "reference_file": memory_reference_payload,
        "source_memory_file_ids": source_memory_file_ids or {},
        "eventos_por_mes": {},
        "tempo": {
            "tc": result.times.tc,
            "tnc": result.times.tnc,
            "tscmm": result.times.tscmm,
            "tssd": result.times.tssd,
            "tsnr": result.times.tsnr,
            "ttes": result.times.ttes,
            "origem": result.times.origem,
            "status_calculo": (
                "PENDENTE_VALIDACAO_HUMANA" if tempo_pendencias else "CALCULADO"
            ),
            "pendencias": tempo_pendencias,
        },
        "tempo_contexto": sicapex_context or {},
        "source_variables": {
            "tempo_origem": result.times.origem,
            "eventos": result.events_count,
            "tabelas": result.tables_count,
        },
        "outputs": {
            "folha_alteracoes_odt": {
                "filename": result.output_path.name,
                "sha256": sha256_file(result.output_path),
            },
            "parte_1_alteracoes_odt": (
                {
                    "filename": result.parte1_output_path.name,
                    "sha256": sha256_file(result.parte1_output_path),
                }
                if result.parte1_output_path and result.parte1_output_path.exists()
                else None
            ),
        },
        "template": {
            "provided": modelo_user_provided,
            "provided_by_user": modelo_user_provided,
            "used": template_used,
            "sha256": template_sha,
            "source": template_source,
            "role": modelo_role,
            "strategy": "template" if template_used else "internal_fallback",
            "warnings": template_warnings,
        },
        "validations": result.validation,
    }


def _manifest_payload(
    *,
    run,
    document_id: str | None,
    result,
    variables_payload: dict,
    files: list[dict],
    validations: list[str],
    package_mode: str,
    warnings: list[str],
) -> dict:
    militar = variables_payload.get("militar", {})
    periodo = variables_payload.get("periodo", {})
    return {
        "run_id": run.id,
        "document_id": document_id,
        "package_mode": package_mode,
        "militar": {
            "id": militar.get("id"),
            "nome_completo": militar.get("nome_completo"),
            "identidade": militar.get("identidade"),
        },
        "periodo": {
            "ano": periodo.get("ano"),
            "semestre": periodo.get("semestre"),
        },
        "template": variables_payload.get("template", {}),
        "source_memory_file_ids": variables_payload.get("source_memory_file_ids", {}),
        "files": files,
        "validations": validations,
        "warnings": warnings,
        "generated_at": _now_iso(),
    }


def _build_zip(
    *,
    package_path: Path,
    entries: list[tuple[Path, str]],
) -> None:
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        seen: set[str] = set()
        for source, arcname in entries:
            if arcname in seen:
                continue
            seen.add(arcname)
            zout.write(source, arcname)


def _validate_memory_file(
    memory_service: CompilerMemoryService,
    file_id: str,
    *,
    field_name: str,
    allowed_roles: set[str],
    allowed_suffixes: set[str],
):
    file = memory_service.get_file(file_id)
    if not file:
        raise bad_request(
            "MEMORY_FILE_NOT_FOUND",
            f"Arquivo informado em {field_name} nao foi encontrado na Memoria do Compilador.",
        )
    suffix = (file.extension or Path(file.filename).suffix).lower()
    if file.role not in allowed_roles or suffix not in allowed_suffixes:
        raise bad_request(
            "MEMORY_FILE_ROLE_INVALID",
            f"Arquivo informado em {field_name} possui role incompativel: {file.role}.",
        )
    path = Path(file.storage_path)
    if not path.exists():
        raise bad_request(
            "MEMORY_FILE_PHYSICAL_NOT_FOUND",
            f"Arquivo fisico informado em {field_name} nao existe mais na memoria.",
        )
    return file, path


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def compile_folha_pipeline(
    *,
    bi_path: Path,
    bi_role: str,
    sicapex_path: Path | None,
    modelo_path: Path,
    modelo_role: str,
    template_source: str,
    modelo_user_provided: bool,
    ano: int,
    semestre: str,
    reparar_tabelas: bool,
    preservar_tabelas_odt: bool,
    gerar_pdf_preview: bool,
    full_package: bool,
    output_mode: str = OUTPUT_MODE_FULL,
    assinatura_mode: str = "auto",
    assinatura_nome: str | None = None,
    assinatura_funcao: str | None = None,
    memory_reference_file_id: str | None = None,
    fonte_eventos: str | None = None,
    source_memory_file_ids: dict | None = None,
    output_dir: Path,
    trace_id: str,
    document_service: DocumentService,
    owner_user_id: str | None,
    db,
    militar_id: int | None = None,
    bi_original_filename: str | None = None,
    sicapex_original_filename: str | None = None,
    modelo_original_filename: str | None = None,
    bi_mime_type: str | None = None,
    sicapex_mime_type: str | None = None,
    modelo_mime_type: str | None = None,
) -> PackageResult:
    """Compila Folha de Alteracoes e registra o ZIP no historico documental."""
    memory_service = CompilerMemoryService(db)
    output_mode = _normalize_output_mode(output_mode)
    period_start, period_end, _period_label = period_bounds(ano, semestre)
    run = memory_service.create_run(
        tipo_compilacao="FOLHA_ALTERACOES_ODT",
        created_by_user_id=owner_user_id,
        periodo_inicio=period_start,
        periodo_fim=period_end,
        ano=ano,
        semestre=semestre,
        fonte_tempo="SICAPEX_PDF_OU_BANCO",
        fonte_eventos=fonte_eventos or bi_role,
    )
    try:
        memory_reference_file = None
        memory_reference_snapshot = None
        if memory_reference_file_id:
            memory_reference_file = memory_service.get_file(memory_reference_file_id)
            if not memory_reference_file or memory_reference_file.role not in ALTERACOES_ROLES:
                raise bad_request(
                    "MEMORY_REFERENCE_INVALIDA",
                    "Referencia da Memoria do Compilador nao encontrada ou invalida.",
                )
            memory_reference_snapshot = memory_service.latest_snapshot_for_file(memory_reference_file.id)
            run.fonte_eventos = fonte_eventos or memory_reference_file.role

        bi_file = memory_service.register_input_file(
            run=run,
            source_path=bi_path,
            role=bi_role,
            original_filename=bi_original_filename,
            mime_type=bi_mime_type,
            owner_user_id=owner_user_id,
            source_kind="folha_alteracoes",
        )
        sicapex_file = None
        if sicapex_path:
            sicapex_file = memory_service.register_input_file(
                run=run,
                source_path=sicapex_path,
                role=INPUT_SICAPEX_PDF,
                original_filename=sicapex_original_filename,
                mime_type=sicapex_mime_type,
                owner_user_id=owner_user_id,
                source_kind="sicapex",
            )
        memory_service.register_input_file(
            run=run,
            source_path=modelo_path,
            role=modelo_role,
            original_filename=modelo_original_filename or modelo_path.name,
            mime_type=modelo_mime_type or "application/vnd.oasis.opendocument.text",
            owner_user_id=owner_user_id,
            source_kind="modelo_odt",
        )
        sicapex_context = _tempo_context_or_none(militar_id, db)
        existing_militar = None
        if sicapex_path:
            sicapex_record = parse_sicapex_pdf(sicapex_path)
            existing_militar = SicapexImportService(db)._find_existing(sicapex_record)
            if existing_militar:
                sicapex_context = build_tempo_servico_context(existing_militar.id, db)
        elif _context_requires_sicapex_pdf(sicapex_context):
            raise bad_request(
                "ERR_SICAPEX_REQUIRED_FOR_UNREGISTERED_OR_INCOMPLETE_MILITAR",
                "Ficha SiCaPEx PDF e obrigatoria quando o militar nao possui contexto completo no banco.",
            )

        options = CompilerOptions(
            ano=ano,
            semestre=semestre,
            reparar_tabelas=reparar_tabelas,
            preservar_tabelas_odt=preservar_tabelas_odt,
            assinatura_mode=assinatura_mode,
            assinatura_nome=assinatura_nome or None,
            assinatura_funcao=assinatura_funcao or None,
        )
        output_odt = output_dir / "folha_alteracoes_compilada.odt"
        result = FolhaAlteracoesCompiler().compile(
            bi_odt_path=bi_path,
            sicapex_pdf_path=sicapex_path,
            template_odt_path=modelo_path,
            output_path=output_odt,
            options=options,
            sicapex_context=sicapex_context,
        )
        route_validations = [
            _validation_for_alteracoes_role(bi_role)["code"],
            _validation_for_modelo_role(modelo_role)["code"],
        ]
        if memory_reference_file:
            route_validations.append("OK_MEMORY_REFERENCE_USED")
        if sicapex_file:
            route_validations.append("OK_INPUT_SICAPEX_PDF_REGISTERED")
        result.validation = list(dict.fromkeys([*result.validation, *route_validations]))
        result.validation_path.write_text("\n".join(result.validation) + "\n", encoding="utf-8")
        run.militar_id = existing_militar.id if existing_militar else militar_id
        run.nome_militar_snapshot = result.profile.nome_completo
        run.identidade_snapshot = result.profile.identidade
        run.posto_grad_snapshot = result.profile.graduacao_abrev or result.profile.graduacao_extenso
        run.fonte_tempo = result.times.origem
        if memory_reference_file:
            run.fonte_eventos = fonte_eventos or "BI_ODT_PLUS_MEMORY_VALIDATION"

        variables_payload = _build_variables_payload(
            result=result,
            run=run,
            ano=ano,
            semestre=semestre,
            period_start=period_start,
            period_end=period_end,
            modelo_path=modelo_path,
            modelo_role=modelo_role,
            template_source=template_source,
            modelo_user_provided=modelo_user_provided,
            sicapex_context=sicapex_context,
            memory_reference_file=memory_reference_file,
            memory_reference_snapshot=memory_reference_snapshot,
            source_memory_file_ids=source_memory_file_ids,
        )
        memory_service.save_variable_snapshot(
            run_id=run.id,
            militar_id=run.militar_id,
            variables_json=variables_payload,
            warnings_json=[],
            pending_json=result.validation,
            confidence_json={"source": "folha_alteracoes_compiler"},
        )

        memory_service.register_output_file(
            run=run,
            source_path=result.output_path,
            role="OUTPUT_FOLHA_ODT",
            owner_user_id=owner_user_id,
            militar_id=run.militar_id,
            source_kind="folha_alteracoes",
        )
        if result.parte1_output_path and result.parte1_output_path.exists():
            memory_service.register_output_file(
                run=run,
                source_path=result.parte1_output_path,
                role="OUTPUT_PARTE1_ODT",
                owner_user_id=owner_user_id,
                militar_id=run.militar_id,
                source_kind="folha_alteracoes_parte1",
            )
        memory_service.register_output_file(
            run=run,
            source_path=result.validation_path,
            role="OUTPUT_VALIDACAO_TXT",
            owner_user_id=owner_user_id,
            militar_id=run.militar_id,
            source_kind="validacao",
        )
        memory_service.register_output_file(
            run=run,
            source_path=result.justification_path,
            role="OUTPUT_JUSTIFICATIVA_TXT",
            owner_user_id=owner_user_id,
            militar_id=run.militar_id,
            source_kind="justificativa",
        )

        package_mode = "full" if full_package else "minimal"
        package_warnings: list[str] = []
        if gerar_pdf_preview:
            package_warnings.append("WARN_PDF_PREVIEW_NOT_GENERATED")

        memory_service.add_validations(
            [
                {
                    "run_id": run.id,
                    "file_id": bi_file.id,
                    **_validation_for_alteracoes_role(bi_role),
                },
                {
                    "run_id": run.id,
                    **_validation_for_modelo_role(modelo_role),
                },
                *(
                    [
                        {
                            "run_id": run.id,
                            "file_id": sicapex_file.id,
                            "level": "OK",
                            "code": "OK_INPUT_SICAPEX_PDF_REGISTERED",
                            "message": "Ficha SiCaPEx PDF registrada como entrada complementar.",
                        }
                    ]
                    if sicapex_file
                    else []
                ),
                *(
                    [
                        {
                            "run_id": run.id,
                            "level": "OK",
                            "code": "OK_MEMORY_REFERENCE_USED",
                            "message": "Fonte de alteracoes usada a partir da Memoria do Compilador.",
                        }
                    ]
                    if memory_reference_file
                    else []
                ),
                {
                    "run_id": run.id,
                    "level": "OK",
                    "code": "OK_VARIABLES_EXTRACTED",
                    "message": "Snapshot de variaveis da compilacao salvo.",
                },
                {
                    "run_id": run.id,
                    "level": "OK",
                    "code": "OK_FULL_PACKAGE_GENERATED" if full_package else "OK_MINIMAL_PACKAGE_GENERATED",
                    "message": (
                        "Pacote completo do Compilador gerado."
                        if full_package
                        else "Pacote minimo do Compilador gerado por compatibilidade."
                    ),
                },
                *(
                    [
                        {
                            "run_id": run.id,
                            "level": "WARNING",
                            "code": "WARN_PDF_PREVIEW_NOT_GENERATED",
                            "message": "Preview PDF nao foi gerado neste ambiente.",
                        }
                    ]
                    if gerar_pdf_preview
                    else []
                ),
                *(
                    [
                        {
                            "run_id": run.id,
                            "file_id": memory_reference_file.id,
                            "level": "INFO",
                            "code": "OK_MEMORY_REFERENCE_LINKED",
                            "message": (
                                "PDF de Folha salvo na Memoria do Compilador "
                                "vinculado para validacao cruzada."
                            ),
                        }
                    ]
                    if memory_reference_file
                    else []
                ),
            ]
        )
        memory_service.finalize_run(run, has_pending=_contains_pending(result.validation + package_warnings))

        variables_path = output_dir / "variables.json"
        compiler_run_path = output_dir / "compiler_run.json"
        manifest_path = output_dir / "manifest.json"
        _write_json(variables_path, variables_payload)
        _write_json(compiler_run_path, _run_to_payload(run))

        manifest_files = [
            _file_to_manifest_item("OUTPUT_FOLHA_ODT", result.output_path),
            *(
                [_file_to_manifest_item("OUTPUT_PARTE1_ODT", result.parte1_output_path)]
                if result.parte1_output_path and result.parte1_output_path.exists()
                else []
            ),
            _file_to_manifest_item("OUTPUT_VALIDACAO_TXT", result.validation_path),
            _file_to_manifest_item("OUTPUT_JUSTIFICATIVA_TXT", result.justification_path),
            _file_to_manifest_item("VARIABLES_JSON", variables_path),
            _file_to_manifest_item("COMPILER_RUN_JSON", compiler_run_path),
        ]
        validations = list(dict.fromkeys([_validation_code(item) for item in result.validation] + package_warnings))

        if output_mode == OUTPUT_MODE_PARTE1:
            if not result.parte1_output_path or not result.parte1_output_path.exists():
                raise bad_request("ERR_PARTE1_ODT_NOT_GENERATED", "ODT da 1a Parte nao foi gerado.")

            final_path = Path("data/outputs") / f"{result.slug}_parte_1_alteracoes.odt"
            final_path.parent.mkdir(parents=True, exist_ok=True)
            document = document_service.register_document(
                kind="FOLHA_ALTERACOES_PARTE1_ODT",
                filename=final_path.name,
                status="generated",
                source_module="compilador.folha",
                output_path=str(final_path).replace("\\", "/"),
                owner_user_id=owner_user_id,
                trace_id=trace_id,
                template_sha256=sha256_file(modelo_path) if modelo_path else None,
                template_version=template_source,
                input_sha256=sha256_file(sicapex_path) if sicapex_path else None,
                output_sha256=None,
                metadata={
                    "ano": ano,
                    "semestre": semestre,
                    "militar": result.profile.nome_completo,
                    "identidade": result.profile.identidade,
                    "eventos": result.events_count,
                    "tabelas": result.tables_count,
                    "alteracoes_sha256": sha256_file(bi_path),
                    "alteracoes_role": bi_role,
                    "modelo_role": modelo_role,
                    "template_source": template_source,
                    "memory_reference_file_id": memory_reference_file.id if memory_reference_file else None,
                    "fonte_eventos": run.fonte_eventos,
                    "package_mode": OUTPUT_MODE_PARTE1,
                },
            )
            manifest = _manifest_payload(
                run=run,
                document_id=document.id,
                result=result,
                variables_payload=variables_payload,
                files=manifest_files,
                validations=validations,
                package_mode=OUTPUT_MODE_PARTE1,
                warnings=package_warnings,
            )
            _write_json(manifest_path, manifest)
            manifest_files.append(_file_to_manifest_item("MANIFEST_JSON", manifest_path))
            final_path.write_bytes(result.parte1_output_path.read_bytes())
            output_sha256 = sha256_file(final_path)
            document.output_sha256 = output_sha256
            document.metadata_json = {
                **(document.metadata_json or {}),
                "output_sha256": output_sha256,
                "contains": ["parte_1_alteracoes.odt"],
            }
            memory_service.register_output_file(
                run=run,
                source_path=variables_path,
                role="VARIABLES_JSON",
                owner_user_id=owner_user_id,
                militar_id=run.militar_id,
                source_kind="variables",
            )
            memory_service.register_output_file(
                run=run,
                source_path=compiler_run_path,
                role="DEBUG_PARSE_JSON",
                owner_user_id=owner_user_id,
                militar_id=run.militar_id,
                source_kind="compiler_run",
            )
            memory_service.register_output_file(
                run=run,
                source_path=manifest_path,
                role="DEBUG_PARSE_JSON",
                owner_user_id=owner_user_id,
                militar_id=run.militar_id,
                source_kind="manifest",
            )
            memory_service.register_existing_document_file(
                run=run,
                source_path=final_path,
                role="OUTPUT_PARTE1_ODT",
                document_id=document.id,
                militar_id=run.militar_id,
                original_filename=final_path.name,
                mime_type="application/vnd.oasis.opendocument.text",
                source_kind="folha_alteracoes_parte1",
            )
            memory_service.add_validation(
                run_id=run.id,
                level="OK",
                code="OK_PARTE1_DOCUMENT_REGISTERED",
                message="ODT isolado da 1a Parte registrado no historico geral de documentos.",
            )
            db.flush()
            db.commit()
            return PackageResult(
                final_path=final_path,
                filename=final_path.name,
                document_id=document.id,
                run_id=run.id,
                package_mode=OUTPUT_MODE_PARTE1,
                media_type="application/vnd.oasis.opendocument.text",
            )

        package_path = output_dir / f"{result.slug}_compilador_sisges.zip"
        final_path = Path("data/outputs") / package_path.name
        final_path.parent.mkdir(parents=True, exist_ok=True)
        document = document_service.register_document(
            kind="FOLHA_ALTERACOES_ZIP",
            filename=final_path.name,
            status="generated",
            source_module="compilador.folha",
            output_path=str(final_path).replace("\\", "/"),
            owner_user_id=owner_user_id,
            trace_id=trace_id,
            template_sha256=sha256_file(modelo_path) if modelo_path else None,
            template_version=template_source,
            input_sha256=sha256_file(sicapex_path) if sicapex_path else None,
            output_sha256=None,
            metadata={
                "ano": ano,
                "semestre": semestre,
                "militar": result.profile.nome_completo,
                "identidade": result.profile.identidade,
                "eventos": result.events_count,
                "tabelas": result.tables_count,
                "tempo_origem": result.times.origem,
                "sicapex_context_status": (
                    sicapex_context.get("status_confiabilidade") if sicapex_context else "SEM_SICAPEX"
                ),
                "ttes": result.times.ttes,
                "tc": result.times.tc,
                "tnc": result.times.tnc,
                "alteracoes_sha256": sha256_file(bi_path),
                "alteracoes_role": bi_role,
                "sicapex_pdf_sha256": sha256_file(sicapex_path) if sicapex_path else None,
                "modelo_role": modelo_role,
                "template_source": template_source,
                "memory_reference_file_id": memory_reference_file.id if memory_reference_file else None,
                "fonte_eventos": run.fonte_eventos,
                "package_mode": package_mode,
            },
        )

        manifest = _manifest_payload(
            run=run,
            document_id=document.id,
            result=result,
            variables_payload=variables_payload,
            files=manifest_files,
            validations=validations,
            package_mode=package_mode,
            warnings=package_warnings,
        )
        _write_json(manifest_path, manifest)
        manifest_files.append(_file_to_manifest_item("MANIFEST_JSON", manifest_path))

        if full_package:
            entries = [
                (result.output_path, "folha_alteracoes.odt"),
                *(
                    [(result.parte1_output_path, "parte_1_alteracoes.odt")]
                    if result.parte1_output_path and result.parte1_output_path.exists()
                    else []
                ),
                (result.validation_path, "validacao.txt"),
                (result.justification_path, "justificativa.txt"),
                (variables_path, "variables.json"),
                (compiler_run_path, "compiler_run.json"),
                (manifest_path, "manifest.json"),
            ]
        else:
            entries = [
                (result.output_path, result.output_path.name),
                (result.validation_path, result.validation_path.name),
                (result.justification_path, result.justification_path.name),
            ]
        _build_zip(package_path=package_path, entries=entries)
        final_path.write_bytes(package_path.read_bytes())

        output_sha256 = sha256_file(final_path)
        document.output_sha256 = output_sha256
        document.metadata_json = {
            **(document.metadata_json or {}),
            "output_sha256": output_sha256,
            "contains": [arcname for _, arcname in entries],
        }

        if full_package:
            memory_service.register_output_file(
                run=run,
                source_path=variables_path,
                role="VARIABLES_JSON",
                owner_user_id=owner_user_id,
                militar_id=run.militar_id,
                source_kind="variables",
            )
            memory_service.register_output_file(
                run=run,
                source_path=compiler_run_path,
                role="DEBUG_PARSE_JSON",
                owner_user_id=owner_user_id,
                militar_id=run.militar_id,
                source_kind="compiler_run",
            )
            memory_service.register_output_file(
                run=run,
                source_path=manifest_path,
                role="DEBUG_PARSE_JSON",
                owner_user_id=owner_user_id,
                militar_id=run.militar_id,
                source_kind="manifest",
            )
        memory_service.register_existing_document_file(
            run=run,
            source_path=final_path,
            role="OUTPUT_ZIP",
            document_id=document.id,
            militar_id=run.militar_id,
            original_filename=final_path.name,
            mime_type="application/zip",
            source_kind="folha_alteracoes_zip",
        )
        memory_service.add_validation(
            run_id=run.id,
            level="OK",
            code="OK_DOCUMENT_REGISTERED",
            message="ZIP registrado no historico geral de documentos.",
        )
        db.flush()
        db.commit()
    except UploadValidationError as exc:
        memory_service.fail_run(run, error_message=exc.message)
        db.commit()
        raise bad_request(exc.code, exc.message) from exc
    except HTTPException as exc:
        memory_service.fail_run(run, error_message=str(exc.detail))
        db.commit()
        raise
    except Exception as exc:
        memory_service.fail_run(run, error_message=str(exc))
        db.commit()
        raise bad_request("COMPILADOR_FOLHA_FALHOU", f"Falha ao compilar Folha: {exc}") from exc

    return PackageResult(
        final_path=final_path,
        filename=final_path.name,
        document_id=document.id,
        run_id=run.id,
        package_mode=package_mode,
        media_type="application/zip",
    )
