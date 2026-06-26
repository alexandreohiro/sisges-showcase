from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import zipfile
from xml.etree import ElementTree as ET

from scripts.complete_folha_semi_ok_parte1 import (
    MONTHS_BY_SEMESTER,
    PLACEHOLDER_RE,
    TEXT_H,
    TEXT_P,
    clean_parte1_lines,
    extract_parte1_from_pdf,
    normalize_parte1_paragraphs,
    normalize_text,
    render_parte1_into_odt,
    sha256_file,
    validate_generated_odt,
)


@dataclass(slots=True)
class OdtInspection:
    path: str
    zip_valid: bool
    content_parseable: bool
    styles_parseable: bool
    paragraph_count: int
    text_chars: int
    months_present: dict[str, bool]
    first_part_present: bool
    second_part_present: bool
    placeholder_leftovers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ModeloPdfRunResult:
    status: str
    generated_at: str
    modelo_odt: str
    fonte_pdf: str
    reference_odt: str | None
    output_odt: str
    output_parte1_text: str
    output_validation_json: str
    output_comparison_json: str
    output_report_txt: str
    output_sha256: str
    raw_lines: int
    normalized_paragraphs: int
    blank_paragraphs_removed_between_parts: int
    nonblank_between_parts_before_replacement: list[str]
    warnings: list[str]
    errors: list[str]
    validation: dict
    generated_inspection: dict
    reference_inspection: dict | None
    comparison: dict


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def paragraph_text(element: ET.Element) -> str:
    return "".join(element.itertext()).strip()


def inspect_odt(path: Path, semestre: str) -> OdtInspection:
    errors: list[str] = []
    warnings: list[str] = []
    zip_valid = False
    content_parseable = False
    styles_parseable = False
    text = ""
    paragraph_count = 0
    expected_months = MONTHS_BY_SEMESTER.get(str(semestre), MONTHS_BY_SEMESTER["2"])

    try:
        with zipfile.ZipFile(path, "r") as archive:
            bad = archive.testzip()
            zip_valid = bad is None
            if bad:
                errors.append(f"ERR_ODT_ZIP_CORRUPTED:{bad}")
            content = archive.read("content.xml")
            styles = archive.read("styles.xml")
    except Exception as exc:
        return OdtInspection(
            path=str(path),
            zip_valid=False,
            content_parseable=False,
            styles_parseable=False,
            paragraph_count=0,
            text_chars=0,
            months_present={month: False for month in expected_months},
            first_part_present=False,
            second_part_present=False,
            errors=[f"ERR_ODT_OPEN_FAILED:{exc}"],
        )

    try:
        root = ET.fromstring(content)
        content_parseable = True
        paragraphs = [
            paragraph_text(element)
            for element in root.iter()
            if element.tag in {TEXT_P, TEXT_H} and paragraph_text(element)
        ]
        paragraph_count = len(paragraphs)
        text = "\n".join(paragraphs)
    except Exception as exc:
        errors.append(f"ERR_CONTENT_XML_INVALID:{exc}")

    try:
        ET.fromstring(styles)
        styles_parseable = True
    except Exception as exc:
        errors.append(f"ERR_STYLES_XML_INVALID:{exc}")

    normalized = normalize_text(text)
    placeholders = sorted(set(PLACEHOLDER_RE.findall(text)))
    if placeholders:
        errors.append("ERR_TEMPLATE_PLACEHOLDER_LEFTOVER")
    if "QUALQUER QMG" in normalized or "QUALQUER QMP" in normalized:
        errors.append("ERR_QMS_RAW_LEAKED")
    if any(marker in normalized for marker in ("CPF", "PAGAMENTO", "BENEFICIARIO")):
        warnings.append("WARN_POSSIBLE_SENSITIVE_EVENT")

    return OdtInspection(
        path=str(path),
        zip_valid=zip_valid,
        content_parseable=content_parseable,
        styles_parseable=styles_parseable,
        paragraph_count=paragraph_count,
        text_chars=len(text),
        months_present={month: f"{month}:" in normalized for month in expected_months},
        first_part_present="1A PARTE" in normalized,
        second_part_present="2A PARTE" in normalized,
        placeholder_leftovers=placeholders,
        warnings=warnings,
        errors=errors,
    )


