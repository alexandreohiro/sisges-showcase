from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass, field
from datetime import datetime
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import uuid
import zipfile


DOCS_REQUIRED = {
    "docs/COMPILADOR_FOLHAS_ALTERACOES_PROCESSO.md": [
        "A dor que o processo resolve",
        "O que é uma Folha de Alterações",
        "Por que não é CRUD",
        "Entradas do processo",
        "SiCaPEx",
        "PDFs de alterações",
        "Modelo ODT oficial",
        "1ª Parte",
        "2ª Parte",
        "Comportamento",
        "Assinatura",
        "Validação",
        "Justificativa",
        "Memória do Compilador",
        "Reprocessamento",
        "Checklist humano",
        "Erros clássicos",
        "Conclusão operacional",
        "validado pela secretaria",
    ],
    "docs/CHECKLIST_OPERADOR_FOLHAS.md": [
        "Antes da assinatura",
        "Conferir",
        "FOLHAS_PRONTAS_ASSINATURA",
        "REVISAR_MANUALMENTE",
        "BLOQUEADAS",
    ],
    "docs/FLUXO_RAPIDO_ENTREGA_FOLHAS.md": [
        "Importar",
        "Gerar",
        "Revisar",
        "Empacotar",
        "assinatura",
    ],
    "docs/ERROS_E_HOTFIX_FOLHAS.md": [
        "Erro",
        "Causa",
        "Impacto",
        "Correção",
    ],
}

PACKAGE_SECTIONS = {
    "FOLHAS_PRONTAS_ASSINATURA",
    "REVISAR_MANUALMENTE",
    "BLOQUEADAS",
    "RELATORIOS",
    "LOGS",
    "AMOSTRA_CONFERENCIA",
}

PENDING_CATEGORIES = {
    "ASSINATURA": {
        "ERR_SIGNATURE_MISSING",
        "WARN_ASSINATURA_NAO_CONFIRMADA",
        "WARN_SIGNATURE_ALIGNMENT_NOT_CONFIRMED",
    },
    "TEMPO_SERVICO": {
        "WARN_TEMPO_PENDENTE_VALIDACAO",
        "ERR_TEMPO_CALCULO_FAILED",
        "ERR_DATA_PRACA_MISSING",
        "WARN_TSCMM_DIVERGENTE",
        "WARN_TTES_PENDENTE",
    },
    "FORMATAÇÃO": {
        "WARN_TABLE_UNREPAIRED",
        "WARN_EVENT_TITLE_MISSING",
        "WARN_FONT_NOT_CONFIRMED",
        "WARN_FORMATACAO_DIVERGENTE",
        "WARN_TEMPLATE_STYLE_PARTIAL",
    },
    "DADOS_MILITAR": {
        "WARN_QMS_GENERICO",
        "WARN_QMS_NAO_RECONHECIDO",
        "WARN_NOME_GUERRA_FALLBACK",
        "ERR_IDENTIDADE_MISSING",
    },
    "FONTE_ALTERACAO": {
        "ERR_EVENTO_SEM_ASSOCIACAO",
        "WARN_EVENTO_ASSOCIACAO_BAIXA_CONFIANCA",
        "WARN_MONTH_WITHOUT_EVENTS",
        "WARN_PDF_ALTERACAO_INCOMPLETO",
    },
    "BLOQUEANTE": {
        "ERR_ODT_INVALIDO",
        "ERR_CONTENT_XML_INVALID",
        "ERR_MISSING_REQUIRED_MONTH",
        "ERR_MONTH_DUPLICATED",
        "ERR_TEMPLATE_IGNORED",
        "ERR_TEMPLATE_ANCHOR_NOT_FOUND",
        "ERR_TEMPLATE_PLACEHOLDER_UNRESOLVED",
        "ERR_QMS_RAW_LEAKED",
        "ERR_MILITAR_NOT_FOUND",
        "ERR_OUTPUT_FILE_MISSING",
    },
}


