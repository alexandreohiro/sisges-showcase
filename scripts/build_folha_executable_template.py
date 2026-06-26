from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree as ET


FLAG_RE = re.compile(r"\[SISGES_[A-Z0-9_]+\]")


@dataclass(slots=True)
class TemplateBuildResult:
    status: str
    generated_at: str
    source_odt: str
    output_odt: str
    contract_json: str
    report_txt: str
    flags_content_xml: list[str]
    flags_styles_xml: list[str]
    structural_checks: list[str]
    warnings: list[str]
    errors: list[str]


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def replace_first_page_period(styles_xml: str) -> str:
    pattern = re.compile(
        r'<text:p text:style-name="MP8">'
        r'<text:span text:style-name="MT13">2</text:span>'
        r'<text:span text:style-name="MT14">º SEMESTRE DE 202</text:span>'
        r'<text:span text:style-name="MT13">5</text:span>'
        r'<text:span text:style-name="MT14"> PERÍODO:</text:span>'
        r'<text:span text:style-name="MT7"> </text:span>'
        r'<text:span text:style-name="MT8">1º </text:span>'
        r'<text:span text:style-name="MT9">JUL</text:span>'
        r'<text:span text:style-name="MT8"> A </text:span>'
        r'<text:span text:style-name="MT10">3</text:span>'
        r'<text:span text:style-name="MT9">1</text:span>'
        r'<text:span text:style-name="MT8"> </text:span>'
        r'<text:span text:style-name="MT9">DEZ</text:span>'
        r"</text:p>"
    )
    replacement = (
        '<text:p text:style-name="MP8">'
        '<text:span text:style-name="MT14">[SISGES_SEMESTRE_TEXTO] PERÍODO: </text:span>'
        '<text:span text:style-name="MT12">[SISGES_PERIODO]</text:span>'
        "</text:p>"
    )
    return pattern.sub(replacement, styles_xml, count=1)


def replace_continuation_period(styles_xml: str) -> str:
    pattern = re.compile(
        r'<text:p text:style-name="MP6">'
        r'<text:span text:style-name="MT5">2</text:span>'
        r'<text:span text:style-name="MT6">º SEMESTRE DE 202</text:span>'
        r'<text:span text:style-name="MT5">5</text:span>'
        r'<text:span text:style-name="MT7"> </text:span>'
        r'<text:span text:style-name="MT6">PERÍODO:</text:span>'
        r'<text:span text:style-name="MT7"> </text:span>'
        r'<text:span text:style-name="MT8">1º </text:span>'
        r'<text:span text:style-name="MT9">JUL</text:span>'
        r'<text:span text:style-name="MT8"> A </text:span>'
        r'<text:span text:style-name="MT10">3</text:span>'
        r'<text:span text:style-name="MT9">1</text:span>'
        r'<text:span text:style-name="MT8"> </text:span>'
        r'<text:span text:style-name="MT9">DEZ</text:span>'
        r"</text:p>"
    )
    replacement = (
        '<text:p text:style-name="MP6">'
        '<text:span text:style-name="MT6">[SISGES_SEMESTRE_TEXTO] PERÍODO: </text:span>'
        '<text:span text:style-name="MT8">[SISGES_PERIODO]</text:span>'
        "</text:p>"
    )
    return pattern.sub(replacement, styles_xml, count=1)


def rebuild_styles_xml(styles_xml: str) -> str:
    styles_xml = styles_xml.replace("ARMA/QUARO/SERVIÇO:", "ARMA/QUADRO/SERVIÇO:")
    styles_xml = styles_xml.replace(
        '<text:span text:style-name="MT4">SUBTENENTE</text:span>',
        '<text:span text:style-name="MT4">[SISGES_POSTO_GRADUACAO_CONTINUACAO]</text:span>',
    )
    styles_xml = replace_continuation_period(styles_xml)
    styles_xml = replace_first_page_period(styles_xml)
    return styles_xml


