from pathlib import Path
import zipfile

from modules.compilador.application.folha_alteracoes_compiler import validate_odt_format


def test_validate_odt_format_reads_styles_xml(tmp_path):
    odt = tmp_path / "folha.odt"
    make_output_odt(odt, styles_text="cabecalho limpo")

    validations = validate_odt_format(odt)

    assert "OK_STYLES_XML_VALID" in validations


def test_validate_odt_format_detects_placeholder_in_header_styles(tmp_path):
    odt = tmp_path / "folha.odt"
    make_output_odt(odt, styles_text="[NOME]")

    validations = validate_odt_format(odt)

    assert "ERR_TEMPLATE_PLACEHOLDER_LEFTOVER" in validations


def test_validate_odt_format_detects_sisges_marker_in_header_styles(tmp_path):
    odt = tmp_path / "folha.odt"
    make_output_odt(odt, styles_text="[[SISGES:HEADER]]")

    validations = validate_odt_format(odt)

    assert "ERR_TEMPLATE_PLACEHOLDER_LEFTOVER" in validations


def make_output_odt(path: Path, styles_text: str = "") -> None:
    content = '''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.2"><office:body><office:text><text:p>1ª PARTE</text:p></office:text></office:body></office:document-content>'''
    styles = f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" office:version="1.2"><office:styles><style:default-style style:family="paragraph"><style:text-properties fo:font-family="Calibri Light" fo:font-size="12pt"/></style:default-style></office:styles><office:master-styles><text:p xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">{styles_text}</text:p></office:master-styles></office:document-styles>'''
    with zipfile.ZipFile(path, "w") as zout:
        zout.writestr("mimetype", "application/vnd.oasis.opendocument.text", compress_type=zipfile.ZIP_STORED)
        zout.writestr("content.xml", content)
        zout.writestr("styles.xml", styles)
        zout.writestr("META-INF/manifest.xml", "")