@dataclass(slots=True)
class PackageValidation:
    pacote: str
    exists: bool
    zip_ok: bool = False
    corrupt_entry: str | None = None
    sha256: str = ""
    sha256_file: str | None = None
    sha256_matches_file: bool | None = None
    entries_count: int = 0
    duplicate_entries: list[str] = field(default_factory=list)
    sections: dict[str, bool] = field(default_factory=dict)
    has_report: bool = False
    has_checklist: bool = False
    has_manifest: bool = False
    has_auditoria: bool = False
    prontas: int = 0
    revisar: int = 0
    bloqueadas: int = 0
    hotfix: int = 0
    odt_count: int = 0
    pdf_count: int = 0
    status: str = "FAILED"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PendingItem:
    categoria: str
    militar: str
    identidade: str
    semestre: str
    arquivo: str
    codigo: str
    descricao: str
    acao_recomendada: str
    prioridade: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Controle operacional de entrega da secretaria.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("diagnostico", help="Gera diagnóstico operacional do SISGES.")

    package_parser = sub.add_parser("validar-pacote", help="Valida pacote revisado de entrega.")
    package_parser.add_argument("--pacote", required=True)

    sub.add_parser("validar-docs", help="Valida documentação operacional.")

    pend_parser = sub.add_parser("listar-pendencias", help="Lista pendências reais da entrega.")
    pend_parser.add_argument("--input", required=True)

    checklist_parser = sub.add_parser("gerar-checklist", help="Gera checklist final de assinatura.")
    checklist_parser.add_argument("--input", required=True)

    register_parser = sub.add_parser("registrar-entrega", help="Registra entrega final.")
    register_parser.add_argument("--pacote", required=True)
    register_parser.add_argument("--responsavel", required=True)
    register_parser.add_argument("--observacao", default="")

    sub.add_parser("resumo", help="Mostra resumo operacional.")

    args = parser.parse_args()
    base_dir = Path.cwd()

    if args.command == "diagnostico":
        result = run_diagnostico(base_dir)
        print_diagnostico(result)
    elif args.command == "validar-pacote":
        result = run_validar_pacote(base_dir, Path(args.pacote))
        print_package_validation(result)
    elif args.command == "validar-docs":
        result = run_validar_docs(base_dir)
        print_docs_validation(result)
    elif args.command == "listar-pendencias":
        items = run_listar_pendencias(base_dir, Path(args.input))
        print(f"PENDENCIAS OPERACIONAIS: {len(items)}")
    elif args.command == "gerar-checklist":
        summary = run_gerar_checklist(base_dir, Path(args.input))
        print(f"CHECKLIST FINAL GERADO: {summary['txt_path']}")
    elif args.command == "registrar-entrega":
        result = run_registrar_entrega(
            base_dir,
            Path(args.pacote),
            responsavel=args.responsavel,
            observacao=args.observacao,
        )
        print(f"REGISTRO DE ENTREGA GERADO: {result['txt_path']}")
    elif args.command == "resumo":
        result = run_resumo(base_dir)
        print_resumo(result)


def run_diagnostico(base_dir: Path) -> dict:
    output_dir = ensure_output_dir(base_dir)
    docs_status = check_docs_presence(base_dir)
    package_path = base_dir / "data/output/PACOTE_ENTREGA_SECRETARIA_REVISADO.zip"
    package_sha_path = base_dir / "data/output/PACOTE_ENTREGA_SECRETARIA_REVISADO.zip.sha256"
    essential_paths = [
        package_path,
        package_sha_path,
        base_dir / "data/output/entrega_final_revisada/RELATORIO_REVISAO_FINAL.txt",
        base_dir / "data/output/entrega_final_revisada/CHECKLIST_ASSINATURA_REVISADO.txt",
    ]
    essential_paths.extend(base_dir / path for path in DOCS_REQUIRED)

    backend_importable = importable("apps.web.app")
    db_status = check_database(base_dir)
    migrations_status = check_alembic_current(base_dir)

    result = {
        "generated_at": now_iso(),
        "backend_importable": backend_importable,
        "database": db_status,
        "migrations": migrations_status,
        "directories": {
            "data": (base_dir / "data").exists(),
            "data_output": output_dir.exists(),
            "docs": (base_dir / "docs").exists(),
            "scripts": (base_dir / "scripts").exists(),
        },
        "essential_files": {str(path.relative_to(base_dir)): path.exists() for path in essential_paths},
        "documentation": docs_status,
        "package_revised_exists": package_path.exists(),
        "permissions_basic": check_permissions_basic(),
        "ruff_status": run_status([sys.executable, "-m", "ruff", "check", "."], base_dir),
        "critical_tests_status": {
            "executed": False,
            "status": "NOT_EXECUTED",
            "detail": "Execute python -m pytest tests/test_secretaria_operacional.py para validação focada.",
        },
    }
    write_json(output_dir / "diagnostico_operacional_sisges.json", result)
    write_text(output_dir / "diagnostico_operacional_sisges.txt", format_diagnostico(result))
    return result


