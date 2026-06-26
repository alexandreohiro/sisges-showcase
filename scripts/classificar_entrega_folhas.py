from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


BLOCKING_CODES = {
    "ERR_ODT_INVALIDO",
    "ERR_CONTENT_XML_INVALID",
    "ERR_TEMPLATE_IGNORED",
    "ERR_TEMPLATE_ANCHOR_NOT_FOUND",
    "ERR_QMS_RAW_LEAKED",
    "ERR_MONTH_DUPLICATED",
    "ERR_MISSING_REQUIRED_MONTH",
    "ERR_MILITAR_NOT_FOUND",
    "ERR_IDENTIDADE_MISSING",
    "ERR_TEMPO_CALCULO_FAILED",
    "ERR_SIGNATURE_MISSING",
    "ERR_OUTPUT_FILE_MISSING",
}
REQUIRED_OUTPUTS = [
    "compiler_run.json",
    "folha_alteracoes.odt",
    "folha_alteracoes.pdf",
    "validacao.txt",
    "justificativa.txt",
    "variables.json",
    "pacote.zip",
]


@dataclass(slots=True)
class DeliveryItem:
    classificacao: str
    semestre_dir: str
    folder: str
    militar_id: str = ""
    nome_completo: str = ""
    nome_guerra: str = ""
    identidade: str = ""
    posto_grad: str = ""
    ano: str = ""
    semestre: str = ""
    status_run: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    odt_path: str = ""
    pdf_path: str = ""
    zip_path: str = ""
    observacao: str = ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Classifica Folhas de Alteracoes para entrega final.")
    parser.add_argument("--input", required=True, help="Diretorio raiz da entrega final.")
    parser.add_argument("--output", required=True, help="Diretorio de relatorios de entrega.")
    args = parser.parse_args()

    input_root = Path(args.input)
    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)

    items = [classify_folder(folder, input_root) for folder in discover_folha_folders(input_root)]
    ready = [item for item in items if item.classificacao == "PRONTA_ASSINATURA"]
    review = [item for item in items if item.classificacao == "REVISAR_ANTES_ASSINATURA"]
    blocked = [item for item in items if item.classificacao == "BLOQUEADA"]

    write_csv(output_root / "folhas_prontas.csv", ready)
    write_csv(output_root / "folhas_revisar.csv", review)
    write_csv(output_root / "folhas_bloqueadas.csv", blocked)
    write_summary(output_root / "resumo_entrega.txt", input_root, items, ready, review, blocked)
    write_checklist(output_root / "checklist_assinatura.txt", ready, review, blocked)
    write_executive_report(input_root / "RELATORIO_EXECUTIVO_SECRETARIA.txt", items, ready, review, blocked)
    write_checklist(input_root / "CHECKLIST_ASSINATURA.txt", ready, review, blocked)
    write_json(output_root / "classificacao_entrega.json", [asdict(item) for item in items])

    print("ENTREGA CLASSIFICADA")
    print(f"Total de folhas: {len(items)}")
    print(f"Prontas: {len(ready)}")
    print(f"Revisar: {len(review)}")
    print(f"Bloqueadas: {len(blocked)}")
    print(f"Relatorios: {output_root}")


def discover_folha_folders(root: Path) -> list[Path]:
    folders: list[Path] = []
    for path in root.rglob("variables.json"):
        folder = path.parent
        if (folder / "folha_alteracoes.odt").exists() or (folder / "validacao.txt").exists():
            folders.append(folder)
    return sorted(folders)


