from __future__ import annotations

from pathlib import Path
import zipfile

from modules.compilador.application.folha_alteracoes_compiler import (
    CompilerOptions,
    EventBlock,
    SicapexProfile,
    TimeSummary,
    render_primeira_parte_odt,
    render_final_odt,
)
from modules.compilador.application.odt_template_policy import REQUIRED_SISGES_MARKERS


def test_template_odt_is_used_and_styles_preserved(tmp_path):
    template = tmp_path / "modelo.odt"
    output = tmp_path / "saida.odt"
    make_template(template, " ".join(REQUIRED_SISGES_MARKERS))

    result = render_final_odt(
        output_path=output,
        profile=profile(),
        events=[EventBlock(mes="JULHO", titulo="ALTERACAO", referencia="- a 1, BI Nº 1 :", corpo="Corpo.")],
        times=times(),
        period_label="2º SEMESTRE DE 2025",
        options=CompilerOptions(ano=2025, semestre="2"),
        template_odt_path=template,
    )

    assert result.template_used is True
    assert "OK_TEMPLATE_USED" in result.validations
    with zipfile.ZipFile(template) as zin, zipfile.ZipFile(output) as zout:
        assert zin.read("styles.xml") == zout.read("styles.xml")


def test_template_sisges_markers_are_replaced(tmp_path):
    template = tmp_path / "modelo.odt"
    output = tmp_path / "saida.odt"
    make_template(template, " ".join(REQUIRED_SISGES_MARKERS))

    result = render_final_odt(
        output_path=output,
        profile=profile(nome="MILITAR COMPLETO"),
        events=[],
        times=times(),
        period_label="2º SEMESTRE DE 2025",
        options=CompilerOptions(),
        template_odt_path=template,
    )

    assert result.template_used is True
    with zipfile.ZipFile(output) as zout:
        content = zout.read("content.xml").decode("utf-8")
    assert "MILITAR COMPLETO" in content
    assert "[[SISGES:" not in content


def test_template_sisges_flags_replace_content_and_styles(tmp_path):
    template = tmp_path / "modelo_flags.odt"
    output = tmp_path / "saida_flags.odt"
    make_flag_template(template)

    result = render_final_odt(
        output_path=output,
        profile=profile(nome="JOAO TESTE"),
        events=[EventBlock(mes="JULHO", titulo="ALTERACAO", referencia="- a 1, BI Nº 1:", corpo="Corpo.")],
        times=times(),
        period_label="2º SEMESTRE DE 2025",
        options=CompilerOptions(ano=2025, semestre="2"),
        template_odt_path=template,
    )

    assert result.template_used is True
    assert result.strategy == "sisges-flags"
    assert "OK_STYLES_PRESERVED" in result.validations
    assert "OK_HEADER_STYLES_RENDERED" in result.validations
    assert "ERR_STYLES_NOT_PRESERVED" not in result.validations
    with zipfile.ZipFile(output) as zout:
        content = zout.read("content.xml").decode("utf-8")
        styles = zout.read("styles.xml").decode("utf-8")
    assert "[SISGES_" not in content
    assert "[SISGES_" not in styles
    assert "JOAO TESTE" in styles
    assert "2º SEMESTRE DE 2025" in styles
    assert "1º JUL A 31 DEZ" in styles
    assert "ALTERACAO" in content
    assert "JULHO:" in content
    assert "SIGNATARIO PRACA" in content


def test_template_without_sisges_markers_is_visual_reference_fallback(tmp_path):
    template = tmp_path / "modelo.odt"
    output = tmp_path / "saida.odt"
    make_template(template, "SEM ANCORAS")

    result = render_final_odt(
        output_path=output,
        profile=profile(),
        events=[],
        times=times(),
        period_label="2º SEMESTRE DE 2025",
        options=CompilerOptions(),
        template_odt_path=template,
    )

    assert result.template_used is False
    assert "WARN_TEMPLATE_VISUAL_REFERENCE_ONLY" in result.validations
    assert output.exists()


