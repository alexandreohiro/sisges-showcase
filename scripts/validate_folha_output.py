from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET


REQUIRED_FILES = [
    "compiler_run.json",
    "folha_alteracoes.odt",
    "folha_alteracoes.pdf",
    "validacao.txt",
    "justificativa.txt",
    "variables.json",
    "pacote.zip",
]
MONTHS_BY_SEMESTER = {
    "1": ["JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO"],
    "2": ["JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"],
}
RAW_QMS_PATTERNS = [
    r"QUALQUER QMG",
    r"QUALQUER QMP",
    r"MANUTENÇÃO DE VIATURA",
    r"MANUTENCAO DE VIATURA",
    r"QMG 00",
    r"\b\d{3,6}\s*-\s*QMS",
]
CRITICAL_CODES = {
    "ERR_TEMPLATE_IGNORED",
    "ERR_TEMPLATE_ANCHOR_NOT_FOUND",
    "ERR_ODT_INVALIDO",
    "ERR_CONTENT_XML_INVALID",
    "ERR_MONTH_DUPLICATED",
    "ERR_MISSING_REQUIRED_MONTH",
    "ERR_QMS_RAW_LEAKED",
    "ERR_MILITAR_NOT_FOUND",
    "ERR_IDENTIDADE_MISSING",
    "ERR_DATA_PRACA_MISSING",
    "ERR_TEMPO_CALCULO_FAILED",
}


@dataclass(slots=True)
class FolhaValidationResult:
    folder: str
    militar: str = ""
    identidade: str = ""
    status: str = "OK"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    qms_raw: str = ""
    qms_normalizado: str = ""
    template_used: bool = False
    odt_path: str = ""
    pdf_path: str = ""
    zip_path: str = ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Valida saida individual ou lote de Folhas de Alteracoes.")
    parser.add_argument("--folder", required=True)
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--allow-pending", action="store_true", default=True)
    args = parser.parse_args()

    root = Path(args.folder)
    if args.recursive:
        folders = [path for path in root.iterdir() if path.is_dir() and (path / "variables.json").exists()]
        if (root / "variables.json").exists():
            folders.insert(0, root)
    else:
        folders = [root]

    results = [validate_folder(folder, allow_pending=args.allow_pending) for folder in folders]
    payload = {
        "folder": str(root),
        "total": len(results),
        "ok": sum(item.status == "OK" for item in results),
        "warning": sum(item.status == "WARNING" for item in results),
        "failed": sum(item.status == "FAILED" for item in results),
        "items": [asdict(item) for item in results],
    }
    output_json = root / "validation_result.json"
    output_txt = root / "validation_result.txt"
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    output_txt.write_text(build_text_report(payload), encoding="utf-8")
    print(output_txt.read_text(encoding="utf-8"))
    if payload["failed"]:
        raise SystemExit(1)


def validate_folder(folder: Path, *, allow_pending: bool) -> FolhaValidationResult:
    result = FolhaValidationResult(folder=str(folder))
    for filename in REQUIRED_FILES:
        if not (folder / filename).exists():
            result.errors.append(f"ERR_MISSING_FILE:{filename}")

    variables = read_json(folder / "variables.json")
    run = read_json(folder / "compiler_run.json")
    validation_text = read_text(folder / "validacao.txt")
    result.militar = str((variables.get("militar") or {}).get("nome_completo") or run.get("nome") or "")
    result.identidade = str((variables.get("militar") or {}).get("identidade") or "")
    qms = variables.get("qms") or {}
    template = variables.get("template") or {}
    result.qms_raw = str(qms.get("raw") or "")
    result.qms_normalizado = str(qms.get("display") or "")
    result.template_used = bool(template.get("used"))
    result.odt_path = str(folder / "folha_alteracoes.odt")
    result.pdf_path = str(folder / "folha_alteracoes.pdf")
    result.zip_path = str(folder / "pacote.zip")

    validate_run(run, folder, result)
    validate_odt(folder / "folha_alteracoes.odt", variables, result)
    validate_pdf(folder / "folha_alteracoes.pdf", result)
    validate_variables(variables, result)
    validate_validation_text(validation_text, allow_pending=allow_pending, result=result)

    if result.errors:
        result.status = "FAILED"
    elif result.warnings:
        result.status = "WARNING"
    return result


