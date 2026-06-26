from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import shutil
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


LEVEL_A = {
    "WARN_MONTH_WITHOUT_EVENTS",
    "WARN_QMS_GENERICO",
    "WARN_TEMPO_PENDENTE_VALIDACAO",
    "WARN_PDF_PREVIEW_NOT_GENERATED",
}
LEVEL_B = {
    "WARN_EVENT_TITLE_MISSING",
    "WARN_TABLE_UNREPAIRED",
    "WARN_QMS_NAO_RECONHECIDO",
    "WARN_ASSINATURA_NAO_CONFIRMADA",
    "WARN_FORMATACAO_DIVERGENTE",
    "WARN_TEMPLATE_STYLE_PARTIAL",
}
LEVEL_C = {
    "ERR_TEMPLATE_IGNORED",
    "ERR_QMS_RAW_LEAKED",
    "ERR_ODT_INVALIDO",
    "ERR_CONTENT_XML_INVALID",
    "ERR_MONTH_DUPLICATED",
    "ERR_MISSING_REQUIRED_MONTH",
    "ERR_MILITAR_NOT_FOUND",
    "ERR_IDENTIDADE_MISSING",
    "ERR_TEMPO_CALCULO_FAILED",
    "ERR_SIGNATURE_MISSING",
    "ERR_OUTPUT_FILE_MISSING",
}
REQUIRED = [
    "compiler_run.json",
    "folha_alteracoes.odt",
    "folha_alteracoes.pdf",
    "validacao.txt",
    "justificativa.txt",
    "variables.json",
    "pacote.zip",
]


@dataclass(slots=True)
class ReviewRow:
    militar: str
    identidade: str
    posto_grad: str
    semestre: str
    status_atual: str
    warnings: str
    errors: str
    qms_status: str
    tempo_status: str
    eventos_status: str
    template_used: bool
    odt_valido: bool
    pdf_valido: bool
    decisao: str
    acao_recomendada: str
    observacao: str
    folder: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Promove Folhas revisadas para assinatura ou revisao manual.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    input_root = Path(args.input)
    source_root = input_root / "2025_2sem" if (input_root / "2025_2sem").exists() else input_root
    output_root = Path(args.output)
    if output_root.exists():
        shutil.rmtree(output_root)
    prepare_dirs(output_root)

    rows = [classify(folder) for folder in discover_folders(source_root)]
    for row in rows:
        source = Path(row.folder)
        if row.decisao == "PROMOVER_PRONTA_ASSINATURA":
            destination = output_root / "FOLHAS_PRONTAS_ASSINATURA" / source.name
        elif row.decisao == "BLOQUEAR":
            destination = output_root / "BLOQUEADAS" / source.name
        else:
            destination = output_root / "REVISAR_MANUALMENTE" / source.name
        copy_delivery_files(source, destination)

    write_reports(output_root, rows)
    build_sample(output_root, rows)
    build_general_zip(output_root)
    print("REVISAO FINAL CONCLUIDA")
    print(f"Folhas analisadas: {len(rows)}")
    print(f"Promovidas para assinatura: {sum(row.decisao == 'PROMOVER_PRONTA_ASSINATURA' for row in rows)}")
    print("Hotfix aplicado: 0")
    print(f"Revisar manualmente: {sum(row.decisao == 'REVISAR_MANUALMENTE' for row in rows)}")
    print(f"Bloqueadas: {sum(row.decisao == 'BLOQUEAR' for row in rows)}")
    print(f"Relatorio: {output_root / 'RELATORIO_REVISAO_FINAL.txt'}")
    print(f"Checklist: {output_root / 'CHECKLIST_ASSINATURA_REVISADO.txt'}")


def prepare_dirs(output_root: Path) -> None:
    for name in (
        "FOLHAS_PRONTAS_ASSINATURA",
        "REVISAR_MANUALMENTE",
        "HOTFIX_APLICADO",
        "BLOQUEADAS",
        "RELATORIOS",
        "LOGS",
        "AMOSTRA_CONFERENCIA",
    ):
        (output_root / name).mkdir(parents=True, exist_ok=True)