def test_primeira_parte_odt_is_generated_with_formatted_months(tmp_path):
    output = tmp_path / "parte_1_alteracoes.odt"

    validations = render_primeira_parte_odt(
        output_path=output,
        events=[EventBlock(mes="JULHO", titulo="ALTERACAO", referencia="- a 1, BI Nº 1 :", corpo="Corpo.")],
        options=CompilerOptions(ano=2025, semestre="2"),
    )

    assert output.exists()
    assert "OK_PARTE1_ODT_GENERATED" in validations
    with zipfile.ZipFile(output) as zout:
        content = zout.read("content.xml").decode("utf-8")
    assert "1ª PARTE" in content
    assert "JULHO:" in content
    assert "ALTERACAO" in content
    assert "2ª PARTE" not in content


def make_template(path: Path, text: str) -> None:
    content = f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" office:version="1.2"><office:body><office:text><text:p>{text}</text:p></office:text></office:body></office:document-content>'''
    styles = '''<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" office:version="1.2"><office:styles><style:default-style style:family="paragraph"><style:text-properties fo:font-family="Calibri Light" fo:font-size="12pt"/></style:default-style></office:styles></office:document-styles>'''
    with zipfile.ZipFile(path, "w") as zout:
        zout.writestr("mimetype", "application/vnd.oasis.opendocument.text", compress_type=zipfile.ZIP_STORED)
        zout.writestr("content.xml", content)
        zout.writestr("styles.xml", styles)
        zout.writestr("META-INF/manifest.xml", "")


def make_flag_template(path: Path) -> None:
    content = '''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.2"><office:body><office:text><text:p>1ª PARTE</text:p><text:p>[SISGES_PARTE_1]</text:p><text:p>[SISGES_COMPORTAMENTO]</text:p><text:p>2ª PARTE</text:p><text:p>[SISGES_DATA_LOCAL]</text:p><text:p>[SISGES_ASSINATURA_NOME]</text:p><text:p>[SISGES_ASSINATURA_FUNCAO]</text:p></office:text></office:body></office:document-content>'''
    styles = '''<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" office:version="1.2"><office:styles><style:default-style style:family="paragraph"><style:text-properties fo:font-family="Calibri Light" fo:font-size="12pt"/></style:default-style></office:styles><office:master-styles><text:p>NOME: [SISGES_NOME]</text:p><text:p>GRADUAÇÃO: [SISGES_GRADUACAO]</text:p><text:p>ARMA/QUADRO/SERVIÇO: [SISGES_QMS]</text:p><text:p>IDENTIDADE: [SISGES_IDENTIDADE]</text:p><text:p>[SISGES_SEMESTRE_TEXTO] PERÍODO: [SISGES_PERIODO]</text:p><text:p>Continuação das Folhas de Alterações do [SISGES_POSTO_GRADUACAO_CONTINUACAO]</text:p></office:master-styles></office:document-styles>'''
    with zipfile.ZipFile(path, "w") as zout:
        zout.writestr("mimetype", "application/vnd.oasis.opendocument.text", compress_type=zipfile.ZIP_STORED)
        zout.writestr("content.xml", content)
        zout.writestr("styles.xml", styles)
        zout.writestr("META-INF/manifest.xml", "")


def profile(nome: str = "MILITAR TESTE") -> SicapexProfile:
    return SicapexProfile(
        nome_completo=nome,
        nome_guerra="TESTE",
        graduacao_abrev="3º Sgt",
        graduacao_extenso="3º Sgt",
        qm="INFANTARIA",
        identidade="9990000001",
        comportamento="BOM",
    )


def times() -> TimeSummary:
    return TimeSummary(
        tc="00a06m00d",
        tc_arreg="00a06m00d",
        tc_nao_arreg="00a00m00d",
        tc_transito="00a00m00d",
        tc_instalacao="00a00m00d",
        tnc="00a00m00d",
        tscmm="01a00m00d",
        tssd="00a00m00d",
        tsnr="00a00m00d",
        ttes="01a00m00d",
        origem="SICAPEX_BANCO_SISGES",
        dias_reais_ttes=360,
        dias_reais_tnc=0,
    )