def run_validar_pacote(base_dir: Path, pacote: Path) -> PackageValidation:
    package_path = resolve_project_path(base_dir, pacote)
    result = validate_package(package_path)
    output_dir = ensure_output_dir(base_dir)
    write_json(output_dir / "VALIDACAO_PACOTE_REVISADO.json", asdict(result))
    write_text(output_dir / "VALIDACAO_PACOTE_REVISADO.txt", format_package_validation(result))
    return result


def run_validar_docs(base_dir: Path) -> dict:
    result = validate_docs(base_dir)
    output_dir = ensure_output_dir(base_dir)
    write_json(output_dir / "VALIDACAO_DOCUMENTACAO_OPERACIONAL.json", result)
    write_text(output_dir / "VALIDACAO_DOCUMENTACAO_OPERACIONAL.txt", format_docs_validation(result))
    return result


def run_listar_pendencias(base_dir: Path, input_path: Path) -> list[PendingItem]:
    input_root = resolve_project_path(base_dir, input_path)
    items = collect_pending_items(input_root)
    output_dir = ensure_output_dir(base_dir)
    rows = [asdict(item) for item in items]
    write_json(output_dir / "PENDENCIAS_OPERACIONAIS_SECRETARIA.json", rows)
    write_pending_csv(output_dir / "PENDENCIAS_OPERACIONAIS_SECRETARIA.csv", items)
    write_text(output_dir / "PENDENCIAS_OPERACIONAIS_SECRETARIA.txt", format_pending_items(items))
    return items


def run_gerar_checklist(base_dir: Path, input_path: Path) -> dict:
    input_root = resolve_project_path(base_dir, input_path)
    summary = build_checklist_summary(base_dir, input_root)
    output_dir = ensure_output_dir(base_dir)
    txt_path = output_dir / "CHECKLIST_FINAL_ASSINATURA_SECRETARIA.txt"
    csv_path = output_dir / "CHECKLIST_FINAL_ASSINATURA_SECRETARIA.csv"
    write_text(txt_path, format_final_checklist(summary))
    write_checklist_csv(csv_path, summary)
    return {**summary, "txt_path": str(txt_path), "csv_path": str(csv_path)}


def run_registrar_entrega(base_dir: Path, pacote: Path, responsavel: str, observacao: str) -> dict:
    package_path = resolve_project_path(base_dir, pacote)
    validation = validate_package(package_path)
    output_dir = ensure_output_dir(base_dir)
    result = {
        "data_hora": now_iso(),
        "pacote": str(package_path),
        "sha256": validation.sha256,
        "tamanho_bytes": package_path.stat().st_size if package_path.exists() else 0,
        "responsavel": responsavel,
        "observacao": observacao,
        "folhas_prontas": validation.prontas,
        "revisar_manualmente": validation.revisar,
        "bloqueadas": validation.bloqueadas,
        "testes_executados": "Ver relatórios operacionais e suíte local.",
        "ruff_status": "Ver diagnostico_operacional_sisges.json.",
        "build_status": "Não aplicável ao registro backend; validar frontend separadamente se alterado.",
        "documentos_operacionais": list(DOCS_REQUIRED),
        "checklist": str(base_dir / "data/output/CHECKLIST_FINAL_ASSINATURA_SECRETARIA.txt"),
        "relatorio": str(base_dir / "data/output/entrega_final_revisada/RELATORIO_REVISAO_FINAL.txt"),
        "manifesto": "LOGS/hashes_outputs.json no pacote, quando presente.",
        "document_model_registered": False,
        "document_model_error": "",
    }
    try_register_document_model(package_path, validation, result)
    json_path = output_dir / "REGISTRO_ENTREGA_SECRETARIA.json"
    txt_path = output_dir / "REGISTRO_ENTREGA_SECRETARIA.txt"
    write_json(json_path, result)
    write_text(txt_path, format_delivery_register(result))
    return {**result, "json_path": str(json_path), "txt_path": str(txt_path)}


def run_resumo(base_dir: Path) -> dict:
    package_path = base_dir / "data/output/PACOTE_ENTREGA_SECRETARIA_REVISADO.zip"
    validation = validate_package(package_path)
    docs = validate_docs(base_dir)
    input_root = base_dir / "data/output/entrega_final_revisada"
    pending = collect_pending_items(input_root) if input_root.exists() else []
    return {
        "package": asdict(validation),
        "docs_ok": docs["status"] == "OK",
        "docs": docs,
        "pendencias_count": len(pending),
        "checklist_exists": (base_dir / "data/output/CHECKLIST_FINAL_ASSINATURA_SECRETARIA.txt").exists(),
    }


