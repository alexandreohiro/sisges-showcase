from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

from modules.compilador.application.folha_format_contract import (
    EMPTY_MONTH_COMPACT_SINGULAR,
)


def extract_contract(odt_path: Path) -> dict:
    warnings: list[str] = []
    with zipfile.ZipFile(odt_path) as odt:
        names = set(odt.namelist())
        content = _read_text(odt, "content.xml", warnings)
        styles = _read_text(odt, "styles.xml", warnings)
        meta_present = "meta.xml" in names
        manifest_present = "META-INF/manifest.xml" in names

    used_styles = sorted(set(re.findall(r'text:style-name="([^"]+)"|style:name="([^"]+)"', content + styles)))
    used_styles = sorted({item for pair in used_styles for item in pair if item})
    main_font = _extract_first(r'style:font-name="([^"]+)"', styles) or "Calibri Light"
    main_size = _extract_first(r'fo:font-size="([^"]+)"', styles) or "12pt"
    plain = _plain(content + "\n" + styles)

    empty_month_mode = "BLOCK"
    if re.search(r"\bDEZEMBRO:\s+Sem Alteração\.", plain, flags=re.I):
        empty_month_mode = EMPTY_MONTH_COMPACT_SINGULAR

    return {
        "schema_version": "folha-format-contract-v1",
        "source": "ALPHA_ODT_REFERENCE",
        "odt": {
            "content_xml": "content.xml" in names,
            "styles_xml": "styles.xml" in names,
            "meta_xml": meta_present,
            "manifest_xml": manifest_present,
            "styles_used": used_styles,
        },
        "page": {
            "page_layouts": sorted(set(re.findall(r'style:page-layout-name="([^"]+)"', styles))),
            "master_pages": sorted(set(re.findall(r'<style:master-page[^>]+style:name="([^"]+)"', styles))),
            "margins_detected": sorted(set(re.findall(r'fo:margin(?:-[a-z]+)?="([^"]+)"', styles))),
        },
        "fonts": {
            "main_family": main_font,
            "main_size": main_size,
            "bold_styles": sorted(set(re.findall(r'fo:font-weight="bold"[^>]*style:name="([^"]+)"', styles))),
            "underline_detected": "text-underline-style" in styles,
            "center_detected": "fo:text-align=\"center\"" in styles or "text-align=\"center\"" in content,
        },
        "headers": {
            "institutional_block_detected": any(
                token in plain
                for token in ("MINISTÉRIO DA DEFESA", "EXÉRCITO BRASILEIRO", "FOLHAS DE ALTERAÇÕES")
            ),
            "name_label": "NOME" in plain,
            "graduacao_label": "GRADUAÇÃO" in plain,
            "qms_label": "ARMA/QUADRO/SERVIÇO" in plain or "QAS/QMS" in plain,
            "identidade_label": "IDENTIDADE" in plain,
            "periodo_label": "PERÍODO" in plain,
            "header_may_be_in_styles": "style:header" in styles,
        },
        "primeira_parte": {
            "title_detected": "1ª PARTE" in plain or "1A PARTE" in _strip_accents(plain),
            "month_labels": _month_labels(plain),
            "blank_line_after_month": None,
        },
        "empty_month": {
            "mode": empty_month_mode,
            "accepted_text": "DEZEMBRO: Sem Alteração."
            if empty_month_mode == EMPTY_MONTH_COMPACT_SINGULAR
            else "DEZEMBRO:\nSem alterações.",
        },
        "event_format": {
            "title_bold_expected": True,
            "reference_bi_expected": True,
            "body_normal_expected": True,
            "spacing_between_events": "contractual_from_reference",
        },
        "tables": {
            "table_count": content.count("<table:table"),
            "policy": "FILTERED_TO_MILITAR_ALLOWED",
            "border_styles_detected": "style:table-cell-properties" in styles,
        },
        "comportamento": {
            "detected": "COMPORTAMENTO" in plain,
            "only_value_bold_expected": True,
            "position": "before_segunda_parte",
        },
        "segunda_parte": {
            "detected": "2ª PARTE" in plain or "2A PARTE" in _strip_accents(plain),
            "rubric_order": ["TC", "TNC", "TSCMM", "TSSD", "TSNR", "TTES"],
            "compact_time_format": bool(re.search(r"\d{2}a\d{2}m\d{2}d", plain)),
        },
        "signature": {
            "centralized_expected": True,
            "treated_as_variable": True,
            "fixed_name_from_reference": False,
        },
        "odt_styles": {
            "raw_style_count": len(used_styles),
            "styles_used": used_styles,
        },
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--odt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    contract = extract_contract(args.odt)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Contrato extraido: {args.output}")


def _read_text(odt: zipfile.ZipFile, name: str, warnings: list[str]) -> str:
    if name not in odt.namelist():
        warnings.append(f"WARN_{name.upper().replace('.', '_')}_AUSENTE")
        return ""
    data = odt.read(name)
    try:
        ET.fromstring(data)
    except ET.ParseError:
        warnings.append(f"WARN_{name.upper().replace('.', '_')}_XML_INVALIDO")
    return data.decode("utf-8", errors="ignore")


def _extract_first(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    return match.group(1) if match else ""


def _plain(xml: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml)).strip()


def _month_labels(text: str) -> list[str]:
    months = "JANEIRO FEVEREIRO MARÇO ABRIL MAIO JUNHO JULHO AGOSTO SETEMBRO OUTUBRO NOVEMBRO DEZEMBRO".split()
    return [month for month in months if re.search(rf"\b{month}:", text, flags=re.I)]


def _strip_accents(text: str) -> str:
    import unicodedata

    value = unicodedata.normalize("NFKD", text)
    return "".join(char for char in value if not unicodedata.combining(char))


if __name__ == "__main__":
    main()
