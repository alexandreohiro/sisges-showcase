"""Testes do fluxo de parametrizacao de modelos ODT de usuario."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from modules.compilador.application.odt_template_policy import (
    EXECUTABLE_TEMPLATE,
    classify_odt_template,
)
from scripts.parametrizar_modelo_folha import VALUE_FLAG_SEQUENCE, parametrizar_modelo


def _write_modelo_usuario(path: Path, *, valores: int = 8) -> Path:
    """ODT minimo com a MESMA anatomia dos modelos de usuario: headers
    estaticos nos master pages, 2a Parte na ordem ANTIGA (TSCMM antes de
    TSSD) e celulas de valor 00a00m00d (uma com lider pontilhado)."""
    cells = []
    for index in range(valores):
        prefix = "………...00a00m00d" if index == 1 else "00a00m00d"
        cells.append(
            '<table:table-row><table:table-cell office:value-type="string">'
            f'<text:p text:style-name="P1">{prefix}</text:p>'
            "</table:table-cell></table:table-row>"
        )
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-content'
        ' xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'
        ' xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"'
        ' xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"'
        ' office:version="1.2"><office:body><office:text>'
        "<text:p>1ª PARTE</text:p>"
        "<text:p>2ª PARTE</text:p>"
        "<text:p>1. TEMPO COMPUTADO DE EFETIVO SERVIÇO (TC) ……</text:p>"
        "<text:p>a) Arregimentado ……</text:p>"
        "<text:p>b) Não arregimentado ……</text:p>"
        "<text:p>2. TEMPO NÃO COMPUTADO (TNC) ……</text:p>"
        "<text:p>3. TEMPO DE SERVIÇO COMPUTÁVEL PARA MEDALHA MILITAR ……</text:p>"
        "<text:p>4. TEMPO DE SERVIÇO EM SITUAÇÕES DIVERSAS (TSSD) ……</text:p>"
        "<text:p>5. TEMPO DE SERVIÇO NACIONAL RELEVANTE (TSNR) ……</text:p>"
        "<text:p>6. TEMPO TOTAL DE EFETIVO SERVIÇO (TTES) ……</text:p>"
        f'<table:table table:name="Valores">{"".join(cells)}</table:table>'
        "<text:p>Quartel-General do Exército – Brasília/DF, 1º de janeiro de 2026</text:p>"
        "<text:p>FULANO DE TAL – Cel</text:p>"
        "<text:p>S Cmt B Adm QGEx</text:p>"
        "</office:text></office:body></office:document-content>"
    )
    styles = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-styles'
        ' xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'
        ' xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"'
        ' xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"'
        ' office:version="1.2"><office:master-styles>'
        '<style:master-page style:name="Primeira"><style:header>'
        "<text:p>NOME: </text:p>"
        "<text:p>GRADUAÇÃO: <text:span>SUBTENENTE</text:span></text:p>"
        "<text:p>ARMA/QUARO/SERVIÇO: </text:p>"
        "<text:p>IDENTIDADE: </text:p>"
        "<text:p>2º SEMESTRE DE 2025 PERÍODO: 1º JUL A 31 DEZ</text:p>"
        "</style:header></style:master-page>"
        '<style:master-page style:name="Continuacao"><style:header>'
        '<text:p text:style-name="MP1"/>'
        "<text:p>Continuação das Folhas de Alterações do SUBTENENTE</text:p>"
        "<text:p>2º SEMESTRE DE 2025 PERÍODO: 1º JUL A 31 DEZ</text:p>"
        "</style:header></style:master-page>"
        "</office:master-styles></office:document-styles>"
    )
    with zipfile.ZipFile(path, "w") as zout:
        zout.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        zout.writestr("content.xml", content)
        zout.writestr("styles.xml", styles)
        zout.writestr("META-INF/manifest.xml", "<manifest:manifest xmlns:manifest=\"urn:oasis:names:tc:opendocument:xmlns:manifest:1.0\"/>")
    return path


def test_parametrizacao_gera_template_executavel_na_ordem_do_art24(tmp_path):
    source = _write_modelo_usuario(tmp_path / "modelo.odt")
    output = tmp_path / "modelo_executavel.odt"

    validations = parametrizar_modelo(source, output)

    assert f"CLASSIFICACAO:{EXECUTABLE_TEMPLATE}" in validations
    assert not any(item.startswith("ERR_") for item in validations)
    assert classify_odt_template(output).classification == EXECUTABLE_TEMPLATE

    with zipfile.ZipFile(output) as zout:
        content = zout.read("content.xml").decode("utf-8")
        styles = zout.read("styles.xml").decode("utf-8")
    ET.fromstring(content.encode("utf-8"))
    ET.fromstring(styles.encode("utf-8"))

    # Rotulos na ordem do Art. 24 (TSSD 3o, TSCMM 4o)
    plain = re.sub(r"<[^>]+>", "\n", content)
    pos_tssd = plain.index("3. TEMPO DE SERVIÇO EM SITUAÇÕES DIVERSAS (TSSD)")
    pos_tscmm = plain.index("4. TEMPO DE SERVIÇO COMPUTADO PARA MEDALHA MILITAR (TSCMM)")
    assert pos_tssd < pos_tscmm

    # Flags de valor na sequencia posicional esperada, sem sobras
    positions = [content.index(flag) for flag in VALUE_FLAG_SEQUENCE]
    assert positions == sorted(positions)
    assert "00a00m00d" not in re.sub(r"<[^>]+>", "", content)

    # Headers parametrizados
    for flag in ("[SISGES_NOME]", "[SISGES_GRADUACAO]", "[SISGES_QMS]",
                 "[SISGES_IDENTIDADE]", "[SISGES_SEMESTRE_TEXTO]",
                 "[SISGES_POSTO_GRADUACAO_CONTINUACAO]"):
        assert flag in styles
    assert "ARMA/QUADRO/SERVIÇO" in styles  # typo QUARO corrigido


def test_parametrizacao_denuncia_layout_divergente(tmp_path):
    """Celula de valor extra nao pode desalinhar flags silenciosamente."""
    source = _write_modelo_usuario(tmp_path / "modelo.odt", valores=9)
    output = tmp_path / "modelo_executavel.odt"

    validations = parametrizar_modelo(source, output)

    assert any(item.startswith("ERR_VALOR_CELULAS_RESTANTES") for item in validations)