def validate_package(package_path: Path) -> PackageValidation:
    result = PackageValidation(pacote=str(package_path), exists=package_path.exists())
    if not package_path.exists():
        result.errors.append("Pacote não existe.")
        return result

    result.sha256 = file_sha256(package_path)
    sha_file = package_path.with_suffix(package_path.suffix + ".sha256")
    if sha_file.exists():
        result.sha256_file = str(sha_file)
        expected = parse_sha256_file(sha_file)
        result.sha256_matches_file = expected.lower() == result.sha256.lower()
        if not result.sha256_matches_file:
            result.errors.append("SHA-256 não confere com arquivo .sha256.")

    try:
        with zipfile.ZipFile(package_path) as archive:
            names = archive.namelist()
            result.entries_count = len(names)
            bad = archive.testzip()
            result.zip_ok = bad is None
            result.corrupt_entry = bad
            if bad:
                result.errors.append(f"Entrada corrompida: {bad}")
            result.duplicate_entries = find_duplicates(names)
            if result.duplicate_entries:
                result.errors.append("ZIP contém entradas duplicadas.")
            result.sections = {section: any(name.startswith(section + "/") for name in names) for section in PACKAGE_SECTIONS}
            missing_sections = [section for section, exists in result.sections.items() if not exists]
            if missing_sections:
                result.errors.append("Seções ausentes: " + ", ".join(sorted(missing_sections)))
            result.has_report = any("RELATORIO_REVISAO_FINAL" in name or "relatorio" in name.lower() for name in names)
            result.has_checklist = any("CHECKLIST" in name.upper() for name in names)
            result.has_manifest = any("manifest" in name.lower() or "hashes_outputs.json" in name for name in names)
            result.has_auditoria = any(
                name.endswith(("validacao.txt", "justificativa.txt", "variables.json", "compiler_run.json"))
                for name in names
            )
            result.prontas = count_zip_leaf_folders(names, "FOLHAS_PRONTAS_ASSINATURA")
            result.revisar = count_zip_leaf_folders(names, "REVISAR_MANUALMENTE")
            result.bloqueadas = count_zip_leaf_folders(names, "BLOQUEADAS")
            result.hotfix = count_zip_leaf_folders(names, "HOTFIX_APLICADO")
            result.odt_count = sum(1 for name in names if name.lower().endswith(".odt"))
            result.pdf_count = sum(1 for name in names if name.lower().endswith(".pdf"))
    except zipfile.BadZipFile:
        result.errors.append("Arquivo não é um ZIP válido.")

    for label, ok in {
        "relatório final": result.has_report,
        "checklist": result.has_checklist,
        "manifesto/hashes": result.has_manifest,
        "auditoria individual": result.has_auditoria,
    }.items():
        if not ok:
            result.warnings.append(f"Não foi detectado {label}.")

    if result.exists and result.zip_ok and not result.errors:
        result.status = "OK"
    elif result.exists and result.zip_ok:
        result.status = "WARNING" if not any(error.startswith("Entrada corrompida") for error in result.errors) else "FAILED"
    return result


def validate_docs(base_dir: Path) -> dict:
    files = {}
    overall_ok = True
    for relative, required_terms in DOCS_REQUIRED.items():
        path = base_dir / relative
        text = read_text(path)
        checks = {term: normalize_for_check(term) in normalize_for_check(text) for term in required_terms}
        ok = path.exists() and all(checks.values())
        overall_ok = overall_ok and ok
        files[relative] = {
            "exists": path.exists(),
            "ok": ok,
            "missing_terms": [term for term, present in checks.items() if not present],
        }
    return {"generated_at": now_iso(), "status": "OK" if overall_ok else "FAILED", "files": files}


def collect_pending_items(input_root: Path) -> list[PendingItem]:
    items: list[PendingItem] = []
    for folder in discover_folha_folders(input_root):
        metadata = read_folha_metadata(folder)
        validation_text = read_text(folder / "validacao.txt")
        for code in extract_validation_codes(validation_text):
            if code.startswith("OK_"):
                continue
            category = categorize_code(code)
            items.append(
                PendingItem(
                    categoria=category,
                    militar=metadata["militar"],
                    identidade=metadata["identidade"],
                    semestre=metadata["semestre"],
                    arquivo=str(folder),
                    codigo=code,
                    descricao=describe_code(code),
                    acao_recomendada=recommend_action(code, category),
                    prioridade=priority_for(category, code),
                )
            )
    if not items:
        for csv_path in [input_root / "RELATORIOS/folhas_revisar_manualmente.csv", input_root / "RELATORIOS/folhas_bloqueadas.csv"]:
            items.extend(items_from_review_csv(csv_path))
    return sorted(items, key=lambda item: (item.prioridade, item.categoria, item.militar, item.codigo))