def rebuild_content_xml(content_xml: str) -> str:
    content_xml = re.sub(
        r'<text:p(?:\s+[^>]*)?>Quartel-General do Exército.*?</text:p>',
        '<text:p text:style-name="P23">[SISGES_DATA_LOCAL]</text:p>',
        content_xml,
        count=1,
        flags=re.S,
    )
    return content_xml


def validate_xml(name: str, value: bytes | str, errors: list[str], checks: list[str]) -> None:
    try:
        if isinstance(value, str):
            value = value.encode("utf-8")
        ET.fromstring(value)
        checks.append(f"OK_XML_PARSEABLE:{name}")
    except Exception as exc:
        errors.append(f"ERR_XML_INVALID:{name}:{exc}")


def build_contract(content_xml: str, styles_xml: str) -> dict:
    flags_content = sorted(set(FLAG_RE.findall(content_xml)))
    flags_styles = sorted(set(FLAG_RE.findall(styles_xml)))
    return {
        "schema_version": "sisges-folha-template-contract-v1",
        "template_role": "FOLHA_ALTERACOES_EXECUTAVEL",
        "rendering_scope": "HEADER_PARTE1_COMPORTAMENTO_ASSINATURA",
        "parte2_status": "MANTIDA_COMO_ESTRUTURA_BASE_SEM_PARAMETRIZACAO_TOTAL",
        "flags": {
            "content_xml": flags_content,
            "styles_xml": flags_styles,
            "all": sorted(set(flags_content + flags_styles)),
        },
        "renderer_requirements": [
            "Substituir content.xml e styles.xml.",
            "Substituir [SISGES_PARTE_1] por paragrafos ODT da 1a Parte.",
            "Substituir cabecalho em styles.xml antes de validar placeholders.",
            "Validar que nenhum [SISGES_*] sobrou no ODT final.",
            "Nao recalcular 2a Parte neste modelo ate o modulo de tempo preencher os campos.",
        ],
        "formatting_contract": {
            "page": "A4 retrato com borda externa preservada",
            "font": "Calibri Light 12 pt",
            "first_part": {
                "title": "1a PARTE sublinhada",
                "months": "meses sublinhados",
                "body": "texto justificado",
                "reference": "referencia de BI em linha propria",
            },
            "signature": "centralizada",
        },
    }


