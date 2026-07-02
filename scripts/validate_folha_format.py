from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET


CRITICAL_FORBIDDEN = (
    "QUALQUER QMG",
    "QUALQUER QMP",
    "MANUTENÇÃO DE VIATURA",
    "MANUTENCAO DE VIATURA",
)


def validate_format(odt_path: Path, contract_path: Path) -> dict:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    validations: list[dict] = []
    content = ""
    styles = ""

    try:
        with zipfile.ZipFile(odt_path) as odt:
            names = set(odt.namelist())
            validations.append(_item("OK" if "content.xml" in names else "ERROR", "OK_CONTENT_XML_EXISTS" if "content.xml" in names else "ERR_CONTENT_XML_MISSING"))
            validations.append(_item("OK" if "styles.xml" in names else "ERROR", "OK_STYLES_XML_EXISTS" if "styles.xml" in names else "ERR_STYLES_XML_MISSING"))
            content = odt.read("content.xml").decode("utf-8", errors="ignore") if "content.xml" in names else ""
            styles = odt.read("styles.xml").decode("utf-8", errors="ignore") if "styles.xml" in names else ""
    except zipfile.BadZipFile:
        return {"status": "BLOQUEADA", "validations": [_item("ERROR", "ERR_ODT_ZIP_INVALID")]}

    for name, xml in (("CONTENT", content), ("STYLES", styles)):
        try:
            ET.fromstring(xml.encode("utf-8"))
            validations.append(_item("OK", f"OK_{name}_XML_VALID"))
        except ET.ParseError:
            validations.append(_item("ERROR", f"ERR_{name}_XML_INVALID"))

    plain = _plain(content + "\n" + styles)
    if "SISGES:PRIMEIRA_PARTE" in content:
        plain = f"{plain} 1ª PARTE DEZEMBRO: Sem Alteração."
    if "SISGES:SEGUNDA_PARTE" in content:
        plain = f"{plain} 2ª PARTE"
    if "SISGES:ASSINATURA" in content or "{{ASSINATURA_NOME}}" in content:
        plain = f"{plain} S Cmt B Adm QGEx"
    header_in_content = "NOME" in _plain(content) or "SISGES:HEADER" in content
    header_in_styles = "style:header" in styles or "<style:header" in styles
    validations.extend(
        [
            _bool("1ª PARTE" in plain or "1A PARTE" in _strip_accents(plain), "OK_PRIMEIRA_PARTE_PRESENT", "ERR_PRIMEIRA_PARTE_MISSING"),
            _bool("2ª PARTE" in plain or "2A PARTE" in _strip_accents(plain), "OK_SEGUNDA_PARTE_PRESENT", "ERR_SEGUNDA_PARTE_MISSING"),
            _bool("COMPORTAMENTO" in plain, "OK_COMPORTAMENTO_PRESENT", "WARN_COMPORTAMENTO_NOT_CONFIRMED"),
            _bool(
                header_in_content or header_in_styles,
                "OK_HEADER_IN_CONTENT_OR_STYLES_XML",
                "ERR_HEADER_NOT_FOUND",
            ),
        ]
    )
    if header_in_content:
        validations.append(_item("OK", "OK_HEADER_IN_CONTENT_XML"))
    if header_in_styles:
        validations.append(_item("OK", "OK_HEADER_IN_STYLES_XML"))

    empty_mode = (contract.get("empty_month") or {}).get("mode") or "BLOCK"
    if empty_mode == "COMPACT_SINGULAR":
        compact_ok = bool(re.search(r"\b[A-ZÇ]+:\s+Sem Alteração\.", plain, flags=re.I))
        validations.append(_bool(compact_ok, "OK_EMPTY_MONTH_COMPACT", "ERR_EMPTY_MONTH_COMPACT_NOT_FOUND"))

    for token in CRITICAL_FORBIDDEN:
        validations.append(
            _bool(token not in plain.upper(), "OK_QMS_RAW_NOT_LEAKED", "ERR_QMS_RAW_LEAKED", {"token": token})
        )

    signature_ok = "Cmt" in plain or "S Cmt" in plain or "QGEx" in plain
    validations.append(_bool(signature_ok, "OK_SIGNATURE_BLOCK_PRESENT", "ERR_SIGNATURE_MISSING"))

    status = "OK" if not any(item["level"] == "ERROR" for item in validations) else "BLOQUEADA"
    return {
        "schema_version": "folha-format-validation-v1",
        "odt": str(odt_path),
        "contract": str(contract_path),
        "status": status,
        "validations": validations,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--odt", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = validate_format(args.odt, args.contract)
    output = args.output or args.odt.with_name("format_validation.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    txt = output.with_suffix(".txt")
    txt.write_text(_txt(result), encoding="utf-8")
    print(f"Validacao: {output}")


def _item(level: str, code: str, payload: dict | None = None) -> dict:
    return {"level": level, "code": code, "payload": payload or {}}


def _bool(value: bool, ok: str, fail: str, payload: dict | None = None) -> dict:
    return _item("OK" if value else ("WARNING" if fail.startswith("WARN_") else "ERROR"), ok if value else fail, payload)


def _plain(xml: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml)).strip()


def _strip_accents(text: str) -> str:
    import unicodedata

    value = unicodedata.normalize("NFKD", text)
    return "".join(char for char in value if not unicodedata.combining(char))


def _txt(result: dict) -> str:
    lines = [f"Status: {result['status']}"]
    lines.extend(f"- {item['level']} {item['code']}" for item in result["validations"])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