def build_checklist_summary(base_dir: Path, input_root: Path) -> dict:
    package_path = base_dir / "data/output/PACOTE_ENTREGA_SECRETARIA_REVISADO.zip"
    validation = validate_package(package_path)
    ready = list_section_folders(input_root / "FOLHAS_PRONTAS_ASSINATURA")
    review = list_section_folders(input_root / "REVISAR_MANUALMENTE")
    blocked = list_section_folders(input_root / "BLOQUEADAS")
    sample_files = sorted(str(path) for path in (input_root / "AMOSTRA_CONFERENCIA").rglob("*") if path.is_file())
    return {
        "generated_at": now_iso(),
        "package": str(package_path),
        "package_sha256": validation.sha256,
        "package_generated_at": datetime.fromtimestamp(package_path.stat().st_mtime).isoformat(timespec="seconds")
        if package_path.exists()
        else "",
        "total_folhas": len(ready) + len(review) + len(blocked),
        "ready": ready,
        "review": review,
        "blocked": blocked,
        "sample_files": sample_files,
    }


def try_register_document_model(package_path: Path, validation: PackageValidation, result: dict) -> None:
    if not package_path.exists():
        return
    try:
        from infra.persistence.db import SessionLocal
        from infra.persistence.models import DocumentModel

        db = SessionLocal()
        try:
            document = DocumentModel(
                id=str(uuid.uuid4()),
                kind="ENTREGA_SECRETARIA_FOLHAS",
                filename=package_path.name,
                status="delivered",
                source_module="secretaria_operacional",
                output_path=str(package_path),
                output_sha256=validation.sha256,
                metadata_json={
                    "folhas_prontas": validation.prontas,
                    "revisar_manualmente": validation.revisar,
                    "bloqueadas": validation.bloqueadas,
                    "entries_count": validation.entries_count,
                },
                owner_user_id=None,
            )
            db.add(document)
            db.commit()
            result["document_model_registered"] = True
            result["document_id"] = document.id
        finally:
            db.close()
    except Exception as exc:  # pragma: no cover - depends on local DB state
        result["document_model_error"] = str(exc)


def check_docs_presence(base_dir: Path) -> dict:
    return {relative: (base_dir / relative).exists() for relative in DOCS_REQUIRED}


def check_database(base_dir: Path) -> dict:
    db_path = base_dir / "data/sisges.db"
    return {"path": str(db_path), "exists": db_path.exists(), "accessible": db_path.exists() and db_path.is_file()}


def check_alembic_current(base_dir: Path) -> dict:
    if not (base_dir / "alembic.ini").exists():
        return {"status": "NOT_CONFIGURED"}
    return run_status([sys.executable, "-m", "alembic", "current"], base_dir)


def check_permissions_basic() -> dict:
    try:
        from infra.persistence.db import SessionLocal
        from infra.persistence.models import PermissionModel

        required = {
            "compilador.run",
            "compilador.generate_odt",
            "documents.view",
            "documents.download",
        }
        db = SessionLocal()
        try:
            found = {row.key for row in db.query(PermissionModel).filter(PermissionModel.key.in_(required)).all()}
        finally:
            db.close()
        return {"checked": True, "present": sorted(found), "missing": sorted(required - found)}
    except Exception as exc:  # pragma: no cover - depends on DB state
        return {"checked": False, "error": str(exc)}


def importable(module: str) -> dict:
    try:
        importlib.import_module(module)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "error": ""}


def run_status(command: list[str], cwd: Path) -> dict:
    try:
        completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=120, check=False)
        return {
            "executed": True,
            "status": "OK" if completed.returncode == 0 else "FAILED",
            "returncode": completed.returncode,
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-2000:],
        }
    except Exception as exc:
        return {"executed": False, "status": "ERROR", "error": str(exc)}


def discover_folha_folders(root: Path) -> list[Path]:
    if not root.exists():
        return []
    folders: set[Path] = set()
    for marker in ("variables.json", "validacao.txt", "compiler_run.json"):
        for path in root.rglob(marker):
            if (path.parent / "folha_alteracoes.odt").exists() or (path.parent / "validacao.txt").exists():
                folders.add(path.parent)
    return sorted(folders)


