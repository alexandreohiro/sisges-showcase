"""Parametriza um modelo ODT de Folha de Alteracoes de usuario com flags SISGES.

Converte um modelo VISUAL_REFERENCE_ONLY (texto estatico) em template
EXECUTABLE_TEMPLATE, preservando o layout:

- headers (styles.xml): semestre/periodo/posto de continuacao viram flags
  (inject_continuation_header_flags) e os rotulos NOME/GRADUACAO/
  ARMA-QUADRO-SERVICO/IDENTIDADE ganham os flags de valor;
- corpo (content.xml): insere [SISGES_PARTE_1] apos "1a PARTE" e
  [SISGES_COMPORTAMENTO] antes de "2a PARTE"; troca a assinatura estatica
  pelos flags; troca a data/local por [SISGES_DATA_LOCAL];
- 2a Parte: corrige a ordem dos titulos 3/4 para o Art. 24 da
  Port. 063-DGP/2020 (III-TSSD, IV-TSCMM) e troca as celulas de valor
  pelos flags de tempo ([SISGES_TC] ... [SISGES_TTES]).

Uso:
    python scripts/parametrizar_modelo_folha.py --source MODELO.odt --output MODELO_EXECUTAVEL.odt
"""

from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape, unescape

from modules.compilador.application.odt_template_policy import (
    REQUIRED_SISGES_FLAGS,
    classify_odt_template,
    inject_continuation_header_flags,
)

# (?<!/) exclui tags auto-fechadas (<text:p/>): sem isso o "conteudo" do
# paragrafo vazio engoliria o paragrafo seguinte e quebraria o XML.
PARAGRAPH_PATTERN = re.compile(r"(<text:p\b[^>]*(?<!/)>)(.*?)(</text:p>)", re.S)
CELL_PATTERN = re.compile(r"(<table:table-cell\b[^>]*(?<!/)>)(.*?)(</table:table-cell>)", re.S)

# Ordem dos flags de valor na 2a Parte APOS a correcao da ordem do Art. 24.
VALUE_FLAG_SEQUENCE = [
    "[SISGES_TC]",
    "[SISGES_TC_ARREG]",
    "[SISGES_TC_NAO_ARREG]",
    "[SISGES_TNC]",
    "[SISGES_TSSD]",
    "[SISGES_TSCMM]",
    "[SISGES_TSNR]",
    "[SISGES_TTES]",
]

LABEL_FIXES = [
    # Art. 24: III-TSSD antes de IV-TSCMM (modelos antigos invertem).
    (
        "TEMPO DE SERVIÇO COMPUTÁVEL PARA MEDALHA MILITAR",
        "TEMPO DE SERVIÇO EM SITUAÇÕES DIVERSAS (TSSD)",
    ),
    (
        "4. TEMPO DE SERVIÇO EM SITUAÇÕES DIVERSAS (TSSD)",
        "4. TEMPO DE SERVIÇO COMPUTADO PARA MEDALHA MILITAR (TSCMM)",
    ),
]

HEADER_LABEL_FLAGS = [
    (re.compile(r"^NOME:\s*$"), "NOME: [SISGES_NOME]"),
    (re.compile(r"^GRADUAÇÃO:.*$"), "GRADUAÇÃO: [SISGES_GRADUACAO]"),
    (re.compile(r"^ARMA/QUADRO/SERVIÇO:\s*$"), "ARMA/QUADRO/SERVIÇO: [SISGES_QMS]"),
    (re.compile(r"^IDENTIDADE:\s*$"), "IDENTIDADE: [SISGES_IDENTIDADE]"),
]


