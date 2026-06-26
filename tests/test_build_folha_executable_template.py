from __future__ import annotations

import zipfile
from pathlib import Path

from scripts.build_folha_executable_template import build_template


def write_template_fixture(path: Path) -> None:
    content = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.2">
  <office:body><office:text>
    <text:p>1ª PARTE</text:p>
    <text:p>[SISGES_PARTE_1]</text:p>
    <text:p>[SISGES_COMPORTAMENTO]</text:p>
    <text:p>2ª PARTE</text:p>
    <text:p>Quartel-General do Exército – Brasília/DF, 1° de janeiro de 2026</text:p>
    <text:p>[SISGES_ASSINATURA_NOME]</text:p>
    <text:p>[SISGES_ASSINATURA_FUNCAO]</text:p>
  </office:text></office:body>
</office:document-content>
"""
    styles = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.2">
  <office:master-styles>
    <text:p text:style-name="MP5">Continuação das Folhas de Alterações do <text:span text:style-name="MT4">SUBTENENTE</text:span></text:p>
    <text:p text:style-name="MP6"><text:span text:style-name="MT5">2</text:span><text:span text:style-name="MT6">º SEMESTRE DE 202</text:span><text:span text:style-name="MT5">5</text:span><text:span text:style-name="MT7"> </text:span><text:span text:style-name="MT6">PERÍODO:</text:span><text:span text:style-name="MT7"> </text:span><text:span text:style-name="MT8">1º </text:span><text:span text:style-name="MT9">JUL</text:span><text:span text:style-name="MT8"> A </text:span><text:span text:style-name="MT10">3</text:span><text:span text:style-name="MT9">1</text:span><text:span text:style-name="MT8"> </text:span><text:span text:style-name="MT9">DEZ</text:span></text:p>
    <text:p><text:span text:style-name="MT11">NOME:</text:span><text:span text:style-name="MT12"> [SISGES_NOME]</text:span></text:p>
    <text:p><text:span text:style-name="MT11">GRADUAÇÃO:</text:span><text:span text:style-name="MT12"> [SISGES_GRADUACAO]</text:span></text:p>
    <text:p><text:span text:style-name="MT11">ARMA/QUARO/SERVIÇO:</text:span><text:span text:style-name="MT12"> [SISGES_QMS]</text:span></text:p>
    <text:p><text:span text:style-name="MT11">IDENTIDADE:</text:span><text:span text:style-name="MT12"> [SISGES_IDENTIDADE]</text:span></text:p>
    <text:p text:style-name="MP8"><text:span text:style-name="MT13">2</text:span><text:span text:style-name="MT14">º SEMESTRE DE 202</text:span><text:span text:style-name="MT13">5</text:span><text:span text:style-name="MT14"> PERÍODO:</text:span><text:span text:style-name="MT7"> </text:span><text:span text:style-name="MT8">1º </text:span><text:span text:style-name="MT9">JUL</text:span><text:span text:style-name="MT8"> A </text:span><text:span text:style-name="MT10">3</text:span><text:span text:style-name="MT9">1</text:span><text:span text:style-name="MT8"> </text:span><text:span text:style-name="MT9">DEZ</text:span></text:p>
  </office:master-styles>
</office:document-styles>
"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.text", compress_type=zipfile.ZIP_STORED)
        archive.writestr("content.xml", content)
        archive.writestr("styles.xml", styles)
        archive.writestr("META-INF/manifest.xml", "")


def test_build_template_parametrizes_header_and_date(tmp_path: Path) -> None:
    source = tmp_path / "modelo.odt"
    output = tmp_path / "modelo_executavel.odt"
    contract = tmp_path / "contract.json"
    report = tmp_path / "report.txt"
    write_template_fixture(source)

    result = build_template(source, output, contract, report)

    assert result.status == "OK"
    assert output.exists()
    assert contract.exists()
    assert report.exists()
    with zipfile.ZipFile(output, "r") as archive:
        content = archive.read("content.xml").decode("utf-8")
        styles = archive.read("styles.xml").decode("utf-8")
    assert "[SISGES_DATA_LOCAL]" in content
    assert "[SISGES_PERIODO]" in styles
    assert "[SISGES_SEMESTRE_TEXTO]" in styles
    assert "[SISGES_POSTO_GRADUACAO_CONTINUACAO]" in styles
    assert "ARMA/QUARO" not in styles
    assert "ARMA/QUADRO/SERVIÇO" in styles