def read_folha_metadata(folder: Path) -> dict:
    variables = read_json(folder / "variables.json")
    run = read_json(folder / "compiler_run.json")
    militar = variables.get("militar") or {}
    periodo = variables.get("periodo") or {}
    return {
        "militar": str(militar.get("nome_completo") or run.get("nome_militar_snapshot") or run.get("nome") or folder.name),
        "identidade": str(militar.get("identidade") or run.get("identidade_snapshot") or ""),
        "semestre": str(periodo.get("semestre") or run.get("semestre") or ""),
    }


def extract_validation_codes(text: str) -> list[str]:
    codes: list[str] = []
    for line in text.splitlines():
        cleaned = line.strip().lstrip("-").strip()
        if not cleaned:
            continue
        token = cleaned.split(":", 1)[0].split()[0].strip()
        if token.startswith(("OK_", "WARN_", "ERR_", "CRITICAL_")):
            codes.append(token)
    return sorted(set(codes))


def categorize_code(code: str) -> str:
    for category, codes in PENDING_CATEGORIES.items():
        if code in codes:
            return category
    if code.startswith("ERR_") or code.startswith("CRITICAL_"):
        return "BLOQUEANTE"
    if "TEMPO" in code or "TSCMM" in code or "TTES" in code:
        return "TEMPO_SERVICO"
    if "QMS" in code or "IDENTIDADE" in code or "NOME_GUERRA" in code:
        return "DADOS_MILITAR"
    if "TABLE" in code or "TEMPLATE" in code or "FONT" in code:
        return "FORMATAÇÃO"
    return "FONTE_ALTERACAO"


def priority_for(category: str, code: str) -> str:
    if category == "BLOQUEANTE" or code.startswith(("ERR_", "CRITICAL_")):
        return "P0"
    if category in {"ASSINATURA", "TEMPO_SERVICO"}:
        return "P1"
    return "P2"


def describe_code(code: str) -> str:
    descriptions = {
        "WARN_TEMPO_PENDENTE_VALIDACAO": "Tempo de serviço exige conferência humana.",
        "WARN_QMS_GENERICO": "QMS/QM genérico ou vazio por regra de normalização.",
        "WARN_EVENT_TITLE_MISSING": "Título de evento ausente ou recuperado parcialmente.",
        "WARN_TABLE_UNREPAIRED": "Tabela não foi reconstruída com confiança.",
        "WARN_MONTH_WITHOUT_EVENTS": "Mês sem eventos no período.",
        "ERR_TEMPLATE_IGNORED": "Modelo ODT informado não foi usado.",
        "ERR_QMS_RAW_LEAKED": "QMS bruto apareceu no documento final.",
        "ERR_ODT_INVALIDO": "ODT final inválido.",
        "ERR_MISSING_REQUIRED_MONTH": "Mês obrigatório ausente.",
        "ERR_MONTH_DUPLICATED": "Mês duplicado.",
        "ERR_TEMPO_CALCULO_FAILED": "Cálculo de tempo falhou.",
    }
    return descriptions.get(code, code.replace("_", " ").title())


def recommend_action(code: str, category: str) -> str:
    if category == "BLOQUEANTE":
        return "Corrigir e reprocessar antes da assinatura."
    if category == "TEMPO_SERVICO":
        return "Conferir 2ª Parte e validar com a secretaria."
    if category == "ASSINATURA":
        return "Confirmar regra oficial/praça e reprocessar se necessário."
    if category == "FORMATAÇÃO":
        return "Abrir ODT/PDF e revisar visualmente."
    if category == "DADOS_MILITAR":
        return "Conferir cadastro e dados importados do SiCaPEx."
    return "Conferir fonte de alteração e decidir se permanece."


def items_from_review_csv(path: Path) -> list[PendingItem]:
    if not path.exists():
        return []
    items: list[PendingItem] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            code_text = row.get("warnings") or row.get("errors") or row.get("observacao") or "REVISAR_MANUALMENTE"
            for code in [part.strip() for part in code_text.replace(",", ";").split(";") if part.strip()]:
                category = categorize_code(code)
                items.append(
                    PendingItem(
                        categoria=category,
                        militar=row.get("nome_completo") or row.get("militar") or "",
                        identidade=row.get("identidade") or "",
                        semestre=row.get("semestre") or "",
                        arquivo=row.get("folder") or row.get("arquivo") or str(path),
                        codigo=code,
                        descricao=describe_code(code),
                        acao_recomendada=recommend_action(code, category),
                        prioridade=priority_for(category, code),
                    )
                )
    return items