def compare_with_reference(
    generated: OdtInspection,
    reference: OdtInspection | None,
    *,
    raw_lines: int,
    normalized_paragraphs: int,
) -> dict:
    comparison = {
        "schema_version": "sisges-modelo-pdf-reference-comparison-v1",
        "raw_pdf_lines": raw_lines,
        "normalized_paragraphs": normalized_paragraphs,
        "line_normalization_ratio": round(normalized_paragraphs / raw_lines, 4)
        if raw_lines
        else None,
        "generated_months_ok": all(generated.months_present.values()),
        "reference_available": reference is not None,
    }
    if reference:
        comparison.update(
            {
                "reference_months_ok": all(reference.months_present.values()),
                "paragraph_count_generated": generated.paragraph_count,
                "paragraph_count_reference": reference.paragraph_count,
                "paragraph_count_delta": generated.paragraph_count - reference.paragraph_count,
                "text_chars_generated": generated.text_chars,
                "text_chars_reference": reference.text_chars,
                "text_chars_delta": generated.text_chars - reference.text_chars,
                "generated_has_less_or_equal_paragraphs_than_raw_lines": (
                    generated.paragraph_count <= raw_lines
                ),
            }
        )
    return comparison


def write_human_report(result: ModeloPdfRunResult) -> None:
    lines = [
        "RELATORIO SISGES - MODELO ODT + PDF PARA FOLHA DE ALTERACOES",
        f"Gerado em: {result.generated_at}",
        "",
        f"Status: {result.status}",
        f"Modelo ODT: {result.modelo_odt}",
        f"Fonte PDF: {result.fonte_pdf}",
        f"Referencia ODT: {result.reference_odt or '-'}",
        f"ODT gerado: {result.output_odt}",
        f"SHA-256 gerado: {result.output_sha256}",
        "",
        "Leitura do algoritmo:",
        f"- Linhas limpas extraidas do PDF: {result.raw_lines}",
        f"- Paragrafos normalizados inseridos: {result.normalized_paragraphs}",
        "- O modelo ODT foi preservado e a 1a Parte foi substituida entre os marcadores 1a/2a Parte.",
        "- Cabecalhos e rodapes de pagina do PDF foram removidos antes da renderizacao.",
        "- Conteudo potencialmente sensivel nao foi removido automaticamente; foi marcado para revisao.",
        "",
        "Validacao:",
    ]
    for check in result.validation.get("checks", []):
        lines.append(f"- {check}")
    for warning in result.warnings:
        lines.append(f"- WARNING: {warning}")
    for error in result.errors:
        lines.append(f"- ERROR: {error}")
    lines.extend(
        [
            "",
            "Comparacao com referencia:",
            json.dumps(result.comparison, ensure_ascii=False, indent=2),
            "",
            "Conclusao operacional:",
            "- O fluxo consegue partir de um modelo/base ODT e de um PDF de alteracoes para gerar a 1a Parte em ODT.",
            "- Para equivalencia perfeita ao ODT ok, o restante da folha precisa vir do banco/modulo de tempo/ODT semi-pronto validado.",
            "- O caso MORAES exige warning de revisao por conter dados potencialmente sensiveis preservados no documento manual ok.",
        ]
    )
    Path(result.output_report_txt).write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_modelo_pdf(
    *,
    modelo_odt: Path,
    fonte_pdf: Path,
    output_dir: Path,
    semestre: str,
    reference_odt: Path | None = None,
    output_name: str = "folha_modelo_pdf_algoritmo.odt",
) -> ModeloPdfRunResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_odt = output_dir / output_name
    output_text = output_dir / "parte1_normalizada.txt"
    output_validation = output_dir / "validacao_modelo_pdf.json"
    output_comparison = output_dir / "comparacao_referencia.json"
    output_report = output_dir / "RELATORIO_MODELO_PDF_ALGORITMO.txt"

    raw = extract_parte1_from_pdf(fonte_pdf, semestre)
    clean_lines, clean_warnings = clean_parte1_lines(raw)
    paragraphs, paragraph_warnings = normalize_parte1_paragraphs(clean_lines, semestre)
    output_text.write_text("\n".join(paragraphs) + "\n", encoding="utf-8")

    blanks, nonblank_before = render_parte1_into_odt(
        source_odt=modelo_odt,
        output_odt=output_odt,
        parte1_lines=paragraphs,
        semestre=semestre,
    )
    validation = validate_generated_odt(output_odt, semestre)
    validation_payload = asdict(validation)
    output_validation.write_text(
        json.dumps(validation_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    generated_inspection = inspect_odt(output_odt, semestre)
    reference_inspection = inspect_odt(reference_odt, semestre) if reference_odt else None
    comparison = compare_with_reference(
        generated_inspection,
        reference_inspection,
        raw_lines=len(clean_lines),
        normalized_paragraphs=len(paragraphs),
    )
    output_comparison.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    warnings = clean_warnings + paragraph_warnings + validation.warnings
    errors = validation.errors + generated_inspection.errors
    status = "ERROR" if errors else "OK_WITH_WARNINGS" if warnings else "OK"
    result = ModeloPdfRunResult(
        status=status,
        generated_at=now_iso(),
        modelo_odt=str(modelo_odt),
        fonte_pdf=str(fonte_pdf),
        reference_odt=str(reference_odt) if reference_odt else None,
        output_odt=str(output_odt),
        output_parte1_text=str(output_text),
        output_validation_json=str(output_validation),
        output_comparison_json=str(output_comparison),
        output_report_txt=str(output_report),
        output_sha256=sha256_file(output_odt),
        raw_lines=len(clean_lines),
        normalized_paragraphs=len(paragraphs),
        blank_paragraphs_removed_between_parts=blanks,
        nonblank_between_parts_before_replacement=nonblank_before,
        warnings=warnings,
        errors=errors,
        validation=validation_payload,
        generated_inspection=asdict(generated_inspection),
        reference_inspection=asdict(reference_inspection) if reference_inspection else None,
        comparison=comparison,
    )
    (output_dir / "resultado_modelo_pdf.json").write_text(
        json.dumps(asdict(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_human_report(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Renderiza Folha de Alteracoes usando modelo ODT e PDF da 1a Parte."
    )
    parser.add_argument("--modelo", required=True, help="ODT modelo/base.")
    parser.add_argument("--pdf", required=True, help="PDF fonte da 1a Parte.")
    parser.add_argument("--output", required=True, help="Pasta de saida.")
    parser.add_argument("--semestre", choices=["1", "2"], default="2")
    parser.add_argument("--reference-odt", help="ODT ok de referencia para comparacao.")
    parser.add_argument("--output-name", default="folha_modelo_pdf_algoritmo.odt")
    args = parser.parse_args()

    result = run_modelo_pdf(
        modelo_odt=Path(args.modelo),
        fonte_pdf=Path(args.pdf),
        output_dir=Path(args.output),
        semestre=args.semestre,
        reference_odt=Path(args.reference_odt) if args.reference_odt else None,
        output_name=args.output_name,
    )
    print("MODELO + PDF PROCESSADO")
    print(f"Status: {result.status}")
    print(f"ODT: {result.output_odt}")
    print(f"Relatorio: {result.output_report_txt}")
    print(f"Warnings: {len(result.warnings)}")
    print(f"Erros: {len(result.errors)}")


if __name__ == "__main__":
    main()