def validate_run(run: dict, folder: Path, result: FolhaValidationResult) -> None:
    status = run.get("status")
    if (folder / "folha_alteracoes.odt").exists() and status == "RECEBIDO":
        result.errors.append("ERR_RUN_STATUS_INCONSISTENTE")
    if status not in {"CONCLUIDO", "CONCLUIDO_COM_PENDENCIAS", "FALHOU"}:
        result.errors.append("ERR_RUN_STATUS_INVALIDO")


def validate_odt(path: Path, variables: dict, result: FolhaValidationResult) -> None:
    if not path.exists():
        return
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "content.xml" not in names:
                result.errors.append("ERR_CONTENT_XML_MISSING")
                return
            if "styles.xml" not in names:
                result.errors.append("ERR_STYLES_XML_MISSING")
            content = archive.read("content.xml").decode("utf-8", errors="ignore")
            ET.fromstring(content.encode("utf-8"))
    except Exception as exc:
        result.errors.append(f"ERR_ODT_INVALIDO:{exc}")
        return

    semestre = str((variables.get("periodo") or {}).get("semestre") or "2")
    for month in MONTHS_BY_SEMESTER.get(semestre, MONTHS_BY_SEMESTER["2"]):
        if content.count(month) == 0:
            result.errors.append(f"ERR_MISSING_REQUIRED_MONTH:{month}")
    for pattern in RAW_QMS_PATTERNS:
        if re.search(pattern, content, re.I):
            result.errors.append("ERR_QMS_RAW_LEAKED")
            break
    for marker in ("1ª PARTE", "2ª PARTE"):
        if marker not in content:
            result.errors.append(f"ERR_MARKER_MISSING:{marker}")
    if "SIGNATARIO PRACA" in content or "SIGNATARIO OFICIAL" in content:
        result.errors.append("ERR_SIGNATURE_IS_PLACEHOLDER")
    elif not re.search(r"[A-ZÁÀÃÂÉÊÍÓÔÕÚ]{5,}", content):
        result.warnings.append("WARN_SIGNATURE_TEXT_NOT_CONFIRMED")


def validate_pdf(path: Path, result: FolhaValidationResult) -> None:
    if not path.exists():
        return
    if path.stat().st_size <= 0:
        result.errors.append("ERR_PDF_EMPTY")
    elif path.read_bytes()[:5] != b"%PDF-":
        result.warnings.append("WARN_PDF_HEADER_NOT_CONFIRMED")


def validate_variables(variables: dict, result: FolhaValidationResult) -> None:
    for key in ("militar", "periodo", "eventos_por_mes", "tempo", "validations"):
        if key not in variables:
            result.errors.append(f"ERR_VARIABLES_MISSING:{key}")
    if variables.get("template", {}).get("provided") and not variables.get("template", {}).get("used"):
        result.errors.append("ERR_TEMPLATE_IGNORED")


def validate_validation_text(text: str, *, allow_pending: bool, result: FolhaValidationResult) -> None:
    for code in CRITICAL_CODES:
        if code in text:
            result.errors.append(code)
    if not allow_pending and "WARN_" in text:
        result.errors.append("ERR_PENDING_NOT_ALLOWED")
    if "OK_TEMPLATE_USED" not in text:
        result.errors.append("ERR_TEMPLATE_USED_VALIDATION_MISSING")
    if "OK_QMS_NORMALIZED" not in text and "WARN_QMS_GENERICO" not in text and "WARN_QMS_NAO_RECONHECIDO" not in text:
        result.warnings.append("WARN_QMS_VALIDATION_MISSING")


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def build_text_report(payload: dict) -> str:
    lines = [
        "RELATORIO DE VALIDACAO DE FOLHAS",
        f"Pasta: {payload['folder']}",
        f"Total: {payload['total']}",
        f"OK: {payload['ok']}",
        f"Warnings: {payload['warning']}",
        f"Falhas: {payload['failed']}",
        "",
    ]
    for item in payload["items"]:
        lines.extend(
            [
                f"Militar: {item['militar'] or '-'}",
                f"Identidade: {item['identidade'] or '-'}",
                f"Status: {item['status']}",
                f"QMS raw: {item['qms_raw'] or '-'}",
                f"QMS normalizado: {item['qms_normalizado'] or '-'}",
                f"Template usado: {item['template_used']}",
                f"Erros: {', '.join(item['errors']) if item['errors'] else '-'}",
                f"Warnings: {', '.join(item['warnings']) if item['warnings'] else '-'}",
                f"ODT: {item['odt_path']}",
                f"PDF: {item['pdf_path']}",
                f"ZIP: {item['zip_path']}",
                "",
            ]
        )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