def list_section_folders(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for folder in sorted(item for item in path.iterdir() if item.is_dir()):
        metadata = read_folha_metadata(folder)
        rows.append(
            {
                "nome": metadata["militar"],
                "identidade": metadata["identidade"],
                "semestre": metadata["semestre"],
                "folder": str(folder),
                "odt": str(folder / "folha_alteracoes.odt"),
                "pdf": str(folder / "folha_alteracoes.pdf"),
            }
        )
    return rows


def count_zip_leaf_folders(names: list[str], section: str) -> int:
    folders = set()
    prefix = section + "/"
    for name in names:
        if not name.startswith(prefix):
            continue
        parts = name[len(prefix) :].split("/")
        if len(parts) >= 2 and parts[0]:
            folders.add(parts[0])
    return len(folders)


def find_duplicates(names: list[str]) -> list[str]:
    seen = set()
    duplicates = set()
    for name in names:
        if name in seen:
            duplicates.add(name)
        seen.add(name)
    return sorted(duplicates)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_sha256_file(path: Path) -> str:
    text = read_text(path).strip()
    return text.split()[0] if text else ""


def ensure_output_dir(base_dir: Path) -> Path:
    output = base_dir / "data/output"
    output.mkdir(parents=True, exist_ok=True)
    return output


def resolve_project_path(base_dir: Path, path: Path) -> Path:
    return path if path.is_absolute() else base_dir / path


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_pending_csv(path: Path, items: list[PendingItem]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(PendingItem("", "", "", "", "", "", "", "", "")).keys()))
        writer.writeheader()
        for item in items:
            writer.writerow(asdict(item))


def write_checklist_csv(path: Path, summary: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["secao", "nome", "identidade", "semestre", "odt", "pdf", "acao"])
        writer.writeheader()
        for section, action in [
            ("ready", "Apta para assinatura após conferência."),
            ("review", "Revisar manualmente antes de assinar."),
            ("blocked", "Bloqueada; corrigir antes."),
        ]:
            for item in summary[section]:
                writer.writerow(
                    {
                        "secao": section,
                        "nome": item["nome"],
                        "identidade": item["identidade"],
                        "semestre": item["semestre"],
                        "odt": item["odt"],
                        "pdf": item["pdf"],
                        "acao": action,
                    }
                )


def normalize_for_check(text: str) -> str:
    return text.lower().replace("ç", "c").replace("ã", "a").replace("á", "a").replace("é", "e")


def format_diagnostico(result: dict) -> str:
    lines = ["SISGES — DIAGNOSTICO OPERACIONAL", ""]
    lines.append(f"Gerado em: {result['generated_at']}")
    lines.append(f"Backend importavel: {result['backend_importable']['ok']}")
    lines.append(f"Banco acessivel: {result['database']['accessible']}")
    lines.append(f"Pacote revisado existe: {result['package_revised_exists']}")
    lines.append(f"Ruff: {result['ruff_status']['status']}")
    lines.append("")
    lines.append("Arquivos essenciais:")
    for path, exists in result["essential_files"].items():
        lines.append(f"- {'OK' if exists else 'FALTA'} {path}")
    return "\n".join(lines) + "\n"


def format_package_validation(result: PackageValidation) -> str:
    lines = ["VALIDACAO DO PACOTE REVISADO", ""]
    lines.append(f"Pacote: {result.pacote}")
    lines.append(f"Status: {result.status}")
    lines.append(f"ZIP OK: {result.zip_ok}")
    lines.append(f"SHA-256: {result.sha256}")
    if result.sha256_matches_file is not None:
        lines.append(f"SHA confere com .sha256: {result.sha256_matches_file}")
    lines.append(f"Entradas: {result.entries_count}")
    lines.append(f"Prontas: {result.prontas}")
    lines.append(f"Revisar: {result.revisar}")
    lines.append(f"Bloqueadas: {result.bloqueadas}")
    lines.append(f"Hotfix: {result.hotfix}")
    lines.append(f"ODTs: {result.odt_count}")
    lines.append(f"PDFs: {result.pdf_count}")
    lines.append("")
    lines.append("Secoes:")
    for section, exists in sorted(result.sections.items()):
        lines.append(f"- {'OK' if exists else 'FALTA'} {section}")
    if result.errors:
        lines.append("")
        lines.append("Erros:")
        lines.extend(f"- {error}" for error in result.errors)
    if result.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in result.warnings)
    return "\n".join(lines) + "\n"


def format_docs_validation(result: dict) -> str:
    lines = ["VALIDACAO DA DOCUMENTACAO OPERACIONAL", "", f"Status: {result['status']}", ""]
    for path, info in result["files"].items():
        lines.append(f"- {'OK' if info['ok'] else 'FALHA'} {path}")
        for term in info["missing_terms"]:
            lines.append(f"  - termo ausente: {term}")
    return "\n".join(lines) + "\n"