def write_report(result: TemplateBuildResult) -> None:
    lines = [
        "RELATORIO SISGES - MODELO EXECUTAVEL DE FOLHA DE ALTERACOES",
        f"Gerado em: {result.generated_at}",
        "",
        f"Status: {result.status}",
        f"Origem: {result.source_odt}",
        f"Saida ODT: {result.output_odt}",
        f"Contrato JSON: {result.contract_json}",
        "",
        "Flags em content.xml:",
        *[f"- {flag}" for flag in result.flags_content_xml],
        "",
        "Flags em styles.xml/header:",
        *[f"- {flag}" for flag in result.flags_styles_xml],
        "",
        "Checks:",
        *[f"- {check}" for check in result.structural_checks],
        "",
        "Warnings:",
        *[f"- {warning}" for warning in result.warnings],
        "",
        "Erros:",
        *[f"- {error}" for error in result.errors],
        "",
        "Uso operacional:",
        "- Este modelo nao deve ser preenchido por adivinhacao.",
        "- content.xml recebe a 1a Parte, comportamento, data/local e assinatura.",
        "- styles.xml recebe cabecalho e periodo.",
        "- A 2a Parte fica como estrutura base ate a etapa especifica de tempo.",
        "- Qualquer placeholder [SISGES_*] restante no ODT final deve bloquear entrega.",
    ]
    Path(result.report_txt).write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_template(source_odt: Path, output_odt: Path, contract_json: Path, report_txt: Path) -> TemplateBuildResult:
    output_odt.parent.mkdir(parents=True, exist_ok=True)
    contract_json.parent.mkdir(parents=True, exist_ok=True)
    report_txt.parent.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []

    with zipfile.ZipFile(source_odt, "r") as zin:
        entries = {info.filename: zin.read(info.filename) for info in zin.infolist() if not info.is_dir()}
        infos = {info.filename: info for info in zin.infolist() if not info.is_dir()}

    if "content.xml" not in entries or "styles.xml" not in entries:
        errors.append("ERR_TEMPLATE_XML_MISSING")
        content_xml = ""
        styles_xml = ""
    else:
        content_xml = rebuild_content_xml(entries["content.xml"].decode("utf-8"))
        styles_xml = rebuild_styles_xml(entries["styles.xml"].decode("utf-8"))
        entries["content.xml"] = content_xml.encode("utf-8")
        entries["styles.xml"] = styles_xml.encode("utf-8")
        validate_xml("content.xml", content_xml, errors, checks)
        validate_xml("styles.xml", styles_xml, errors, checks)

    contract = build_contract(content_xml, styles_xml)
    flags_content = contract["flags"]["content_xml"]
    flags_styles = contract["flags"]["styles_xml"]
    required = {
        "[SISGES_NOME]",
        "[SISGES_GRADUACAO]",
        "[SISGES_QMS]",
        "[SISGES_IDENTIDADE]",
        "[SISGES_SEMESTRE_TEXTO]",
        "[SISGES_PERIODO]",
        "[SISGES_PARTE_1]",
        "[SISGES_COMPORTAMENTO]",
        "[SISGES_DATA_LOCAL]",
        "[SISGES_ASSINATURA_NOME]",
        "[SISGES_ASSINATURA_FUNCAO]",
    }
    missing = sorted(required - set(contract["flags"]["all"]))
    if missing:
        errors.extend(f"ERR_REQUIRED_FLAG_MISSING:{flag}" for flag in missing)
    else:
        checks.append("OK_REQUIRED_FLAGS_PRESENT")
    if "[SISGES_POSTO_GRADUACAO_CONTINUACAO]" in contract["flags"]["all"]:
        checks.append("OK_CONTINUATION_HEADER_PARAMETRIZED")
    else:
        warnings.append("WARN_CONTINUATION_HEADER_NOT_PARAMETRIZED")
    if "ARMA/QUARO" not in styles_xml:
        checks.append("OK_HEADER_LABEL_ARMA_QUADRO_FIXED")
    else:
        errors.append("ERR_HEADER_LABEL_ARMA_QUADRO_NOT_FIXED")

    with zipfile.ZipFile(output_odt, "w") as zout:
        if "mimetype" in entries:
            zout.writestr("mimetype", entries.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
        for filename, data in entries.items():
            info = infos.get(filename)
            if info:
                zout.writestr(info, data)
            else:
                zout.writestr(filename, data, compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(output_odt, "r") as zout:
        bad = zout.testzip()
    if bad:
        errors.append(f"ERR_ODT_ZIP_CORRUPTED:{bad}")
    else:
        checks.append("OK_ODT_ZIP_VALID")

    contract_json.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
    result = TemplateBuildResult(
        status="ERROR" if errors else "OK_WITH_WARNINGS" if warnings else "OK",
        generated_at=now_iso(),
        source_odt=str(source_odt),
        output_odt=str(output_odt),
        contract_json=str(contract_json),
        report_txt=str(report_txt),
        flags_content_xml=flags_content,
        flags_styles_xml=flags_styles,
        structural_checks=checks,
        warnings=warnings,
        errors=errors,
    )
    write_report(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera modelo ODT executavel SISGES para Folha.")
    parser.add_argument("--source", required=True, help="ODT base.")
    parser.add_argument("--output", required=True, help="ODT executavel gerado.")
    parser.add_argument("--contract", required=True, help="JSON de contrato.")
    parser.add_argument("--report", required=True, help="Relatorio TXT.")
    args = parser.parse_args()

    result = build_template(
        source_odt=Path(args.source),
        output_odt=Path(args.output),
        contract_json=Path(args.contract),
        report_txt=Path(args.report),
    )
    print("MODELO EXECUTAVEL GERADO")
    print(f"Status: {result.status}")
    print(f"ODT: {result.output_odt}")
    print(f"Contrato: {result.contract_json}")
    print(f"Relatorio: {result.report_txt}")
    print(f"Erros: {len(result.errors)}")


if __name__ == "__main__":
    main()