def discover_folders(root: Path) -> list[Path]:
    return sorted(path.parent for path in root.rglob("variables.json") if (path.parent / "validacao.txt").exists())


def classify(folder: Path) -> ReviewRow:
    variables = read_json(folder / "variables.json")
    run = read_json(folder / "compiler_run.json")
    validation = read_text(folder / "validacao.txt")
    militar = variables.get("militar") or {}
    qms = variables.get("qms") or {}
    tempo = variables.get("tempo") or {}
    template = variables.get("template") or {}
    warnings = extract_codes(validation, "WARN_")
    errors = extract_codes(validation, "ERR_")
    for filename in REQUIRED:
        if not (folder / filename).exists():
            errors.append("ERR_OUTPUT_FILE_MISSING")
    odt_ok = validate_odt(folder / "folha_alteracoes.odt")
    pdf_ok = validate_pdf(folder / "folha_alteracoes.pdf")
    if not odt_ok:
        errors.append("ERR_ODT_INVALIDO")
    if not pdf_ok:
        warnings.append("WARN_PDF_PREVIEW_NOT_GENERATED")
    blocking = sorted(set(errors) & LEVEL_C)
    b_warnings = sorted(set(warnings) & LEVEL_B)
    unknown_warnings = sorted(set(warnings) - LEVEL_A - LEVEL_B)
    if blocking:
        decision = "BLOQUEAR"
        action = "Corrigir erro critico antes de assinatura."
        observation = ", ".join(blocking)
    elif b_warnings or unknown_warnings:
        decision = "REVISAR_MANUALMENTE"
        action = "Revisar warning que exige decisao humana."
        observation = ", ".join(b_warnings + unknown_warnings)
    else:
        decision = "PROMOVER_PRONTA_ASSINATURA"
        action = "Pode seguir para assinatura apos conferencia visual de rotina."
        observation = "Somente warnings de nivel A."
    return ReviewRow(
        militar=str(militar.get("nome_completo") or run.get("nome") or ""),
        identidade=str(militar.get("identidade") or ""),
        posto_grad=str(militar.get("posto_graduacao") or ""),
        semestre=str((variables.get("periodo") or {}).get("semestre") or ""),
        status_atual=str(run.get("status") or ""),
        warnings=";".join(warnings),
        errors=";".join(errors),
        qms_status=str(qms.get("status") or ""),
        tempo_status=str(tempo.get("status_calculo") or ""),
        eventos_status="TITULO_PENDENTE" if "WARN_EVENT_TITLE_MISSING" in warnings else "OK",
        template_used=bool(template.get("used")),
        odt_valido=odt_ok,
        pdf_valido=pdf_ok,
        decisao=decision,
        acao_recomendada=action,
        observacao=observation,
        folder=str(folder),
    )