def classify_folder(folder: Path, input_root: Path) -> DeliveryItem:
    variables = read_json(folder / "variables.json")
    run = read_json(folder / "compiler_run.json")
    validation = read_text(folder / "validacao.txt")
    militar = variables.get("militar") or {}
    periodo = variables.get("periodo") or {}
    warnings = extract_codes(validation, "WARN_")
    errors = extract_codes(validation, "ERR_")

    for filename in REQUIRED_OUTPUTS:
        if not (folder / filename).exists():
            errors.append("ERR_OUTPUT_FILE_MISSING")

    blocking_errors = sorted(set(errors) & BLOCKING_CODES)
    if blocking_errors:
        classificacao = "BLOQUEADA"
        observacao = "Erro critico: " + ", ".join(blocking_errors)
    elif warnings:
        classificacao = "REVISAR_ANTES_ASSINATURA"
        observacao = "Warnings: " + ", ".join(sorted(set(warnings)))
    else:
        classificacao = "PRONTA_ASSINATURA"
        observacao = "Sem pendencias bloqueantes."

    return DeliveryItem(
        classificacao=classificacao,
        semestre_dir=semester_dir(folder, input_root),
        folder=str(folder),
        militar_id=str(militar.get("id") or run.get("militar_id") or ""),
        nome_completo=str(militar.get("nome_completo") or run.get("nome") or ""),
        nome_guerra=str(militar.get("nome_guerra") or ""),
        identidade=str(militar.get("identidade") or ""),
        posto_grad=str(militar.get("posto_graduacao") or ""),
        ano=str(periodo.get("ano") or ""),
        semestre=str(periodo.get("semestre") or ""),
        status_run=str(run.get("status") or ""),
        warnings=warnings,
        errors=errors,
        odt_path=str(folder / "folha_alteracoes.odt"),
        pdf_path=str(folder / "folha_alteracoes.pdf"),
        zip_path=str(folder / "pacote.zip"),
        observacao=observacao,
    )


def semester_dir(folder: Path, input_root: Path) -> str:
    try:
        relative = folder.relative_to(input_root)
    except ValueError:
        return ""
    return relative.parts[0] if len(relative.parts) > 1 else input_root.name


def extract_codes(text: str, prefix: str) -> list[str]:
    codes: list[str] = []
    for line in text.splitlines():
        stripped = line.strip().lstrip("-").strip()
        token = stripped.split(":", 1)[0].split()[0] if stripped else ""
        if token.startswith(prefix):
            codes.append(token)
    return codes