def format_pending_items(items: list[PendingItem]) -> str:
    lines = ["PENDENCIAS OPERACIONAIS DA SECRETARIA", "", f"Total: {len(items)}", ""]
    for item in items:
        lines.append(f"[{item.prioridade}] {item.categoria} — {item.codigo}")
        lines.append(f"Militar: {item.militar} | Identidade: {item.identidade} | Semestre: {item.semestre}")
        lines.append(f"Arquivo: {item.arquivo}")
        lines.append(f"Ação: {item.acao_recomendada}")
        lines.append("")
    return "\n".join(lines)


def format_final_checklist(summary: dict) -> str:
    lines = ["CHECKLIST FINAL DE ASSINATURA — SECRETARIA", ""]
    lines.append("1. Pacote principal")
    lines.append(f"- Caminho: {summary['package']}")
    lines.append(f"- SHA-256: {summary['package_sha256']}")
    lines.append(f"- Data de geração: {summary['package_generated_at']}")
    lines.append(f"- Total de folhas: {summary['total_folhas']}")
    lines.append("")
    lines.append("2. Folhas prontas")
    for item in summary["ready"]:
        lines.append(f"- {item['nome']} | {item['identidade']} | ODT: {item['odt']} | PDF: {item['pdf']}")
    lines.append("")
    lines.append("3. Folhas revisar manualmente")
    if not summary["review"]:
        lines.append("- Nenhuma.")
    for item in summary["review"]:
        lines.append(f"- {item['nome']} | {item['identidade']} | revisar antes da assinatura")
    lines.append("")
    lines.append("4. Folhas bloqueadas")
    if not summary["blocked"]:
        lines.append("- Nenhuma.")
    for item in summary["blocked"]:
        lines.append(f"- {item['nome']} | {item['identidade']} | bloqueada")
    lines.append("")
    lines.append("5. Amostra obrigatória")
    for path in summary["sample_files"][:50]:
        lines.append(f"- {path}")
    lines.append("")
    lines.append("6. Conferência humana")
    lines.extend(
        [
            "- abrir 3 PDFs aleatórios;",
            "- conferir cabeçalho;",
            "- conferir meses;",
            "- conferir comportamento;",
            "- conferir 2ª Parte;",
            "- conferir assinatura;",
            "- conferir QMS;",
            "- conferir folhas em REVISAR_MANUALMENTE.",
        ]
    )
    lines.append("")
    lines.append("7. Decisão")
    lines.append("- Prontas: aptas para assinatura após conferência.")
    lines.append("- Revisar manualmente: revisar antes.")
    lines.append("- Bloqueadas: não assinar.")
    return "\n".join(lines) + "\n"


def format_delivery_register(result: dict) -> str:
    lines = ["REGISTRO DE ENTREGA DA SECRETARIA", ""]
    for key in [
        "data_hora",
        "pacote",
        "sha256",
        "tamanho_bytes",
        "responsavel",
        "observacao",
        "folhas_prontas",
        "revisar_manualmente",
        "bloqueadas",
        "document_model_registered",
        "document_model_error",
    ]:
        lines.append(f"{key}: {result.get(key)}")
    return "\n".join(lines) + "\n"


def print_diagnostico(result: dict) -> None:
    print(format_diagnostico(result))


def print_package_validation(result: PackageValidation) -> None:
    print(format_package_validation(result))


def print_docs_validation(result: dict) -> None:
    print(format_docs_validation(result))


def print_resumo(result: dict) -> None:
    package = result["package"]
    print("SISGES — RESUMO OPERACIONAL")
    print("")
    print("Pacote revisado:")
    print(f"- caminho: {package['pacote']}")
    print(f"- sha256: {package['sha256']}")
    print("")
    print("Folhas:")
    print(f"- prontas assinatura: {package['prontas']}")
    print(f"- revisar manualmente: {package['revisar']}")
    print(f"- bloqueadas: {package['bloqueadas']}")
    print("")
    print("Validações:")
    print(f"- pacote: {package['status']}")
    print(f"- docs: {'OK' if result['docs_ok'] else 'FALHA'}")
    print(f"- pendências: {result['pendencias_count']}")
    print(f"- checklist: {'OK' if result['checklist_exists'] else 'FALTA'}")
    print("")
    print("Próxima ação:")
    print("- abrir checklist;")
    print("- revisar amostra;")
    print("- assinar prontas;")
    print("- resolver revisar manualmente.")


if __name__ == "__main__":
    main()