def copy_delivery_files(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for filename in REQUIRED:
        src = source / filename
        if src.exists():
            shutil.copy2(src, destination / filename)


def write_reports(output_root: Path, rows: list[ReviewRow]) -> None:
    reports = output_root / "RELATORIOS"
    write_csv(reports / "matriz_revisao.csv", rows)
    write_json(reports / "matriz_revisao.json", [asdict(row) for row in rows])
    write_csv(reports / "folhas_promovidas.csv", [row for row in rows if row.decisao == "PROMOVER_PRONTA_ASSINATURA"])
    write_csv(reports / "folhas_revisar_manualmente.csv", [row for row in rows if row.decisao == "REVISAR_MANUALMENTE"])
    write_csv(reports / "folhas_bloqueadas.csv", [row for row in rows if row.decisao == "BLOQUEAR"])
    counter = Counter(code for row in rows for code in (row.warnings.split(";") if row.warnings else []))
    package_path = output_root / "pacote_geral_revisao.zip"
    package_sha = sha256(package_path) if package_path.exists() else ""
    lines = [
        "RELATORIO DE REVISAO FINAL",
        f"Gerado em: {datetime.now().isoformat(timespec='seconds')}",
        f"Total inicial em REVISAR: {len(rows)}",
        f"Promovidas para PRONTAS_ASSINATURA: {sum(row.decisao == 'PROMOVER_PRONTA_ASSINATURA' for row in rows)}",
        f"Mantidas para REVISAR_MANUALMENTE: {sum(row.decisao == 'REVISAR_MANUALMENTE' for row in rows)}",
        f"Bloqueadas: {sum(row.decisao == 'BLOQUEAR' for row in rows)}",
        "Hotfix aplicado: 0",
        "",
        "Principais warnings encontrados:",
    ]
    lines.extend(f"- {code}: {count}" for code, count in sorted(counter.items()))
    lines.extend(
        [
            "",
            "Principais correcoes automaticas:",
            "- Nenhuma alteracao automatica aplicada em ODT/PDF aceitavel.",
            "",
            "Pendencias de validacao humana:",
            "- Validar calculo de tempo de servico antes da assinatura.",
            "- Revisar folhas com titulo de evento ausente.",
            "",
            f"Caminho do pacote revisado: {package_path}",
            f"SHA-256 do pacote revisado: {package_sha}",
        ]
    )
    (output_root / "RELATORIO_REVISAO_FINAL.txt").write_text("\n".join(lines), encoding="utf-8")
    (reports / "relatorio_revisao_final.txt").write_text("\n".join(lines), encoding="utf-8")
    checklist = [
        "CHECKLIST DE ASSINATURA REVISADO",
        "",
        "Folhas prontas:",
    ]
    checklist.extend(f"- {row.militar} ({row.identidade})" for row in rows if row.decisao == "PROMOVER_PRONTA_ASSINATURA")
    checklist.extend(["", "Folhas que exigem revisao manual:"])
    checklist.extend(f"- {row.militar} ({row.identidade}): {row.observacao}" for row in rows if row.decisao == "REVISAR_MANUALMENTE")
    checklist.extend(
        [
            "",
            "Orientacoes:",
            "- conferir cabecalho, meses, 1a Parte, 2a Parte e assinatura;",
            "- abrir PDF e ODT da amostra;",
            "- validar manualmente calculo de tempo antes da assinatura.",
        ]
    )
    (output_root / "CHECKLIST_ASSINATURA_REVISADO.txt").write_text("\n".join(checklist), encoding="utf-8")
    (reports / "checklist_assinatura_revisado.txt").write_text("\n".join(checklist), encoding="utf-8")
    write_json(
        output_root / "LOGS" / "resumo_execucao_revisao.json",
        {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "total": len(rows),
            "promovidas": sum(row.decisao == "PROMOVER_PRONTA_ASSINATURA" for row in rows),
            "revisar": sum(row.decisao == "REVISAR_MANUALMENTE" for row in rows),
            "bloqueadas": sum(row.decisao == "BLOQUEAR" for row in rows),
            "hotfix_aplicado": 0,
        },
    )
    write_hashes(output_root)


def build_sample(output_root: Path, rows: list[ReviewRow]) -> None:
    sample_root = output_root / "AMOSTRA_CONFERENCIA"
    selected: list[ReviewRow] = []
    ready = [row for row in rows if row.decisao == "PROMOVER_PRONTA_ASSINATURA"]
    selected.extend(ready[:3])
    qms_generic = next((row for row in rows if "WARN_QMS_GENERICO" in row.warnings), None)
    many_events = max(rows, key=lambda row: len((Path(row.folder) / "validacao.txt").read_text(encoding="utf-8", errors="ignore")), default=None)
    tempo = next((row for row in rows if "WARN_TEMPO_PENDENTE_VALIDACAO" in row.warnings), None)
    praca = next((row for row in rows if row.posto_grad and "Ten" not in row.posto_grad), None)
    for candidate in (qms_generic, many_events, tempo, praca):
        if candidate and candidate not in selected:
            selected.append(candidate)
    if len(selected) < 3:
        pool = rows[:]
        random.Random(20250521).shuffle(pool)
        for candidate in pool:
            if candidate not in selected:
                selected.append(candidate)
            if len(selected) >= 3:
                break
    for row in selected:
        copy_delivery_files(Path(row.folder), sample_root / Path(row.folder).name)
    lines = [
        "CHECKLIST DA AMOSTRA DE CONFERENCIA",
        "",
        "Itens:",
        "- cabecalho correto;",
        "- nome completo;",
        "- nome de guerra em negrito;",
        "- QMS correto/vazio;",
        "- meses completos;",
        "- 2a Parte presente;",
        "- assinatura correta;",
        "- PDF abre;",
        "- ODT abre.",
        "",
        "Folhas da amostra:",
    ]
    lines.extend(f"- {row.militar} ({row.identidade}) - {row.decisao}" for row in selected)
    (sample_root / "checklist_amostra.txt").write_text("\n".join(lines), encoding="utf-8")


def build_general_zip(output_root: Path) -> None:
    package = output_root / "pacote_geral_revisao.zip"
    if package.exists():
        package.unlink()
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output_root.rglob("*")):
            if path.is_file() and path != package:
                archive.write(path, path.relative_to(output_root))
    write_hashes(output_root)
    # Atualiza relatorio com hash real apos criar o pacote.
    rows = [ReviewRow(**item) for item in read_json(output_root / "RELATORIOS" / "matriz_revisao.json")]
    write_reports_without_rebuilding_package(output_root, rows)