def plain(inner_xml: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", inner_xml))


def rewrite_paragraph(match: re.Match, new_text: str) -> str:
    return match.group(1) + escape(new_text) + match.group(3)


def parametrizar_styles(styles_xml: str) -> tuple[str, list[str]]:
    styles_xml = styles_xml.replace("ARMA/QUARO/SERVIÇO:", "ARMA/QUADRO/SERVIÇO:")
    styles_xml, validations = inject_continuation_header_flags(styles_xml)
    validations = list(validations)

    def visit(match: re.Match) -> str:
        text = plain(match.group(2)).strip()
        for pattern, replacement in HEADER_LABEL_FLAGS:
            if pattern.match(text) and "[SISGES_" not in text:
                validations.append(f"OK_HEADER_LABEL_FLAG:{replacement}")
                return rewrite_paragraph(match, replacement)
        return match.group(0)

    return PARAGRAPH_PATTERN.sub(visit, styles_xml), validations


def parametrizar_content(content_xml: str) -> tuple[str, list[str]]:
    validations: list[str] = []

    # 1) Ordem do Art. 24 nos rotulos da 2a Parte (preserva lideres pontilhados).
    for old, new in LABEL_FIXES:
        if old in content_xml:
            content_xml = content_xml.replace(old, new, 1)
            validations.append(f"OK_ORDEM_ART24:{new[:40]}")

    # 2) Celulas de valor da 2a Parte -> flags de tempo, em ordem posicional.
    flag_iter = iter(VALUE_FLAG_SEQUENCE)

    def visit_cell(match: re.Match) -> str:
        # Aceita celulas com lideres pontilhados antes do valor
        # (ex.: "………...00a00m00d") e troca apenas o paragrafo do valor.
        if not plain(match.group(2)).strip().endswith("00a00m00d"):
            return match.group(0)
        try:
            flag = next(flag_iter)
        except StopIteration:
            return match.group(0)

        def replace_value_paragraph(pm: re.Match) -> str:
            if "00a00m00d" not in plain(pm.group(2)):
                return pm.group(0)
            new_text = plain(pm.group(2)).replace("00a00m00d", flag)
            return pm.group(1) + escape(new_text) + pm.group(3)

        inner = PARAGRAPH_PATTERN.sub(replace_value_paragraph, match.group(2))
        validations.append(f"OK_VALOR_FLAG:{flag}")
        return match.group(1) + inner + match.group(3)

    content_xml = CELL_PATTERN.sub(visit_cell, content_xml)

    # 3) Assinatura, data/local, 1a parte e comportamento.
    def visit_paragraph(match: re.Match) -> str:
        text = plain(match.group(2)).strip()
        if "[SISGES_" in text:
            return match.group(0)
        if text.startswith("Quartel-General do Exército"):
            validations.append("OK_FLAG:[SISGES_DATA_LOCAL]")
            return rewrite_paragraph(match, "[SISGES_DATA_LOCAL]")
        if re.match(r"^S Cmt B Adm QGEx$|^Cmt B Adm QGEx$", text):
            validations.append("OK_FLAG:[SISGES_ASSINATURA_FUNCAO]")
            return rewrite_paragraph(match, "[SISGES_ASSINATURA_FUNCAO]")
        if re.match(r"^[A-ZÀ-Ü][A-ZÀ-Ü ]+ – Cel$", text):
            validations.append("OK_FLAG:[SISGES_ASSINATURA_NOME]")
            return rewrite_paragraph(match, "[SISGES_ASSINATURA_NOME]")
        return match.group(0)

    content_xml = PARAGRAPH_PATTERN.sub(visit_paragraph, content_xml)

    # 4) [SISGES_PARTE_1] apos "1a PARTE" e [SISGES_COMPORTAMENTO] antes de "2a PARTE".
    def insert_after(xml: str, anchor_text: str, insert_xml: str) -> str:
        for match in PARAGRAPH_PATTERN.finditer(xml):
            if plain(match.group(2)).strip() == anchor_text:
                return xml[: match.end()] + insert_xml + xml[match.end() :]
        return xml

    def insert_before(xml: str, anchor_text: str, insert_xml: str) -> str:
        for match in PARAGRAPH_PATTERN.finditer(xml):
            if plain(match.group(2)).strip() == anchor_text:
                return xml[: match.start()] + insert_xml + xml[match.start() :]
        return xml

    if "[SISGES_PARTE_1]" not in content_xml:
        content_xml = insert_after(
            content_xml, "1ª PARTE", '<text:p text:style-name="Standard">[SISGES_PARTE_1]</text:p>'
        )
        validations.append("OK_FLAG:[SISGES_PARTE_1]")
    if "[SISGES_COMPORTAMENTO]" not in content_xml:
        content_xml = insert_before(
            content_xml,
            "2ª PARTE",
            '<text:p text:style-name="Standard">[SISGES_COMPORTAMENTO]</text:p>',
        )
        validations.append("OK_FLAG:[SISGES_COMPORTAMENTO]")

    return content_xml, validations


def parametrizar_modelo(source: Path, output: Path) -> list[str]:
    with zipfile.ZipFile(source, "r") as zin:
        entries = {info.filename: zin.read(info.filename) for info in zin.infolist() if not info.is_dir()}

    content_xml = entries["content.xml"].decode("utf-8")
    styles_xml = entries.get("styles.xml", b"").decode("utf-8")

    styles_xml, style_validations = parametrizar_styles(styles_xml)
    content_xml, content_validations = parametrizar_content(content_xml)

    entries["content.xml"] = content_xml.encode("utf-8")
    if "styles.xml" in entries:
        entries["styles.xml"] = styles_xml.encode("utf-8")

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as zout:
        if "mimetype" in entries:
            zout.writestr("mimetype", entries.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
        for filename, data in entries.items():
            zout.writestr(filename, data, compress_type=zipfile.ZIP_DEFLATED)

    validations = [*style_validations, *content_validations]
    classification = classify_odt_template(output)
    validations.append(f"CLASSIFICACAO:{classification.classification}")
    combined = content_xml + styles_xml
    for flag in REQUIRED_SISGES_FLAGS:
        if flag not in combined:
            validations.append(f"ERR_FLAG_AUSENTE:{flag}")
    return validations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    validations = parametrizar_modelo(Path(args.source), Path(args.output))
    for item in validations:
        print(item)


if __name__ == "__main__":
    main()