def write_csv(path: Path, items: list[DeliveryItem]) -> None:
    fieldnames = [
        "classificacao",
        "semestre_dir",
        "militar_id",
        "posto_grad",
        "nome_completo",
        "nome_guerra",
        "identidade",
        "ano",
        "semestre",
        "status_run",
        "warnings",
        "errors",
        "odt_path",
        "pdf_path",
        "zip_path",
        "observacao",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            row = asdict(item)
            row["warnings"] = ";".join(item.warnings)
            row["errors"] = ";".join(item.errors)
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def write_summary(
    path: Path,
    input_root: Path,
    items: list[DeliveryItem],
    ready: list[DeliveryItem],
    review: list[DeliveryItem],
    blocked: list[DeliveryItem],
) -> None:
    warning_counter = Counter(code for item in items for code in item.warnings)
    error_counter = Counter(code for item in items for code in item.errors)
    lines = [
        "RESUMO DA ENTREGA FINAL DAS FOLHAS DE ALTERACOES",
        f"Entrada: {input_root}",
        f"Gerado em: {datetime.now().isoformat(timespec='seconds')}",
        f"Total de folhas: {len(items)}",
        f"Prontas para assinatura: {len(ready)}",
        f"Revisar antes da assinatura: {len(review)}",
        f"Bloqueadas: {len(blocked)}",
        "",
        "Warnings:",
    ]
    lines.extend(f"- {code}: {count}" for code, count in sorted(warning_counter.items()))
    lines.extend(["", "Erros:"])
    lines.extend(f"- {code}: {count}" for code, count in sorted(error_counter.items()))
    lines.extend(["", "Bloqueadas:"])
    lines.extend(f"- {item.nome_completo} ({item.identidade}): {item.observacao}" for item in blocked)
    lines.extend(["", "Revisar:"])
    lines.extend(f"- {item.nome_completo} ({item.identidade}): {item.observacao}" for item in review)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_checklist(path: Path, ready: list[DeliveryItem], review: list[DeliveryItem], blocked: list[DeliveryItem]) -> None:
    lines = [
        "CHECKLIST DE ASSINATURA",
        "",
        "1. Conferencia por amostragem:",
        "- abrir 3 PDFs aleatorios;",
        "- abrir 1 PDF com muitos eventos;",
        "- abrir 1 PDF com QMS generico;",
        "- abrir 1 PDF de oficial, se houver;",
        "- abrir 1 PDF de praca;",
        "- conferir assinatura.",
        "",
        "2. Conferencia obrigatoria:",
        "- todas as folhas BLOQUEADAS;",
        "- todas com ERR_TEMPLATE_IGNORED;",
        "- todas com ERR_QMS_RAW_LEAKED;",
        "- todas com ERR_TEMPO_CALCULO_FAILED;",
        "- todas com ERR_MONTH_DUPLICATED;",
        "- todas com ERR_MISSING_REQUIRED_MONTH.",
        "",
        "3. Conferencia visual rapida:",
        "- cabecalho;",
        "- meses;",
        "- 1a Parte;",
        "- 2a Parte;",
        "- assinatura;",
        "- PDF abre;",
        "- ODT abre.",
        "",
        "4. Decisao:",
        f"- PRONTA_ASSINATURA: {len(ready)} folhas.",
        f"- REVISAR_ANTES_ASSINATURA: {len(review)} folhas.",
        f"- BLOQUEADA: {len(blocked)} folhas.",
        "",
        "Folhas bloqueadas:",
    ]
    lines.extend(f"- {item.nome_completo} ({item.identidade}): {item.observacao}" for item in blocked)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_executive_report(path: Path, items: list[DeliveryItem], ready: list[DeliveryItem], review: list[DeliveryItem], blocked: list[DeliveryItem]) -> None:
    periods = sorted({f"{item.ano}/{item.semestre}" for item in items if item.ano and item.semestre})
    lines = [
        "RELATORIO DE PRODUCAO DAS FOLHAS DE ALTERACOES",
        "",
        "1. Periodo processado:",
        f"- periodos: {', '.join(periods) if periods else '-'}",
        "- OM: B Adm QGEx",
        f"- data/hora: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "2. Fontes utilizadas:",
        "- SQL.zip / SiCaPEx;",
        "- PDFs de alteracoes 2025;",
        "- modelo ODT oficial;",
        "- modulo de calculo de tempo;",
        "- memoria do Compilador.",
        "",
        "3. Quantitativo:",
        f"- militares processados: {len(items)}",
        f"- folhas geradas: {len(items)}",
        f"- folhas prontas: {len(ready)}",
        f"- folhas para revisar: {len(review)}",
        f"- folhas bloqueadas: {len(blocked)}",
        f"- arquivos ODT: {sum(1 for item in items if Path(item.odt_path).exists())}",
        f"- arquivos PDF: {sum(1 for item in items if Path(item.pdf_path).exists())}",
        f"- pendencias: {sum(len(item.warnings) + len(item.errors) for item in items)}",
        "",
        "4. Criterios aplicados:",
        "- meses obrigatorios;",
        "- Sem alteracoes.;",
        "- cabecalho;",
        "- QMS normalizado;",
        "- assinatura por oficial/praca;",
        "- tempo calculado ou pendente de validacao humana;",
        "- validacao estrutural.",
        "",
        "5. Pendencias:",
    ]
    for item in review + blocked:
        codes = item.errors or item.warnings
        lines.append(f"- {item.nome_completo} ({item.identidade}): {', '.join(codes)}")
    lines.extend(
        [
            "",
            "6. Proximo passo:",
            "- assinar folhas prontas;",
            "- corrigir bloqueadas;",
            "- revisar pendentes;",
            "- arquivar pacote.",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