def write_reports_without_rebuilding_package(output_root: Path, rows: list[ReviewRow]) -> None:
    package = output_root / "pacote_geral_revisao.zip"
    package_sha = sha256(package)
    counter = Counter(code for row in rows for code in (row.warnings.split(";") if row.warnings else []))
    lines = [
        "RELATORIO DE REVISAO FINAL",
        f"Gerado em: {datetime.now().isoformat(timespec='seconds')}",
        f"Total inicial em REVISAR: {len(rows)}",
        f"Promovidas para PRONTAS_ASSINATURA: {sum(row.decisao == 'PROMOVER_PRONTA_ASSINATURA' for row in rows)}",
        f"Mantidas para REVISAR_MANUALMENTE: {sum(row.decisao == 'REVISAR_MANUALMENTE' for row in rows)}",
        f"Bloqueadas: {sum(row.decisao == 'BLOQUEAR' for row in rows)}",
        "Hotfix aplicado: 0",
        "",
        "Principais warnings encontrados:",
    ]
    lines.extend(f"- {code}: {count}" for code, count in sorted(counter.items()))
    lines.extend(["", "Caminho do pacote revisado:", str(package), "SHA-256 do pacote revisado:", package_sha])
    (output_root / "RELATORIO_REVISAO_FINAL.txt").write_text("\n".join(lines), encoding="utf-8")
    (output_root / "RELATORIOS" / "relatorio_revisao_final.txt").write_text("\n".join(lines), encoding="utf-8")


def write_hashes(output_root: Path) -> None:
    hashes = {}
    for path in sorted(output_root.rglob("*")):
        if path.is_file():
            hashes[str(path.relative_to(output_root))] = sha256(path)
    write_json(output_root / "LOGS" / "hashes_outputs.json", hashes)


def validate_odt(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            return archive.testzip() is None and "content.xml" in archive.namelist() and "styles.xml" in archive.namelist()
    except Exception:
        return False


def validate_pdf(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0 and path.read_bytes()[:5] == b"%PDF-"


def extract_codes(text: str, prefix: str) -> list[str]:
    codes = []
    for line in text.splitlines():
        stripped = line.strip().lstrip("-").strip()
        token = stripped.split(":", 1)[0].split()[0] if stripped else ""
        if token.startswith(prefix):
            codes.append(token)
    return codes


def write_csv(path: Path, rows: list[ReviewRow]) -> None:
    fieldnames = list(asdict(rows[0]).keys()) if rows else list(ReviewRow.__dataclass_fields__.keys())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def read_json(path: Path) -> list | dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
